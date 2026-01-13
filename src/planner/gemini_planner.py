import json
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.gemini_client import GeminiCLI
from ..utils.logging import logger
from ..utils.prompt_loader import get_planner_prompt
from ..utils.prompt_evolution import prompt_evolution

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

### TASK PATTERNS:
- "search X" → blind: [Cmd+Space, "Safari", Enter, Cmd+L, type "X", Enter]
- "open X and search Y" → blind: [Cmd+Space, "Safari", Enter, Cmd+L, "Y", Enter]
- "click first result" → vision: need to see screen for coordinates
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
    """
    def __init__(self, cli: GeminiCLI):
        self.cli = cli
        self.memory = TaskMemory()

    def plan(self, task: str) -> List[Dict]:
        """
        Returns list of action batches:
        [{"type": "blind", "actions": [...], "description": "..."},
         {"type": "vision", "action": "...", "description": "..."}]
        """
        # Check cache
        cached = self.memory.find_similar(task)
        if cached:
            logger.info("⚡ Using cached plan")
            return cached.get("batches", [{"type": "blind", "actions": [task]}])
        
        # Load evolved system prompt
        system_prompt = get_planner_prompt()
        
        prompt = f"""{system_prompt}

## Task: {task}

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
            
            self.memory.remember(task, data)
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

    def plan_simple(self, task: str) -> List[str]:
        """Legacy method - returns flat subtask list."""
        batches = self.plan(task)
        subtasks = []
        for b in batches:
            subtasks.append(b.get("description", str(b)))
        return subtasks if subtasks else [task]
