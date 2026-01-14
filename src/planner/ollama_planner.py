"""
Ollama-based Planner using Qwen 3 Coder model.
Replaces Gemini planner with Ollama Qwen 3 Coder 480B.
"""
import json
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.ollama_client import OllamaClient
from ..utils.logging import logger
from ..utils.prompt_loader import get_planner_prompt
from ..utils.prompt_evolution import prompt_evolution
from ..utils.pattern_store import pattern_store
from ..utils.choice_tracker import choice_tracker
from ..utils.action_optimizer import action_optimizer
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


class OllamaPlanner:
    """
    Ollama-based Smart Planner using Qwen 3 Coder 480B.
    Generates batched blind vs vision actions with pattern learning.
    """
    def __init__(self, client: OllamaClient):
        self.client = client
        self.memory = TaskMemory()
        self.pattern_store = pattern_store
        self.action_optimizer = action_optimizer

    def plan(self, task: str, executor_history: Optional[List[Dict]] = None) -> List[Dict]:
        """
        Generate plan for task with awareness of previous executor operations.
        
        Args:
            task: User task description
            executor_history: List of previous tasks executor has completed
        
        Returns:
            List of action batches:
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
        
        # 3. Generate with executor history context
        try:
            show_planner_thinking("Generating new plan with Ollama Qwen 3 Coder...")
        except:
            pass
        
        pattern_hints = self._get_pattern_hints(similar_patterns)
        history_context = self._format_executor_history(executor_history)
        
        # Load evolved system prompt
        system_prompt = get_planner_prompt()
        
        prompt = f"""{system_prompt}

## Task: {task}

{history_context}

{pattern_hints}

## Output Format
Return a JSON object with this structure:
{{
  "batches": [
    {{
      "type": "blind",
      "description": "What this batch does",
      "actions": [
        "hotkey:command,space",
        "type:Safari",
        "key:return",
        "wait:1.5"
      ]
    }},
    {{
      "type": "vision",
      "description": "What to find and click",
      "action": "click the first search result"
    }}
  ]
}}

Generate the plan now:
"""
        
        # Generate with Ollama
        try:
            response = self.client.generate_json(prompt, system_prompt=None, temperature=0.3)
            
            if "batches" not in response:
                raise ValueError("Response missing 'batches' key")
            
            batches = response["batches"]
            
            # Optimize actions
            batches = self.action_optimizer.optimize_plan(batches)
            
            # Cache the plan
            self.memory.remember(task, {"batches": batches})
            
            # Track this choice
            choice_tracker.add_choice(task, {"plan": batches})
            
            logger.info(f"✅ Generated plan with {len(batches)} batches")
            return batches
            
        except Exception as e:
            logger.error(f"Failed to generate plan with Ollama: {e}")
            # Fallback to simple plan
            return self._fallback_plan(task)
    
    def _format_executor_history(self, history: Optional[List[Dict]]) -> str:
        """Format executor history for context."""
        if not history:
            return ""
        
        context = "\n## Previous Executor Operations\n"
        context += "The executor has previously completed these tasks:\n"
        
        for i, item in enumerate(history[-5:], 1):  # Last 5 tasks
            task_desc = item.get("task", "Unknown task")
            success = item.get("success", False)
            timestamp = item.get("timestamp", "")
            status = "✓" if success else "✗"
            
            context += f"{i}. {status} {task_desc}"
            if timestamp:
                context += f" (at {timestamp})"
            context += "\n"
        
        context += "\nConsider this context when planning the current task.\n"
        return context
    
    def _get_pattern_hints(self, similar_patterns) -> str:
        """Generate hints from similar patterns."""
        if not similar_patterns:
            return ""
        
        hints = "\n## Similar Task Patterns Found\n"
        for pattern in similar_patterns[:3]:  # Top 3
            hints += f"- Pattern: {pattern.task_template} (confidence: {pattern.confidence:.0%})\n"
            hints += f"  Average time: {pattern.avg_execution_time:.1f}s\n"
        
        return hints
    
    def _pattern_to_batches(self, pattern, task: str) -> List[Dict]:
        """Convert a pattern to executable batches."""
        try:
            # Pattern stores the successful plan structure
            return pattern.plan_structure.get("batches", [])
        except:
            return self._fallback_plan(task)
    
    def _fallback_plan(self, task: str) -> List[Dict]:
        """Generate a simple fallback plan when LLM fails."""
        logger.warning("Using fallback plan")
        
        # Simple heuristic-based plan
        if "search" in task.lower():
            return [
                {
                    "type": "blind",
                    "description": "Open Safari and search",
                    "actions": [
                        "hotkey:command,space",
                        "type:Safari",
                        "key:return",
                        "wait:1.5",
                        "hotkey:command,l",
                        f"type:{task}",
                        "key:return",
                        "wait:2"
                    ]
                }
            ]
        else:
            return [
                {
                    "type": "blind",
                    "description": task,
                    "actions": [task]
                }
            ]


# Alias for compatibility
QwenPlanner = OllamaPlanner
