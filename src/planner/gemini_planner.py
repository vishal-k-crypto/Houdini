import json
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.gemini_client import GeminiCLI
from ..utils.logging import logger
from ..utils.prompt_loader import get_planner_prompt
from ..utils.prompt_evolution import prompt_evolution
from ..utils.pattern_store import pattern_store, PatternStore
from ..utils.choice_tracker import choice_tracker
from ..utils.action_optimizer import action_optimizer, ActionOptimizer
from ..ui.thinking_window import show_planner_thinking, show_thinking

TASK_HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "task_history.json"

PLANNING_RULES = """
## Smart Planning Rules

### TWO TYPES OF ACTIONS:
1. **BLIND actions** (no screen check needed) - can be batched together:
   - Open apps via Spotlight (Cmd+Space, type name, Enter)
   - Keyboard shortcuts (Cmd+T, Cmd+L, etc.)
   - Typing text
   - Pressing keys

2. **VISION actions** (need to see screen) - done separately:
   - Click on specific UI elements
   - Verify something on screen
   - Find and interact with dynamic content

### OPTIMIZATION RULES:
- Combine all BLIND actions into ONE subtask
- Example: "Open Safari, go to URL, search" = ONE blind subtask
- Only split when VISION action is needed

### SAFARI SHORTCUTS:
- Cmd+Space → type "Safari" → Enter (open Safari)
- Cmd+T (new tab)
- Cmd+L (focus URL/search bar)
- Type and Enter (search with default engine - Google)

### YOUTUBE NAVIGATION:
- Navigate to channel page: youtube.com/@{channel_name}/videos
- First video in grid is the latest/most recent upload
- Use direct URL navigation when possible to avoid vision actions

### VISION ACTION DESCRIPTIONS:
When vision actions are needed, be SPECIFIC:
- GOOD: "click the first video thumbnail in the main grid"
- BAD: "click the video"
- GOOD: "click the first search result link"
- BAD: "click result"

### TASK PATTERNS:
- "search X" → blind: [Cmd+Space, "Safari", Enter, Cmd+L, type "X", Enter]
- "open X and search Y" → blind: [Cmd+Space, "Safari", Enter, Cmd+L, "Y", Enter]
- "open latest video from {creator}" → blind: [Cmd+Space, Safari, Enter, Cmd+L, youtube.com/@{creator}/videos, Enter] + vision: click first video thumbnail
- "click first result" → vision: click first search result in main content area
"""


class TaskMemory:
    """Store past plans for faster execution."""
    
    def __init__(self, history_file: Path = TASK_HISTORY_FILE):
        self.history_file = history_file
        self.history: Dict[str, dict] = {}
        self._load()
    
    def _load(self):
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
        except:
            self.history = {}
    
    def _save(self):
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except:
            pass
    
    def find_similar(self, task: str) -> Optional[dict]:
        task_lower = task.lower().strip()
        if task_lower in self.history:
            return self.history[task_lower]
        return None
    
    def remember(self, task: str, plan: dict):
        self.history[task.lower().strip()] = plan
        self._save()


