"""
Vision Feedback Loop - LangGraph-based adaptive vision system.

This module creates a feedback loop for UI element localization that:
1. Learns from successful/failed clicks
2. Adapts prompts based on context
3. Maintains a memory of UI patterns
4. Improves over time through reinforcement

The system uses LangGraph for:
- State persistence across sessions
- Checkpointing for reliability
- Clear node-based learning flow
"""

import json
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, TypedDict, Annotated
from dataclasses import dataclass, field, asdict
import operator

from .logging import logger

# LangGraph imports
try:
    from langgraph.graph import StateGraph, END, START
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.checkpoint.sqlite import SqliteSaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("LangGraph not available for vision feedback loop")


# ============================================================================
# STATE DEFINITIONS
# ============================================================================

@dataclass
class VisionAttempt:
    """Record of a single vision localization attempt."""
    timestamp: str
    element_description: str
    context: str  # App name, window title, task context
    method_used: str  # "ui_tars", "apple_vision", etc.
    coordinates: Optional[Tuple[int, int]]
    confidence: float
    success: Optional[bool] = None  # Set after click verification
    error: Optional[str] = None
    latency_ms: float = 0.0
    prompt_used: str = ""
    raw_output: str = ""


@dataclass
class ElementPattern:
    """Learned pattern for finding specific UI elements."""
    element_type: str  # "button", "field", "link", "icon", etc.
    keywords: List[str]  # Words that identify this type
    typical_locations: List[str]  # "top-right", "center", "bottom", etc.
    avg_confidence: float
    success_rate: float
    total_attempts: int
    last_updated: str
    
    # Learned prompt modifications
    effective_hints: List[str] = field(default_factory=list)
    ineffective_hints: List[str] = field(default_factory=list)


@dataclass  
class AppContext:
    """Context about a specific application's UI patterns."""
    app_name: str
    learned_elements: Dict[str, ElementPattern] = field(default_factory=dict)
    common_layouts: List[str] = field(default_factory=list)
    success_rate: float = 0.5
    total_interactions: int = 0


class VisionFeedbackState(TypedDict):
    """State for the LangGraph vision feedback loop."""
    # Current request
    element_description: str
    task_context: str
    app_name: str
    screenshot_path: Optional[str]
    
    # Current attempt
    current_prompt: str
    current_method: str
    coordinates: Optional[Tuple[int, int]]
    confidence: float
    raw_output: str
    
    # Feedback
    click_success: Optional[bool]
    verification_method: str
    error_message: Optional[str]
    
    # Learning state
    attempt_count: int
    max_attempts: int
    should_retry: bool
    
    # History (accumulates)
    attempts: Annotated[List[Dict], operator.add]
    
    # Learned patterns (loaded from storage)
    app_patterns: Dict[str, Any]
    element_patterns: Dict[str, Any]


# ============================================================================
# VISION MEMORY - Persistent storage for learned patterns
# ============================================================================

