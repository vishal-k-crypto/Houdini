import json
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.gemini_client import GeminiCLI
from ..utils.logging import logger
from ..utils.prompt_loader import get_planner_prompt
from ..utils.schemas import parse_planner_response, PlannerResponse, BlindBatch, VisionBatch
from ..utils.prompt_evolution import prompt_evolution
from ..utils.pattern_store import pattern_store, PatternStore
from ..utils.choice_tracker import choice_tracker
from ..utils.action_optimizer import action_optimizer, ActionOptimizer
from ..utils.lesson_store import lesson_store
from ..ui.thinking_window import show_planner_thinking, show_thinking

# Import app knowledge for action validation
try:
    from ..utils.app_knowledge import app_knowledge, AppKnowledge
    APP_KNOWLEDGE_AVAILABLE = True
except ImportError:
    APP_KNOWLEDGE_AVAILABLE = False
    app_knowledge = None

# Import web interaction policy for website action validation
try:
    from ..utils.web_interaction_policy import get_policy, WebInteractionPolicy
    WEB_POLICY_AVAILABLE = True
except ImportError:
    WEB_POLICY_AVAILABLE = False
    get_policy = None

TASK_HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "task_history.json"

PLANNING_RULES = """
## Smart Planning Rules

### ⚠️ CRITICAL: VISION-FIRST FOR WEBSITES
**When interacting with ANY website (YouTube, Google, etc.), use VISION not hotkeys!**

Website hotkeys are UNRELIABLE:
- Cmd+F is "find in page", NOT website search
- Cmd+K opens browser command bar, NOT website search
- Each website has different shortcuts (or none at all)

**For website interactions:**
- ✅ Use VISION: "click the search field", "click first video thumbnail"
- ❌ DON'T use hotkeys: "hotkey:command,f" for website search

**Exception - Browser CHROME control is OK:**
- Cmd+L (focus URL bar to navigate)
- Cmd+T (new tab)
- Cmd+W (close tab)

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

### ⚠️ CRITICAL: APP-SPECIFIC SEARCH SHORTCUTS
Different apps use DIFFERENT shortcuts for search! Using the wrong one causes failures.

| App           | Search Shortcut       | WRONG Shortcut | Notes                    |
|---------------|----------------------|----------------|--------------------------|
| **Apple Music** | `Cmd+Option+F`       | ~~Cmd+F~~      | Cmd+F does nothing useful |
| **Spotify**   | `Cmd+L` or `Cmd+K`   | ~~Cmd+F~~      | Cmd+F doesn't search     |
| **Safari**    | `Cmd+L` (URL bar)    | ~~Cmd+F~~      | Cmd+F is find-in-page    |
| **Finder**    | `Cmd+F`              | ✓ Correct      | Cmd+F works in Finder    |
| **WhatsApp**  | `Cmd+F`              | ✓ Correct      | Cmd+F works in WhatsApp  |
| **Notes**     | `Cmd+Option+F`       | ~~Cmd+F~~      | Cmd+F finds in note only |
| **VS Code**   | `Cmd+Shift+F`        | ~~Cmd+F~~      | Cmd+F is find in file    |

### SAFARI/BROWSER SHORTCUTS:
- Cmd+Space → type "Safari" → Enter (open Safari)
- Cmd+T (new tab)
- Cmd+L (focus URL/search bar - USE THIS FOR WEB SEARCH, NOT Cmd+F)
- Type and Enter (search with default engine - Google)

### APPLE MUSIC SHORTCUTS:
- Cmd+Option+F (search for songs - NOT Cmd+F!)
- Space (play/pause)
- Cmd+Right/Left (next/previous track)

### SPOTIFY SHORTCUTS:
- Cmd+L or Cmd+K (search bar - NOT Cmd+F!)
- Space (play/pause)

### YOUTUBE NAVIGATION (VISION REQUIRED):
- Navigate to channel page: youtube.com/@{channel_name}/videos
- First video in grid is the latest/most recent upload
- Use direct URL navigation to reach the page, then VISION to click
- **To search on YouTube:**
  1. Navigate to youtube.com via URL bar (Cmd+L)
  2. Wait for page to load (3 seconds)
  3. VISION: "click the search box at top of page"
  4. Type search query
  5. Press Enter
  6. VISION: "click the first video result"

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
- "play song X on Apple Music" → blind: [Cmd+Space, "Music", Enter, wait:2, Cmd+Option+F, type "X", Enter]
- "play song X on Spotify" → blind: [Cmd+Space, "Spotify", Enter, wait:2.5, Cmd+L, type "X", Enter]
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
        self.lesson_store = lesson_store
        self.app_knowledge = app_knowledge if APP_KNOWLEDGE_AVAILABLE else None

    def _detect_target_app(self, task: str) -> Optional[str]:
        """Detect which app the task is targeting."""
        task_lower = task.lower()
        
        app_keywords = {
            "Music": ["apple music", "music app", "play song", "play music"],
            "Spotify": ["spotify"],
            "Safari": ["safari", "browse", "website", "web search"],
            "Finder": ["finder", "folder", "file"],
            "WhatsApp": ["whatsapp"],
            "Messages": ["messages", "imessage", "text message"],
            "Notes": ["notes app", "apple notes"],
            "Terminal": ["terminal", "command line"],
            "Code": ["vs code", "vscode", "visual studio code"],
        }
        
        for app_name, keywords in app_keywords.items():
            for keyword in keywords:
                if keyword in task_lower:
                    return app_name

            def _is_website_task(self, task: str) -> bool:
                """Check if task involves website interaction."""
                task_lower = task.lower()
        
                website_keywords = [
                    "youtube", "google", "facebook", "twitter", "instagram",
                    "reddit", "amazon", "netflix", "github", "stackoverflow",
                    "website", "web page", "search on", "find on", "click video",
                    "click link", "click button on", "play video on", "browse to"
                ]
        
                return any(kw in task_lower for kw in website_keywords)
    
            def _convert_website_hotkeys_to_vision(self, batch: Dict, task: str) -> Dict:
                """
                Convert hotkey-based actions to vision-based actions for website tasks.
        
                This is the core of vision-first web interaction.
                """
                if not WEB_POLICY_AVAILABLE or batch.get("type") != "blind":
                    return batch
        
                policy = get_policy()
                actions = batch.get("actions", [])
                task_lower = task.lower()
        
                # Check if this is a browser task
                target_app = self._detect_target_app(task)
                if not target_app or not policy.is_browser_app(target_app):
                    return batch
        
                # Check if this involves website interaction
                if not self._is_website_task(task):
                    return batch
        
                # Convert problematic hotkeys to vision actions
                converted_actions = []
                vision_needed = False
        
                for i, action in enumerate(actions):
                    action_str = str(action).lower()
            
                    # Check for forbidden hotkeys
                    if "hotkey:" in action_str:
                        # Extract hotkey
                        parts = action.split(":", 1)
                        if len(parts) == 2:
                            hotkey = parts[1].strip()
                            is_forbidden, reason = policy.is_hotkey_forbidden(
                                target_app,
                                hotkey,
                                action_context=task
                            )
                    
                            if is_forbidden:
                                logger.warning(f"⚠️ Forbidden hotkey detected: {hotkey}")
                                logger.warning(f"   Reason: {reason}")
                        
                                # Convert to vision action
                                if "search" in task_lower or "find" in task_lower:
                                    # Convert search hotkey to vision
                                    vision_needed = True
                                    logger.info(f"   ✅ Converting to vision action")
                                    # Skip this hotkey, will be handled by vision batch below
                                    continue
                                else:
                                    # Keep other hotkeys but warn
                                    converted_actions.append(action)
                            else:
                                converted_actions.append(action)
                        else:
                            converted_actions.append(action)
                    else:
                        converted_actions.append(action)
        
                # If we removed hotkeys, we need to add a vision action instead
                if vision_needed:
                    # Update the batch description
                    batch["actions"] = converted_actions
                    batch["requires_vision"] = True
            
                    # Log the conversion
                    try:
                        show_planner_thinking(f"Converted website hotkeys to vision-based interaction")
                    except:
                        pass
        
                return batch
        
        return None

    def _validate_and_correct_actions(self, actions: List[str], target_app: Optional[str]) -> List[str]:
        """
        Validate actions against app-specific knowledge and correct mistakes.
        
        This prevents common errors like using Cmd+F in Apple Music when
        Cmd+Option+F is needed for search.
        """
        if not self.app_knowledge or not target_app:
            return actions
        
        corrected = []
        corrections_made = []
        
        for action in actions:
            is_valid, correction_msg = self.app_knowledge.validate_action(target_app, action)
            
            if not is_valid:
                # Try to get the correct action
                logger.warning(f"⚠️ Invalid action for {target_app}: {action}")
                logger.warning(f"   Reason: {correction_msg}")
                
                # Check if this is a search-related mistake
                if "search" in action.lower() or ("command,f" in action and target_app in ["Music", "Spotify"]):
                    correct_keys = self.app_knowledge.get_search_shortcut(target_app)
                    if correct_keys:
                        corrected_action = f"hotkey:{','.join(correct_keys)}"
                        corrected.append(corrected_action)
                        corrections_made.append(f"Changed '{action}' to '{corrected_action}' for {target_app}")
                        logger.info(f"   ✅ Corrected to: {corrected_action}")
                        continue
                
                # If we can't correct, still include the action but log warning
                corrected.append(action)
            else:
                corrected.append(action)
        
        if corrections_made:
            try:
                show_planner_thinking(f"Corrected {len(corrections_made)} action(s) for {target_app}")
            except:
                pass
            
            # Record as a lesson for future
            if self.lesson_store:
                for correction in corrections_made:
                    self.lesson_store.record_failure(
                        component="planner",
                        task=f"Action for {target_app}",
                        error_type="wrong_shortcut",
                        error_details=correction,
                        suggestion=f"Use app-specific shortcuts for {target_app}"
                    )
        
        return corrected

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
        
        # 4. Retrieve relevant past lessons (RAG-based)
        lessons_context = self.lesson_store.get_prompt_context(task, "planner")
        
        # Load evolved system prompt
        system_prompt = get_planner_prompt()
        
        prompt = f"""{system_prompt}
{lessons_context}
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
            # Use Pydantic validation for strict schema enforcement
            parsed = parse_planner_response(response)
            batches = [batch.model_dump() for batch in parsed.batches]
            
            # 4. Optimize the plan using learned patterns
            batches = self._optimize_batches(batches, task)
            
            # 5. Detect target app and validate/correct actions
            target_app = self._detect_target_app(task)
            if target_app:
                logger.info(f"🎯 Target app detected: {target_app}")
                batches = self._validate_batches(batches, target_app)
            
            # 6. Validate and convert website hotkey actions to vision
            batches = self._validate_and_convert_website_actions(batches, task)
            
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
            
            # Also record as a lesson for future retrieval
            self.lesson_store.record_failure(
                component="planner",
                task=task,
                error_type="parse_error",
                error_details=str(e),
                suggestion="Ensure JSON output is well-formed with proper structure"
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
    
    def _validate_batches(self, batches: List[Dict], target_app: str) -> List[Dict]:
        """
        Validate all batches against app-specific knowledge.
        Corrects common mistakes like using wrong shortcuts.
        """
        validated_batches = []
        
        for batch in batches:
            if batch.get("type") == "blind":
                actions = batch.get("actions", [])
                if actions:
                    # Validate and correct actions for the target app
                    corrected_actions = self._validate_and_correct_actions(actions, target_app)
                    batch["actions"] = corrected_actions
            
            validated_batches.append(batch)
        
        return validated_batches
    
        def _validate_and_convert_website_actions(self, batches: List[Dict], task: str) -> List[Dict]:
            """
            Validate and convert hotkey actions to vision actions for website tasks.
            This ensures website interactions use vision instead of unreliable hotkeys.
            """
            if not WEB_POLICY_AVAILABLE:
                return batches
        
            # Check if this is a website task
            if not self._is_website_task(task):
                return batches
        
            validated = []
            for batch in batches:
                converted_batch = self._convert_website_hotkeys_to_vision(batch, task)
                validated.append(converted_batch)
        
            return validated
    
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