class GeminiPlanner:
    """
    Smart Planner - generates batched blind vs vision actions.
    Now enhanced with pattern learning for efficiency.
    """
    def __init__(self, cli: GeminiCLI):
        self.cli = cli
        self.memory = TaskMemory()
        self.pattern_store = pattern_store
        self.action_optimizer = action_optimizer

    def plan(self, task: str) -> List[Dict]:
        """
        Returns list of action batches:
        [{"type": "blind", "actions": [...], "description": "..."},
         {"type": "vision", "action": "...", "description": "..."}]
        """
        # 1. Check for high-confidence learned patterns first
        similar_patterns = self.pattern_store.find_similar(task, threshold=0.7)
        if similar_patterns:
            best_pattern = self.pattern_store.get_best_pattern(similar_patterns)
            if best_pattern and best_pattern.confidence >= 0.85:
                logger.info(f"🧠 Using learned pattern (confidence: {best_pattern.confidence:.0%})")
                try:
                    show_planner_thinking(f"Using learned pattern (confidence: {best_pattern.confidence:.0%})")
                except:
                    pass
                batches = self._pattern_to_batches(best_pattern, task)
                return batches
        
        # 2. Check exact cache
        cached = self.memory.find_similar(task)
        if cached:
            logger.info("⚡ Using cached plan")
            try:
                show_planner_thinking("Using cached plan from memory")
            except:
                pass
            return cached.get("batches", [{"type": "blind", "actions": [task]}])
        
        # 3. Generate pattern hints for the LLM
        try:
            show_planner_thinking("Generating new plan with LLM...")
        except:
            pass
        pattern_hints = self._get_pattern_hints(similar_patterns)
        
        # Load evolved system prompt
        system_prompt = get_planner_prompt()
        
        prompt = f"""{system_prompt}

## Task: {task}
{pattern_hints}
## Output Format
Generate a plan with batched actions. Output JSON:
{{
  "batches": [
    {{"type": "blind", "description": "Open Safari and search", "actions": ["hotkey:command,space", "type:Safari", "key:enter", "wait:0.5", "hotkey:command,l", "type:python tutorials", "key:enter"]}},
    {{"type": "vision", "description": "Click first result", "action": "click first search result"}}
  ]
}}

Action format for blind actions:
- "hotkey:key1,key2" (e.g., "hotkey:command,space")
- "type:text" (e.g., "type:Safari")
- "key:keyname" (e.g., "key:enter")
- "wait:seconds" (e.g., "wait:0.5")

Output JSON only:"""
        
        response = self.cli.generate(prompt)
        try:
            clean = response.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0]
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0]
            
            data = json.loads(clean)
            batches = data.get("batches", [])
            
            # 4. Optimize the plan using learned patterns
            batches = self._optimize_batches(batches, task)
            
            self.memory.remember(task, {"batches": batches})
            logger.info(f"Plan: {len(batches)} batches")
            
            # Record successful planning
            prompt_evolution.record_feedback(
                component="planner",
                task=task,
                success=True,
                actions_taken=[b.get("description", "") for b in batches]
            )
            
            return batches
            
        except Exception as e:
            logger.error(f"Plan parse failed: {e}")
            
            # Record planning failure
            prompt_evolution.record_feedback(
                component="planner",
                task=task,
                success=False,
                error_type="parse_error",
                error_details=str(e)
            )
            
            # Fallback: single blind batch
            return [{"type": "blind", "description": task, "actions": [task]}]
    
    def _pattern_to_batches(self, pattern, task: str) -> List[Dict]:
        """Convert a learned pattern to action batches."""
        # Extract variables from the current task
        _, variables = self.pattern_store.normalize_task(task)
        
        # Apply pattern with current variables
        actions = self.pattern_store.apply_pattern(pattern, variables)
        
        # Use action optimizer to batch them
        batches = self.action_optimizer.batch_actions(actions)
        
        return batches
    
    def _get_pattern_hints(self, similar_patterns) -> str:
        """Generate hints from similar patterns for the LLM."""
        if not similar_patterns:
            return ""
        
        hints = ["\n## Similar Patterns (for reference):"]
        for pattern, similarity in similar_patterns[:3]:  # Top 3 patterns
            if pattern.success_rate > 0.7:
                hints.append(f"- Pattern '{pattern.task_template}' works well ({pattern.success_rate:.0%} success)")
                if pattern.optimized_waits:
                    avg_wait = sum(pattern.optimized_waits.values()) / len(pattern.optimized_waits)
                    hints.append(f"  Optimal avg wait: {avg_wait:.1f}s")
        
        return "\n".join(hints) + "\n" if len(hints) > 1 else ""
    
    def _optimize_batches(self, batches: List[Dict], task: str) -> List[Dict]:
        """Optimize batches using the action optimizer."""
        optimized_batches = []
        
        for batch in batches:
            if batch.get("type") == "blind":
                actions = batch.get("actions", [])
                if actions:
                    # Optimize the action sequence
                    result = self.action_optimizer.optimize_sequence(
                        actions,
                        context={"task": task}
                    )
                    
                    if result.changes_made:
                        logger.debug(f"Optimizations: {', '.join(result.changes_made[:3])}")
                    
                    batch["actions"] = result.optimized_actions
            
            optimized_batches.append(batch)
        
        return optimized_batches

    def plan_simple(self, task: str) -> List[str]:
        """Legacy method - returns flat subtask list."""
        batches = self.plan(task)
        subtasks = []
        for b in batches:
            subtasks.append(b.get("description", str(b)))
        return subtasks if subtasks else [task]