class VisionMemory:
    """
    Persistent memory for vision learning.
    Stores patterns, success rates, and prompt effectiveness.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path(__file__).parent.parent.parent / "data" / "vision_memory.json"
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self._app_contexts: Dict[str, AppContext] = {}
        self._element_patterns: Dict[str, ElementPattern] = {}
        self._recent_attempts: List[VisionAttempt] = []
        
        # Load from disk
        self._load()
    
    def _load(self):
        """Load memory from disk."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                
                # Restore app contexts
                for app_name, ctx_data in data.get("app_contexts", {}).items():
                    self._app_contexts[app_name] = AppContext(
                        app_name=ctx_data["app_name"],
                        learned_elements=ctx_data.get("learned_elements", {}),
                        common_layouts=ctx_data.get("common_layouts", []),
                        success_rate=ctx_data.get("success_rate", 0.5),
                        total_interactions=ctx_data.get("total_interactions", 0)
                    )
                
                # Restore element patterns
                for pattern_key, pattern_data in data.get("element_patterns", {}).items():
                    self._element_patterns[pattern_key] = ElementPattern(**pattern_data)
                
                logger.info(f"📚 Loaded vision memory: {len(self._app_contexts)} apps, {len(self._element_patterns)} patterns")
                
            except Exception as e:
                logger.warning(f"Failed to load vision memory: {e}")
    
    def _save(self):
        """Save memory to disk."""
        try:
            data = {
                "app_contexts": {
                    name: asdict(ctx) for name, ctx in self._app_contexts.items()
                },
                "element_patterns": {
                    key: asdict(pattern) for key, pattern in self._element_patterns.items()
                },
                "last_updated": datetime.now().isoformat()
            }
            
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
                
        except Exception as e:
            logger.warning(f"Failed to save vision memory: {e}")
    
    def get_app_context(self, app_name: str) -> AppContext:
        """Get or create context for an app."""
        if app_name not in self._app_contexts:
            self._app_contexts[app_name] = AppContext(app_name=app_name)
        return self._app_contexts[app_name]
    
    def get_element_hints(self, element_description: str, app_name: str = "") -> List[str]:
        """Get learned hints for finding this type of element."""
        hints = []
        
        # Check for exact match patterns
        pattern_key = self._make_pattern_key(element_description)
        if pattern_key in self._element_patterns:
            pattern = self._element_patterns[pattern_key]
            hints.extend(pattern.effective_hints)
        
        # Check for keyword matches
        desc_lower = element_description.lower()
        for key, pattern in self._element_patterns.items():
            if any(kw in desc_lower for kw in pattern.keywords):
                hints.extend(pattern.effective_hints[:2])  # Top 2 hints
        
        # Check app-specific patterns
        if app_name:
            app_ctx = self.get_app_context(app_name)
            for elem_key, elem_data in app_ctx.learned_elements.items():
                if elem_key in desc_lower or desc_lower in elem_key:
                    if isinstance(elem_data, dict) and "hints" in elem_data:
                        hints.extend(elem_data["hints"][:2])
        
        return list(set(hints))[:5]  # Unique, max 5
    
    def record_attempt(self, attempt: VisionAttempt):
        """Record a vision attempt for learning."""
        self._recent_attempts.append(attempt)
        
        # Update app context
        app_ctx = self.get_app_context(attempt.context.split(":")[0] if ":" in attempt.context else "unknown")
        app_ctx.total_interactions += 1
        
        # Update success rate if we know the outcome
        if attempt.success is not None:
            total = app_ctx.total_interactions
            current_rate = app_ctx.success_rate
            new_rate = ((current_rate * (total - 1)) + (1.0 if attempt.success else 0.0)) / total
            app_ctx.success_rate = new_rate
        
        # Update element patterns
        self._update_element_pattern(attempt)
        
        # Save periodically
        if len(self._recent_attempts) % 10 == 0:
            self._save()
    
    def record_feedback(self, element_description: str, success: bool, 
                       prompt_used: str = "", context: str = ""):
        """Record feedback about whether a click succeeded."""
        pattern_key = self._make_pattern_key(element_description)
        
        if pattern_key not in self._element_patterns:
            self._element_patterns[pattern_key] = ElementPattern(
                element_type=self._infer_element_type(element_description),
                keywords=self._extract_keywords(element_description),
                typical_locations=[],
                avg_confidence=0.5,
                success_rate=0.5,
                total_attempts=0,
                last_updated=datetime.now().isoformat()
            )
        
        pattern = self._element_patterns[pattern_key]
        pattern.total_attempts += 1
        
        # Update success rate with exponential moving average
        alpha = 0.3  # Learning rate
        pattern.success_rate = (1 - alpha) * pattern.success_rate + alpha * (1.0 if success else 0.0)
        pattern.last_updated = datetime.now().isoformat()
        
        # Extract effective/ineffective hints from prompt
        if prompt_used:
            hints = self._extract_hints_from_prompt(prompt_used)
            if success:
                pattern.effective_hints.extend(hints)
                pattern.effective_hints = list(set(pattern.effective_hints))[-10:]  # Keep last 10
            else:
                pattern.ineffective_hints.extend(hints)
                pattern.ineffective_hints = list(set(pattern.ineffective_hints))[-10:]
        
        self._save()
    
    def _make_pattern_key(self, element_description: str) -> str:
        """Create a normalized key for element patterns."""
        # Normalize and hash
        normalized = element_description.lower().strip()
        # Remove common words
        for word in ["the", "a", "an", "this", "that"]:
            normalized = normalized.replace(f" {word} ", " ")
        return hashlib.md5(normalized.encode()).hexdigest()[:12]
    
    def _infer_element_type(self, description: str) -> str:
        """Infer element type from description."""
        desc_lower = description.lower()
        
        if any(w in desc_lower for w in ["button", "btn", "submit", "click", "press"]):
            return "button"
        elif any(w in desc_lower for w in ["field", "input", "text", "enter", "type"]):
            return "field"
        elif any(w in desc_lower for w in ["link", "url", "href"]):
            return "link"
        elif any(w in desc_lower for w in ["icon", "image", "logo"]):
            return "icon"
        elif any(w in desc_lower for w in ["menu", "dropdown", "select"]):
            return "menu"
        elif any(w in desc_lower for w in ["checkbox", "toggle", "switch"]):
            return "toggle"
        else:
            return "unknown"
    
    def _extract_keywords(self, description: str) -> List[str]:
        """Extract meaningful keywords from description."""
        # Remove stop words and extract significant words
        stop_words = {"the", "a", "an", "this", "that", "in", "on", "at", "to", "for", "of", "with"}
        words = description.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords[:5]
    
    def _extract_hints_from_prompt(self, prompt: str) -> List[str]:
        """Extract hint phrases from a prompt."""
        hints = []
        
        # Look for hint patterns
        hint_markers = ["look for", "find the", "locate", "should be", "typically", "usually"]
        for marker in hint_markers:
            if marker in prompt.lower():
                # Extract the phrase after the marker
                idx = prompt.lower().find(marker)
                phrase = prompt[idx:idx+50].split(".")[0].split(",")[0]
                hints.append(phrase)
        
        return hints
    
    def _update_element_pattern(self, attempt: VisionAttempt):
        """Update patterns based on attempt."""
        pattern_key = self._make_pattern_key(attempt.element_description)
        
        if pattern_key not in self._element_patterns:
            self._element_patterns[pattern_key] = ElementPattern(
                element_type=self._infer_element_type(attempt.element_description),
                keywords=self._extract_keywords(attempt.element_description),
                typical_locations=[],
                avg_confidence=attempt.confidence,
                success_rate=0.5,
                total_attempts=1,
                last_updated=datetime.now().isoformat()
            )
        else:
            pattern = self._element_patterns[pattern_key]
            pattern.total_attempts += 1
            
            # Update average confidence
            alpha = 0.2
            pattern.avg_confidence = (1 - alpha) * pattern.avg_confidence + alpha * attempt.confidence
            pattern.last_updated = datetime.now().isoformat()


# ============================================================================
# ENHANCED PROMPT BUILDER
# ============================================================================

class AdaptivePromptBuilder:
    """
    Builds adaptive prompts for UI-TARS based on:
    - Element type and context
    - Learned patterns from memory
    - Current app/window state
    """
    
    def __init__(self, memory: VisionMemory):
        self.memory = memory
        
        # Base prompt templates for different element types
        self.templates = {
            "button": """You are analyzing a screenshot to find a BUTTON element.

TARGET: "{description}"
APP CONTEXT: {app_context}

BUTTON IDENTIFICATION RULES:
1. Buttons often have rounded corners or distinct borders
2. Text inside buttons is usually centered
3. Buttons may have icons alongside text
4. Common locations: toolbars, dialogs, form bottoms
5. Look for hover/focus states indicating interactivity

{learned_hints}

OUTPUT FORMAT:
Return ONLY valid JSON: {{"point": [x, y], "confidence": 0.0-1.0, "element_text": "exact text on button"}}
If multiple matches, choose the MOST PROMINENT one.
If NOT FOUND, return: {{"point": null, "confidence": 0.0, "reason": "why not found"}}""",

            "field": """You are analyzing a screenshot to find an INPUT FIELD.

TARGET: "{description}"
APP CONTEXT: {app_context}

INPUT FIELD IDENTIFICATION:
1. Look for rectangular areas with borders or underlines
2. May have placeholder text (grayed out)
3. Often have labels above or beside them
4. Look for text cursor indicators
5. Search fields often have magnifying glass icons

{learned_hints}

OUTPUT FORMAT:
Return ONLY valid JSON: {{"point": [x, y], "confidence": 0.0-1.0, "field_label": "associated label"}}
Click point should be CENTER of the input area.
If NOT FOUND, return: {{"point": null, "confidence": 0.0, "reason": "why not found"}}""",

            "icon": """You are analyzing a screenshot to find an ICON.

TARGET: "{description}"
APP CONTEXT: {app_context}

ICON IDENTIFICATION:
1. Icons are small graphical elements (typically 16-48px)
2. May represent actions, status, or navigation
3. Often in toolbars, menus, or beside text
4. Look for common icon shapes (gear=settings, X=close, +=add)

{learned_hints}

OUTPUT FORMAT:
Return ONLY valid JSON: {{"point": [x, y], "confidence": 0.0-1.0, "icon_type": "description"}}
Click point should be CENTER of the icon.
If NOT FOUND, return: {{"point": null, "confidence": 0.0, "reason": "why not found"}}""",

            "menu": """You are analyzing a screenshot to find a MENU item.

TARGET: "{description}"
APP CONTEXT: {app_context}

MENU IDENTIFICATION:
1. Menu items are usually in lists (horizontal or vertical)
2. Look in menu bars, dropdowns, context menus, sidebars
3. May have icons, checkmarks, or keyboard shortcuts
4. Hover states often change background color

{learned_hints}

OUTPUT FORMAT:
Return ONLY valid JSON: {{"point": [x, y], "confidence": 0.0-1.0, "menu_path": "parent > item"}}
If NOT FOUND, return: {{"point": null, "confidence": 0.0, "reason": "why not found"}}""",

            "link": """You are analyzing a screenshot to find a LINK.

TARGET: "{description}"
APP CONTEXT: {app_context}

LINK IDENTIFICATION:
1. Links are often underlined or colored differently (blue common)
2. Text links change cursor to pointer on hover
3. May be inline with other text or standalone
4. In web pages, look for anchor-style elements

{learned_hints}

OUTPUT FORMAT:
Return ONLY valid JSON: {{"point": [x, y], "confidence": 0.0-1.0, "link_text": "visible text"}}
If NOT FOUND, return: {{"point": null, "confidence": 0.0, "reason": "why not found"}}""",

            "generic": """You are analyzing a screenshot to find a UI ELEMENT.

TARGET: "{description}"
APP CONTEXT: {app_context}

GENERAL STRATEGY:
1. Scan the entire screen systematically (left-to-right, top-to-bottom)
2. Look for text that matches the description
3. Consider element position relative to other UI components
4. Check common locations: headers, sidebars, dialogs, toolbars
5. If description mentions color/size/position, use those cues

{learned_hints}

COORDINATE SYSTEM:
- Origin (0,0) is TOP-LEFT corner
- X increases going RIGHT
- Y increases going DOWN
- Return the CENTER point of the target element

OUTPUT FORMAT:
Return ONLY valid JSON: {{"point": [x, y], "confidence": 0.0-1.0, "element_found": "what you found"}}
If NOT FOUND, return: {{"point": null, "confidence": 0.0, "reason": "detailed explanation"}}"""
        }
    
    def build_prompt(
        self,
        element_description: str,
        app_name: str = "",
        window_title: str = "",
        task_context: str = "",
        previous_attempts: List[Dict] = None
    ) -> str:
        """Build an adaptive prompt for finding an element."""
        
        # Determine element type
        element_type = self.memory._infer_element_type(element_description)
        template = self.templates.get(element_type, self.templates["generic"])
        
        # Build app context string
        app_context = f"App: {app_name}" if app_name else "Unknown app"
        if window_title:
            app_context += f" | Window: {window_title}"
        if task_context:
            app_context += f" | Task: {task_context}"
        
        # Get learned hints
        hints = self.memory.get_element_hints(element_description, app_name)
        learned_hints_str = ""
        if hints:
            learned_hints_str = "LEARNED HINTS (from past successes):\n" + "\n".join(f"- {h}" for h in hints)
        
        # Add retry context if this is a retry
        if previous_attempts:
            learned_hints_str += "\n\nPREVIOUS ATTEMPTS (avoid these areas):\n"
            for attempt in previous_attempts[-3:]:  # Last 3 attempts
                if attempt.get("coordinates"):
                    x, y = attempt["coordinates"]
                    learned_hints_str += f"- Tried ({x}, {y}) with {attempt.get('confidence', 0):.0%} confidence - FAILED\n"
        
        # Build the prompt
        prompt = template.format(
            description=element_description,
            app_context=app_context,
            learned_hints=learned_hints_str
        )
        
        return prompt


# ============================================================================
# LANGGRAPH VISION FEEDBACK LOOP
# ============================================================================

def create_vision_feedback_graph(memory: VisionMemory, localizer) -> StateGraph:
    """
    Create the LangGraph-based vision feedback loop.
    
    Nodes:
    1. prepare - Build adaptive prompt with learned hints
    2. locate - Run UI-TARS localization
    3. verify - Check if location seems valid
    4. execute - Perform click (optional)
    5. feedback - Record success/failure and learn
    6. retry_decision - Decide whether to retry with new prompt
    """
    
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("LangGraph required for vision feedback loop")
    
    prompt_builder = AdaptivePromptBuilder(memory)
    
    # Node functions
    def prepare_node(state: VisionFeedbackState) -> Dict:
        """Prepare the prompt with learned context."""
        prompt = prompt_builder.build_prompt(
            element_description=state["element_description"],
            app_name=state.get("app_name", ""),
            task_context=state.get("task_context", ""),
            previous_attempts=state.get("attempts", [])
        )
        
        return {
            "current_prompt": prompt,
            "current_method": "ui_tars_adaptive"
        }
    
    def locate_node(state: VisionFeedbackState) -> Dict:
        """Run the localization."""
        from .local_vision_localizer import LocalizationResult
        
        start_time = time.time()
        
        try:
            # Use the localizer with our adaptive prompt
            result = localizer.find_element_with_prompt(
                element_description=state["element_description"],
                custom_prompt=state["current_prompt"],
                image_path=state.get("screenshot_path")
            )
            
            latency = (time.time() - start_time) * 1000
            
            if result.found:
                return {
                    "coordinates": (result.x, result.y),
                    "confidence": result.confidence,
                    "raw_output": result.reasoning,
                    "attempts": [{
                        "timestamp": datetime.now().isoformat(),
                        "coordinates": (result.x, result.y),
                        "confidence": result.confidence,
                        "method": "ui_tars_adaptive",
                        "latency_ms": latency
                    }]
                }
            else:
                return {
                    "coordinates": None,
                    "confidence": 0.0,
                    "raw_output": result.reasoning,
                    "error_message": "Element not found",
                    "attempts": [{
                        "timestamp": datetime.now().isoformat(),
                        "coordinates": None,
                        "confidence": 0.0,
                        "method": "ui_tars_adaptive",
                        "latency_ms": latency,
                        "error": "Not found"
                    }]
                }
                
        except Exception as e:
            logger.error(f"Vision locate error: {e}")
            return {
                "coordinates": None,
                "confidence": 0.0,
                "error_message": str(e),
                "attempts": [{
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                }]
            }
    
    def verify_node(state: VisionFeedbackState) -> Dict:
        """Verify the location seems valid."""
        coords = state.get("coordinates")
        confidence = state.get("confidence", 0.0)
        
        if not coords:
            return {"click_success": False, "verification_method": "no_coords"}
        
        # Basic bounds check
        x, y = coords
        # Get actual screen size from the system
        try:
            import subprocess
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=5
            )
            # Parse resolution like "Resolution: 3024 x 1964 Retina"
            import re
            match = re.search(r"Resolution:\s+(\d+)\s*x\s*(\d+)", result.stdout)
            if match:
                screen_w, screen_h = int(match.group(1)), int(match.group(2))
            else:
                screen_w, screen_h = 3000, 2000
        except Exception:
            screen_w, screen_h = 3000, 2000
        
        if x < 0 or y < 0 or x > screen_w or y > screen_h:
            return {"click_success": False, "verification_method": "out_of_bounds"}
        
        # Confidence threshold
        if confidence < 0.3:
            return {"click_success": None, "verification_method": "low_confidence"}
        
        return {"click_success": None, "verification_method": "passed_checks"}
    
    def feedback_node(state: VisionFeedbackState) -> Dict:
        """Record feedback and update memory."""
        success = state.get("click_success")
        
        if success is not None:
            memory.record_feedback(
                element_description=state["element_description"],
                success=success,
                prompt_used=state.get("current_prompt", ""),
                context=state.get("app_name", "")
            )
            
            logger.info(f"📝 Vision feedback recorded: {'✅ Success' if success else '❌ Failed'}")
        
        return {"attempt_count": state.get("attempt_count", 0) + 1}
    
    def retry_decision(state: VisionFeedbackState) -> str:
        """Decide whether to retry."""
        attempt_count = state.get("attempt_count", 0)
        max_attempts = state.get("max_attempts", 3)
        coords = state.get("coordinates")
        confidence = state.get("confidence", 0.0)
        
        # Don't retry if we succeeded
        if coords and confidence > 0.7:
            return "done"
        
        # Retry if we haven't exceeded max attempts
        if attempt_count < max_attempts:
            return "retry"
        
        return "done"
    
    # Build the graph
    graph = StateGraph(VisionFeedbackState)
    
    # Add nodes
    graph.add_node("prepare", prepare_node)
    graph.add_node("locate", locate_node)
    graph.add_node("verify", verify_node)
    graph.add_node("feedback", feedback_node)
    
    # Add edges
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "locate")
    graph.add_edge("locate", "verify")
    graph.add_edge("verify", "feedback")
    
    # Conditional edge for retry
    graph.add_conditional_edges(
        "feedback",
        retry_decision,
        {
            "retry": "prepare",
            "done": END
        }
    )
    
    return graph


# ============================================================================
# MAIN INTERFACE - AdaptiveVisionLocalizer
# ============================================================================

class AdaptiveVisionLocalizer:
    """
    Main interface for adaptive vision localization with feedback loop.
    
    This wraps the UI-TARS localizer with:
    - Learned prompts based on past successes
    - Memory of app-specific UI patterns
    - Automatic feedback recording
    - LangGraph-based retry logic
    """
    
    def __init__(
        self,
        memory_path: Optional[str] = None,
        checkpoint_path: Optional[str] = None,
        max_retries: int = 3
    ):
        self.memory = VisionMemory(memory_path)
        self.prompt_builder = AdaptivePromptBuilder(self.memory)
        self.max_retries = max_retries
        
        # Initialize base localizer
        from .local_vision_localizer import LocalVisionLocalizer, UITARSConfig
        
        config = UITARSConfig(
            model_path="mlx-community/UI-TARS-7B-SFT-4bit",
            max_tokens=512,  # More tokens for detailed output
            temperature=0.1,
            verbose=False
        )
        
        self._base_localizer = LocalVisionLocalizer(
            enable_apple_vision=True,
            enable_ui_tars=True,
            ui_tars_config=config,
            lazy_load_ui_tars=True
        )
        
        # Setup checkpointing
        if LANGGRAPH_AVAILABLE:
            if checkpoint_path:
                self._checkpointer = SqliteSaver.from_conn_string(checkpoint_path)
            else:
                self._checkpointer = MemorySaver()
            
            # Build the feedback graph
            self._graph = create_vision_feedback_graph(self.memory, self)
            self._app = self._graph.compile(checkpointer=self._checkpointer)
        else:
            self._app = None
    
    def find_element_with_prompt(
        self,
        element_description: str,
        custom_prompt: str,
        image_path: Optional[str] = None
    ):
        """Find element using a custom prompt."""
        from .local_vision_localizer import LocalizationResult
        
        # Get or take screenshot
        temp_screenshot = None
        if image_path is None:
            temp_screenshot = self._base_localizer.take_screenshot()
            image_path = temp_screenshot
        
        try:
            ui_tars = self._base_localizer._get_ui_tars()
            if not ui_tars:
                return LocalizationResult(found=False, reasoning="UI-TARS not available")
            
            # Use the custom prompt
            ui_tars._ensure_loaded()
            
            from mlx_vlm import generate
            
            output = generate(
                ui_tars.model,
                ui_tars.processor,
                custom_prompt,
                [image_path],
                max_tokens=ui_tars.config.max_tokens,
                temp=ui_tars.config.temperature,
                verbose=ui_tars.config.verbose
            )
            
            # Parse the output
            result = ui_tars._parse_coordinate_output(output, image_path)
            result.element_description = element_description
            result.method = "ui_tars_adaptive"
            result.reasoning = output[:200] if output else "No output"
            
            return result
            
        finally:
            if temp_screenshot:
                import os
                try:
                    os.remove(temp_screenshot)
                except:
                    pass
    
    def find_element(
        self,
        element_description: str,
        app_name: str = "",
        window_title: str = "",
        task_context: str = "",
        image_path: Optional[str] = None
    ) -> "LocalizationResult":
        """
        Find a UI element with adaptive prompting.
        
        Uses learned patterns and LangGraph feedback loop for
        improved accuracy over time.
        """
        from .local_vision_localizer import LocalizationResult
        
        # If LangGraph available, use the full feedback loop
        if self._app:
            initial_state = {
                "element_description": element_description,
                "task_context": task_context,
                "app_name": app_name,
                "screenshot_path": image_path,
                "current_prompt": "",
                "current_method": "",
                "coordinates": None,
                "confidence": 0.0,
                "raw_output": "",
                "click_success": None,
                "verification_method": "",
                "error_message": None,
                "attempt_count": 0,
                "max_attempts": self.max_retries,
                "should_retry": False,
                "attempts": [],
                "app_patterns": {},
                "element_patterns": {}
            }
            
            config = {"configurable": {"thread_id": f"vision_{hash(element_description)}"}}
            
            try:
                final_state = self._app.invoke(initial_state, config)
                
                if final_state.get("coordinates"):
                    x, y = final_state["coordinates"]
                    return LocalizationResult(
                        found=True,
                        x=x,
                        y=y,
                        confidence=final_state.get("confidence", 0.8),
                        method="adaptive_ui_tars",
                        element_description=element_description,
                        reasoning=final_state.get("raw_output", "")[:200]
                    )
                else:
                    return LocalizationResult(
                        found=False,
                        method="adaptive_ui_tars",
                        element_description=element_description,
                        reasoning=final_state.get("error_message", "Not found")
                    )
                    
            except Exception as e:
                logger.error(f"Adaptive vision failed: {e}")
        
        # Fallback to simple adaptive prompt
        prompt = self.prompt_builder.build_prompt(
            element_description=element_description,
            app_name=app_name,
            window_title=window_title,
            task_context=task_context
        )
        
        return self.find_element_with_prompt(element_description, prompt, image_path)
    
    def record_click_result(self, element_description: str, success: bool):
        """Record whether a click succeeded (for learning)."""
        self.memory.record_feedback(element_description, success)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics."""
        return {
            "apps_learned": len(self.memory._app_contexts),
            "patterns_learned": len(self.memory._element_patterns),
            "recent_attempts": len(self.memory._recent_attempts),
            "top_patterns": [
                {
                    "type": p.element_type,
                    "success_rate": p.success_rate,
                    "attempts": p.total_attempts
                }
                for p in sorted(
                    self.memory._element_patterns.values(),
                    key=lambda x: x.total_attempts,
                    reverse=True
                )[:10]
            ]
        }


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_adaptive_localizer: Optional[AdaptiveVisionLocalizer] = None


def get_adaptive_localizer() -> AdaptiveVisionLocalizer:
    """Get or create the global adaptive vision localizer."""
    global _adaptive_localizer
    
    if _adaptive_localizer is None:
        _adaptive_localizer = AdaptiveVisionLocalizer()
    
    return _adaptive_localizer
