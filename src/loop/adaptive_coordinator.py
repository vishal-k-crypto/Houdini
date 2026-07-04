"""
AdaptiveLoopCoordinator - New architecture with clear role separation.

Key Philosophy:
- Planner: Macro-level plans only (high-level task understanding)
- Executor: Takes macro + screen info → generates micro cursor instructions
- Supervisor: Handles randomness, guides executor, verifies completion, evolves tasks

The system is designed to:
1. Handle unpredictability gracefully
2. Evolve tasks in real-time based on screen state
3. Never get stuck - supervisor always has fallback control

UPDATED: Now uses event-driven waiting via macOS Accessibility Tree
instead of fixed time.sleep() calls for better reliability and speed.

UPDATED: Now logs all events to the Replay system for "Time Travel" debugging.
"""

import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from .loop_state import LoopState, LoopStatus, ActionRecord
from ..utils.logging import logger
from ..utils.ollama_client import OllamaClient
from ..providers.base import LLMProvider
from ..utils.schemas import (
    MacroPlanResponse, MicroActionsResponse, SupervisorGuidance as PydanticSupervisorGuidance,
    VerificationResult as PydanticVerificationResult, MicroAction as PydanticMicroAction,
    SupervisorDecision
)
from ..ui.thinking_window import (
    show_planner_thinking,
    show_executor_thinking,
    show_supervisor_thinking,
    show_thinking,
    set_window_status
)

# Import replay system for time travel debugging
try:
    from ..replay.execution_logger import get_execution_logger, ExecutionLogger
    REPLAY_AVAILABLE = True
except ImportError:
    REPLAY_AVAILABLE = False

# Import event-driven wait system
try:
    from ..utils.ui_wait import (
        get_ui_wait_system, wait_for_ui_stable, smart_wait,
        wait_for_element, wait_for_window_ready, UIWaitSystem
    )
    UI_WAIT_AVAILABLE = True
except ImportError:
    UI_WAIT_AVAILABLE = False
    logger.debug("Event-driven UI wait system not available, using fixed sleeps")

# Import probability model for flexible execution
try:
    from ..utils.probability_model import (
        get_probability_model,
        analyze_task_flexibility,
        get_flexible_execution_params,
        ExecutionFlexibility
    )
    PROBABILITY_MODEL_AVAILABLE = True
except ImportError:
    PROBABILITY_MODEL_AVAILABLE = False
    logger.debug("Probability model not available in coordinator")

# Import semantic checker for fast dual-path validation
try:
    from ..supervisor.semantic_checker import (
        SemanticChecker,
        get_semantic_checker,
        quick_semantic_check,
        SemanticCheckResult,
        SemanticMismatchType
    )
    SEMANTIC_CHECKER_AVAILABLE = True
except ImportError:
    SEMANTIC_CHECKER_AVAILABLE = False

# Import context memory for long-term file/resource learning
try:
    from ..utils.context_memory import (
        get_context_memory,
        learn_from_successful_task,
        resolve_task_context
    )
    CONTEXT_MEMORY_AVAILABLE = True
except ImportError:
    CONTEXT_MEMORY_AVAILABLE = False
    logger.debug("Context memory not available in coordinator")
    logger.debug("Semantic checker not available, using LLM-only validation")

# Import execution confidence model for action rating
try:
    from ..utils.execution_confidence import (
        rate_action,
        record_action_outcome,
        should_execute_action,
        ConfidenceRating,
        ActionDecision,
        ConfidenceLevel
    )
    CONFIDENCE_MODEL_AVAILABLE = True
except ImportError:
    CONFIDENCE_MODEL_AVAILABLE = False
    logger.debug("Execution confidence model not available")

# Import platform abstraction for cross-platform support
try:
    from ..platform.factory import get_platform, PlatformBundle
    PLATFORM_AVAILABLE = True
except ImportError:
    PLATFORM_AVAILABLE = False
    logger.debug("Platform abstraction not available, using direct macOS calls")

# Import fast executor for batched/speculative execution
try:
    from .fast_executor import FastExecutor, ExecutionResult
    FAST_EXECUTOR_AVAILABLE = True
except ImportError:
    FAST_EXECUTOR_AVAILABLE = False
    FastExecutor = None  # type: ignore
    ExecutionResult = None  # type: ignore
    logger.debug("Fast executor not available in coordinator")

# Import semantic cache for fast plan reuse
try:
    from ..utils.semantic_cache import lookup_plan, store_plan
    SEMANTIC_CACHE_AVAILABLE = True
except ImportError:
    SEMANTIC_CACHE_AVAILABLE = False
    lookup_plan = store_plan = None

# Import event bus for external listeners (API / dashboard)
try:
    from ..utils.event_bus import event_bus as _event_bus
except ImportError:
    _event_bus = None

# Import lesson store for automatic failure recording
try:
    from ..utils.lesson_store import lesson_store
    LESSON_STORE_AVAILABLE = True
except ImportError:
    LESSON_STORE_AVAILABLE = False
    logger.debug("Lesson store not available in coordinator")

# Import centralized config
try:
    from config.settings import settings as _settings
except ImportError:
    _settings = None

def _cfg(attr: str, fallback):
    """Get config value with fallback if config module unavailable."""
    if _settings is not None:
        return getattr(_settings, attr, fallback)
    return fallback


class AdaptivePhase(str, Enum):
    """Current phase of adaptive execution."""
    PLANNING = "planning"           # Initial macro planning
    EXECUTING = "executing"         # Executor generating/running micro actions  
    SUPERVISOR_GUIDE = "supervisor_guide"  # Supervisor guiding executor
    VERIFYING = "verifying"         # Verifying task completion
    EVOLVING = "evolving"           # Task evolution/replanning
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MacroPlan:
    """High-level macro plan from planner."""
    task: str
    macro_steps: List[Dict]  # [{step: "Open browser and go to X", context: "..."}, ...]
    expected_outcome: str
    success_criteria: str


@dataclass  
class MicroAction:
    """Low-level micro action from executor."""
    action_type: str  # "hotkey", "type", "click", "wait"
    params: Dict
    description: str
    requires_screen: bool = False


@dataclass
class ScreenContext:
    """Current screen state information."""
    app_name: str
    window_title: str
    visible_elements: List[Dict]
    screenshot_path: Optional[str] = None
    raw_accessibility_tree: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AdaptiveState:
    """State for adaptive execution with full context."""
    task: str
    phase: AdaptivePhase = AdaptivePhase.PLANNING
    
    # Planning state
    macro_plan: Optional[MacroPlan] = None
    current_macro_step_idx: int = 0
    
    # Execution state  
    pending_micro_actions: List[MicroAction] = field(default_factory=list)
    executed_actions: List[Dict] = field(default_factory=list)
    
    # Delayed Reward: Pending confidence outcomes (committed after verification)
    # Each entry: {"action_type": str, "params": dict, "rating": ConfidenceRating, "execution_time": float}
    pending_confidence_outcomes: List[Dict] = field(default_factory=list)
    
    # Screen context
    last_screen_context: Optional[ScreenContext] = None
    screen_context_history: List[ScreenContext] = field(default_factory=list)
    
    # Supervisor state
    supervisor_interventions: int = 0
    evolution_count: int = 0
    supervisor_notes: List[str] = field(default_factory=list)
    
    # Probability/Flexibility state (NEW)
    task_flexibility: Optional[Dict] = None  # Results from probability model
    execution_params: Optional[Dict] = None  # Dynamic params from probability model
    uncertainty_score: float = 0.0  # Overall uncertainty
    
    # Stuck detection state
    step_attempt_count: int = 0  # How many times current step has been attempted
    last_attempted_step_idx: int = -1  # Last step index that was attempted
    max_step_attempts: int = field(default_factory=lambda: _cfg("max_step_attempts", 5))  # Max attempts before forcing advancement
    
    # Evolution limits (prevent infinite evolution loops)
    max_evolution_attempts: int = field(default_factory=lambda: _cfg("max_evolution_attempts", 3))  # Max times supervisor can evolve task
    evolution_attempt_count: int = 0  # Current evolution attempts
    
    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AdaptiveLoopCoordinator:
    """
    New architecture with clear role separation:
    
    PLANNER (Macro):
    - Receives task, gives high-level plan
    - Example: "Open WhatsApp, find contact Kushal, send message"
    - Does NOT specify exact actions
    
    EXECUTOR (Micro):
    - Takes current macro step + screen info
    - Generates micro cursor instructions
    - Example: hotkey:cmd+space, type:WhatsApp, key:return
    - Asks supervisor when unsure
    
    SUPERVISOR (Adaptive):
    - Monitors for randomness/unexpected states
    - Guides executor when screen doesn't match expectations
    - Verifies task completion with screen analysis
    - Takes over planning if verification fails
    - Enables real-time task evolution
    """
    
    # DOM element for terminal display (optional)
    _terminal_display: Optional[Any] = None

    def __init__(self,
                 client: Union[OllamaClient, LLMProvider],
                 enable_thinking_window: bool = True,
                 max_iterations: int = None,
                 screen_capture_interval: float = 0.5):
        self.client = client
        self.enable_thinking_window = enable_thinking_window
        self.max_iterations = max_iterations or _cfg("max_iterations", 100)
        self.screen_capture_interval = screen_capture_interval
        
        # Platform abstraction (enables Linux/OSWorld support)
        self._platform: Optional[PlatformBundle] = None
        if PLATFORM_AVAILABLE:
            try:
                self._platform = get_platform()
                logger.info(f"AdaptiveCoordinator: Platform = {self._platform.name}")
            except Exception as e:
                logger.debug(f"Could not init platform bundle: {e}")
        
        # Current state
        self.state: Optional[AdaptiveState] = None
        self.running = False
        
        # Replay logger (set in execute)
        self._replay_logger: Optional[ExecutionLogger] = None
        
        # Event-driven wait system (initialized lazily)
        self._ui_wait: Optional[UIWaitSystem] = None
        if UI_WAIT_AVAILABLE:
            try:
                self._ui_wait = get_ui_wait_system()
                logger.debug("AdaptiveCoordinator: Event-driven UI wait system initialized")
            except Exception as e:
                logger.debug(f"Could not init UI wait system: {e}")

        # Fast executor for batched/speculative action execution (initialized lazily)
        self._fast_executor: Optional[FastExecutor] = None

    def _fast_exec(self) -> Optional[FastExecutor]:
        """Lazy initialize FastExecutor with this coordinator's vision handler."""
        if self._fast_executor is not None or not FAST_EXECUTOR_AVAILABLE:
            return self._fast_executor
        try:
            self._fast_executor = FastExecutor(
                vision_handler=self._vision_handler_for_fast_executor,
                enable_cache=True,
                enable_patterns=True,
                enable_confidence=CONFIDENCE_MODEL_AVAILABLE,
            )
            logger.debug("AdaptiveCoordinator: FastExecutor initialized")
        except Exception as e:
            logger.debug(f"Could not init FastExecutor: {e}")
        return self._fast_executor

    def _vision_handler_for_fast_executor(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Bridge FastExecutor vision actions to the existing vision executor."""
        try:
            from ..agents.vision_executor import execute_vision_action
            from ..utils.gemini_client import GeminiCLI
            cli = GeminiCLI()
            element = action.get("params", {}).get("element", "")
            result = execute_vision_action(
                cli,
                f"click: {element}",
                max_attempts=2,
                execution_params=self.state.execution_params if self.state else None,
            )
            return {
                "success": result.get("success", False),
                "error": result.get("error"),
                "coordinates": result.get("coordinates"),
                "method": result.get("method", "vision"),
            }
        except Exception as e:
            logger.error(f"FastExecutor vision bridge failed: {e}")
            return {"success": False, "error": str(e)}

    def _set_phase(self, new_phase: AdaptivePhase):
        """Set phase and log to replay system."""
        old_phase = self.state.phase if self.state else AdaptivePhase.PLANNING
        self.state.phase = new_phase
        
        # Log phase change to replay
        if self._replay_logger and self._replay_logger.current_session:
            self._replay_logger.log_phase_change(old_phase.value, new_phase.value)
        
    def execute(self, task: str, is_training: bool = False) -> Dict:
        """Execute a task using the adaptive architecture."""
        import uuid
        start_time = time.time()
        
        # Generate task ID
        task_id = str(uuid.uuid4())[:8]
        
        # Initialize state
        self.state = AdaptiveState(task=task)
        self.state.started_at = datetime.now()
        self.running = True
        
        # Start replay session for time travel debugging
        if REPLAY_AVAILABLE:
            try:
                self._replay_logger = get_execution_logger()
                self._replay_logger.start_session(
                    task_id=task_id,
                    task_description=task,
                    metadata={
                        "architecture": "adaptive_coordinator",
                    },
                    is_training=is_training
                )
                logger.debug("📼 Replay session started for time travel debugging")
            except Exception as e:
                logger.debug(f"Could not start replay session: {e}")
        
        logger.info(f"🎯 AdaptiveCoordinator starting: {task}")
        self._show("system", f"Task received: {task}", "info")
        
        # NEW: Analyze task flexibility with probability model
        if PROBABILITY_MODEL_AVAILABLE:
            self._analyze_task_flexibility(task)
        
        try:
            # PHASE 1: Macro Planning
            self._set_phase(AdaptivePhase.PLANNING)
            macro_plan = self._generate_macro_plan(task)
            
            if not macro_plan:
                return {"success": False, "error": "Macro planning failed"}
            
            self.state.macro_plan = macro_plan
            logger.info(f"📋 Macro plan: {len(macro_plan.macro_steps)} high-level steps")
            
            # PHASE 2: Adaptive Execution Loop
            iteration = 0
            while self.running and iteration < self.max_iterations:
                iteration += 1
                
                # Check if all macro steps complete
                if self.state.current_macro_step_idx >= len(macro_plan.macro_steps):
                    # PHASE 3: Verification
                    self._set_phase(AdaptivePhase.VERIFYING)
                    verification = self._supervisor_verify_completion()
                    
                    if verification["complete"]:
                        self._set_phase(AdaptivePhase.COMPLETED)
                        break
                    else:
                        # PHASE 4: Evolution - Supervisor takes over
                        self._set_phase(AdaptivePhase.EVOLVING)
                        evolved = self._supervisor_evolve_task(verification)
                        
                        if not evolved:
                            self._set_phase(AdaptivePhase.FAILED)
                            break
                        # Continue with evolved plan
                        continue
                
                # Get current macro step
                current_macro = macro_plan.macro_steps[self.state.current_macro_step_idx]
                step_desc = current_macro.get('step', 'Unknown')
                logger.info(f"\n▶️ Macro Step {self.state.current_macro_step_idx + 1}: {step_desc}")
                
                # ========== STUCK DETECTION ==========
                # Track step attempts to detect loops
                if self.state.current_macro_step_idx == self.state.last_attempted_step_idx:
                    self.state.step_attempt_count += 1
                else:
                    self.state.step_attempt_count = 1
                    self.state.last_attempted_step_idx = self.state.current_macro_step_idx
                
                # Check if stuck on same step too many times
                if self.state.step_attempt_count > self.state.max_step_attempts:
                    logger.warning(f"⚠️ Stuck on step {self.state.current_macro_step_idx + 1} after {self.state.step_attempt_count} attempts")
                    self._show("supervisor", f"⚠️ Step stuck after {self.state.step_attempt_count} attempts - checking if already done", "warning")
                    
                    # Check if step might already be complete
                    if self._verify_step_completion(current_macro):
                        logger.info(f"✅ Step was actually complete - advancing")
                        self._show("executor", f"✅ Step {self.state.current_macro_step_idx + 1} verified complete", "success")
                        self.state.current_macro_step_idx += 1
                        self.state.step_attempt_count = 0
                        continue
                    else:
                        # Force skip if truly stuck
                        logger.warning(f"⏭️ Forcing skip of stuck step")
                        self._show("supervisor", f"⏭️ Skipping stuck step to continue task", "warning")
                        self.state.supervisor_notes.append(f"Skipped stuck step: {step_desc}")
                        self.state.current_macro_step_idx += 1
                        self.state.step_attempt_count = 0
                        continue
                
                # EXECUTOR: Generate and execute micro actions
                self._set_phase(AdaptivePhase.EXECUTING)
                step_result = self._execute_macro_step(current_macro)
                
                if step_result.get("needs_supervisor"):
                    # Executor needs guidance
                    self._set_phase(AdaptivePhase.SUPERVISOR_GUIDE)
                    guidance = self._supervisor_guide_executor(
                        current_macro,
                        step_result.get("reason", "Unknown situation")
                    )
                    
                    if guidance.get("abort"):
                        self._set_phase(AdaptivePhase.FAILED)
                        break
                    elif guidance.get("skip"):
                        self.state.current_macro_step_idx += 1
                        self.state.step_attempt_count = 0
                        continue
                    elif guidance.get("new_actions"):
                        # Execute supervisor-provided actions
                        exec_success = self._execute_micro_actions(guidance["new_actions"])
                        
                        # After executing supervisor actions, check if step is now complete
                        if exec_success:
                            time.sleep(0.5)  # Wait for UI to settle
                            if self._verify_step_completion(current_macro):
                                self._show("executor", f"✅ Step {self.state.current_macro_step_idx + 1} complete (after guidance)", "success")
                                self.state.current_macro_step_idx += 1
                                self.state.step_attempt_count = 0
                                continue
                    
                if step_result.get("complete"):
                    self._show("executor", f"✅ Step {self.state.current_macro_step_idx + 1} complete", "success")
                    self.state.current_macro_step_idx += 1
                    self.state.step_attempt_count = 0
                
                # Event-driven wait between iterations instead of fixed sleep
                self._smart_wait_after("iteration")
            
            # Final result
            elapsed = time.time() - start_time
            self.state.completed_at = datetime.now()
            
            success = self.state.phase == AdaptivePhase.COMPLETED
            
            # Learn from successful task for context memory
            if success and CONTEXT_MEMORY_AVAILABLE:
                try:
                    # Extract action descriptions for learning
                    action_descriptions = [
                        a.get("description", str(a)) 
                        for a in self.state.executed_actions
                    ]
                    learn_from_successful_task(
                        task=task,
                        actions=action_descriptions,
                        context=None  # Could add file paths extracted during execution
                    )
                    logger.debug("📁 Context memory updated from successful task")
                except Exception as e:
                    logger.debug(f"Could not update context memory: {e}")
            
            # End replay session for time travel debugging
            if self._replay_logger and self._replay_logger.current_session:
                try:
                    error = None if success else f"Phase: {self.state.phase.value}"
                    self._replay_logger.end_session(success=success, error=error)
                    logger.debug("📼 Replay session saved for time travel debugging")
                except Exception as e:
                    logger.debug(f"Could not end replay session: {e}")
            
            return {
                "success": success,
                "elapsed": elapsed,
                "macro_steps_completed": self.state.current_macro_step_idx,
                "total_actions": len(self.state.executed_actions),
                "supervisor_interventions": self.state.supervisor_interventions,
                "evolution_count": self.state.evolution_count,
                "phase": self.state.phase.value,
                "uncertainty": self.state.uncertainty_score,
                "flexibility": self.state.task_flexibility,
            }
            
        except Exception as e:
            logger.error(f"❌ Adaptive execution error: {e}")
            import traceback
            traceback.print_exc()
            
            # Record failure to lesson store for learning
            if LESSON_STORE_AVAILABLE:
                try:
                    lesson_store.record_failure(
                        component="supervisor",
                        task=task,
                        error_type="execution_failure",
                        error_details=str(e)
                    )
                    logger.debug("📚 Failure recorded to lesson store")
                except Exception as lesson_err:
                    logger.debug(f"Could not record failure to lesson store: {lesson_err}")
            
            # End replay session on error
            if self._replay_logger and self._replay_logger.current_session:
                try:
                    self._replay_logger.end_session(success=False, error=str(e))
                except:
                    pass
            
            return {"success": False, "error": str(e)}
    
    # ========== PROBABILITY MODEL INTEGRATION ==========
    
    def _analyze_task_flexibility(self, task: str):
        """
        Analyze task using the probability model for flexible execution.
        
        This determines:
        - How complete the task specification is
        - Where it falls on the macro-micro spectrum
        - What the user's likely intent is
        - What execution parameters to use
        """
        try:
            flexibility = analyze_task_flexibility(task, context={
                'current_app': self._get_current_app_name(),
            })
            
            # Store in state
            self.state.uncertainty_score = flexibility.overall_uncertainty
            self.state.execution_params = get_flexible_execution_params(task)
            self.state.task_flexibility = {
                'completeness': flexibility.task_completeness.overall_score,
                'macro_micro_position': flexibility.macro_micro.position,
                'strategy': flexibility.macro_micro.execution_strategy,
                'intent': flexibility.intent.primary_intent,
                'intent_confidence': flexibility.intent.confidence,
                'ambiguity': flexibility.intent.ambiguity_score,
                'missing_info': flexibility.task_completeness.missing_info,
                'predicted_info': flexibility.task_completeness.predicted_info,
                'recommended_approach': flexibility.recommended_approach,
                'fallback_strategies': flexibility.fallback_strategies,
            }
            
            # Log analysis results
            logger.info(f"📊 Task Flexibility Analysis:")
            logger.info(f"   Completeness: {flexibility.task_completeness.overall_score:.0%}")
            logger.info(f"   Macro-Micro: {flexibility.macro_micro.position:.2f} ({flexibility.macro_micro.execution_strategy})")
            logger.info(f"   Intent: {flexibility.intent.primary_intent} ({flexibility.intent.confidence:.0%} confident)")
            logger.info(f"   Uncertainty: {flexibility.overall_uncertainty:.0%}")
            logger.info(f"   Approach: {flexibility.recommended_approach}")
            
            if flexibility.task_completeness.missing_info:
                logger.info(f"   Missing: {', '.join(flexibility.task_completeness.missing_info)}")
            
            if flexibility.task_completeness.predicted_info:
                logger.info(f"   Predicted: {flexibility.task_completeness.predicted_info}")
            
            # Show in thinking window
            self._show("system", 
                f"Task analysis: {flexibility.task_completeness.overall_score:.0%} complete, "
                f"{flexibility.intent.primary_intent} intent, "
                f"uncertainty: {flexibility.overall_uncertainty:.0%}",
                "info"
            )
            
        except Exception as e:
            logger.warning(f"Flexibility analysis failed: {e}")
            self.state.uncertainty_score = 0.5  # Default moderate uncertainty
            self.state.task_flexibility = None
    
    def _get_current_app_name(self) -> Optional[str]:
        """Get current frontmost app name (cross-platform)."""
        try:
            if self._platform:
                info = self._platform.accessibility.get_frontmost_app_info()
                return info.get("app")
            from ..utils.accessibility_reader import get_frontmost_app
            app_info = get_frontmost_app()
            return app_info.get('app')
        except:
            return None
    
    # ========== PLANNER: MACRO LEVEL ==========
    
    def _generate_macro_plan(self, task: str) -> Optional[MacroPlan]:
        """
        Generate a high-level macro plan.
        The planner ONLY provides macro understanding, NOT detailed actions.
        """
        self._show("planner", f"Analyzing task: {task}", "planning")
        
        # Include flexibility info in prompt if available
        flexibility_context = ""
        if self.state.task_flexibility:
            flex = self.state.task_flexibility
            flexibility_context = f"""
TASK ANALYSIS (from probability model):
- Completeness: {flex.get('completeness', 0):.0%} of information provided
- Predicted intent: {flex.get('intent', 'unknown')}
- Missing info: {', '.join(flex.get('missing_info', []))}
- Predicted info: {flex.get('predicted_info', {})}
- Recommended approach: {flex.get('recommended_approach', 'standard')}

Use this analysis to:
1. Fill in any missing information with reasonable defaults
2. Adjust planning granularity based on completeness
3. Add verification steps if uncertainty is high
"""
        
        # Get platform-specific context for Linux/Docker vs macOS
        try:
            from ..utils.platform_config import get_platform_prompt_context, PLATFORM_CONFIG, get_step_type_rules, get_example_prompts
            platform_context = get_platform_prompt_context()
            platform_name = PLATFORM_CONFIG.get("platform_name", "Unknown")
            step_type_rules = get_step_type_rules()
            example_prompts = get_example_prompts()
            hotkey_modifier = PLATFORM_CONFIG.get("hotkey_modifier", "command")
        except ImportError:
            platform_context = ""
            platform_name = "macOS"  # Default
            step_type_rules = """
### step_type: "blind" (keyboard-only, no vision needed):
- Opening apps: ["hotkey:command,space", "type:Safari", "key:return", "wait:2"]
- URL navigation: ["hotkey:command,l", "type:google.com", "key:return", "wait:2"]
- Keyboard shortcuts: ["hotkey:command,c"], ["hotkey:command,v"]
"""
            example_prompts = ""
            hotkey_modifier = "command"
        
        prompt = f"""You are a MACRO PLANNER using HYBRID PLANNING architecture.

CRITICAL ARCHITECTURE:
- You provide BOTH high-level steps AND concrete action sequences
- The executor uses your suggested_actions DIRECTLY without calling another LLM
- This makes execution FAST and DETERMINISTIC

{platform_context}
{flexibility_context}
TASK: {task}

## OUTPUT FORMAT (JSON):
{{
    "macro_steps": [
        {{
            "step": "High-level description",
            "context": "What should be visible after",
            "potential_issues": "What could go wrong",
            "step_type": "blind" or "vision",
            "suggested_actions": ["action1", "action2"]  // ⚠️ MANDATORY - executor uses these directly!
        }}
    ],
    "expected_outcome": "What success looks like",
    "success_criteria": "How to verify completion"
}}

## ACTION FORMAT:
- Hotkey: "hotkey:{hotkey_modifier},space" (comma-separated modifiers)
- Type text: "type:Hello World"
- Press key: "key:return" or "key:escape" or "key:tab"
- Wait: "wait:1.5" (seconds)
- Vision click: "click:description of element to click"
- Scroll: "scroll:down,3" or "scroll:up,5" (direction,amount)
- Drag: "drag:100,200,300,400" (start_x,start_y,end_x,end_y)
- Clipboard: "clipboard:copy" or "clipboard:paste" or "clipboard:cut" or "clipboard:select_all"

## STEP TYPE RULES:

{step_type_rules}

### step_type: "vision" (requires finding/clicking UI element):
- Website search boxes: ["click:search box at top of page"]
- Video thumbnails: ["click:first video thumbnail in the grid"]
- Buttons/Links: ["click:Submit button", "click:Sign In link"]
- CRITICAL: Be SPECIFIC about which element! Don't say "click search", say "click:search input field on the webpage"

{example_prompts}

⚠️ CRITICAL RULES:
1. EVERY step MUST have suggested_actions - the executor depends on them!
2. For vision steps, use "click:specific element description"
3. For blind steps, use concrete keyboard actions
4. Include "wait:X" after actions that need time to complete (app launches, page loads)
5. Be SPECIFIC in element descriptions - "first video thumbnail" not just "video"

Generate the macro plan for the task:"""
        
        try:
            # Show that we're waiting for LLM to plan
            self._show("planner", "⏳ Creating hybrid macro plan...", "thinking")
            
            response = self.client.generate_json(prompt, temperature=0.3)
            
            # Use Pydantic validation for macro plan response
            try:
                validated = MacroPlanResponse.model_validate(response)
                macro_steps = [step.model_dump() for step in validated.macro_steps]
                expected_outcome = validated.expected_outcome
                success_criteria = validated.success_criteria
            except Exception as validation_error:
                logger.warning(f"Pydantic validation failed, falling back: {validation_error}")
                macro_steps = response.get("macro_steps", [])
                expected_outcome = response.get("expected_outcome", "Task completed")
                success_criteria = response.get("success_criteria", "User goal achieved")
            
            if not macro_steps:
                raise ValueError("No macro steps generated")
            
            # HYBRID PLANNING VALIDATION: Ensure all steps have suggested_actions
            for i, step in enumerate(macro_steps):
                suggested = step.get("suggested_actions", [])
                if not suggested or len(suggested) == 0:
                    step_desc = step.get('step', f'Step {i+1}')
                    logger.warning(f"⚠️ HYBRID PLANNING: Step '{step_desc}' missing suggested_actions - execution will be slower!")
                    self._show("planner", f"⚠️ Step {i+1} missing actions - will need LLM fallback", "warning")
                else:
                    logger.info(f"✅ Step {i+1} has {len(suggested)} pre-planned actions (deterministic execution)")
            
            plan = MacroPlan(
                task=task,
                macro_steps=macro_steps,
                expected_outcome=expected_outcome,
                success_criteria=success_criteria
            )
            
            for i, step in enumerate(macro_steps, 1):
                step_desc = step.get('step', 'Unknown') if isinstance(step, dict) else str(step)
                step_type = step.get('step_type', 'blind') if isinstance(step, dict) else 'blind'
                action_count = len(step.get('suggested_actions', [])) if isinstance(step, dict) else 0
                self._show("planner", f"Step {i} [{step_type}]: {step_desc} ({action_count} actions)", "planning")
            
            return plan
            
        except Exception as e:
            logger.error(f"Macro planning failed: {e}")
            return None
    
    # ========== EXECUTOR: MICRO LEVEL ==========
    
    def _execute_macro_step(self, macro_step: Dict) -> Dict:
        """
        Executor takes a macro step + screen context and generates micro actions.
        If screen context doesn't match expectations, asks supervisor.
        
        DUAL-PATH VALIDATION:
        1. Fast path: Semantic checker (< 1ms) - catches obvious app/window mismatches
        2. Slow path: LLM analysis - only when fast path passes or is inconclusive
        """
        step_desc = macro_step.get("step", "Unknown step")
        expected_context = macro_step.get("context", "")
        
        # Clear status message for this step
        self._show("executor", f"━━━ Step: {step_desc} ━━━", "executing")
        
        # ========== FAST PATH: Semantic Check (no LLM) ==========
        # Re-enabled with fix: skip for app-launching steps where the whole
        # point of the step is to CHANGE the active app.
        step_lower = step_desc.lower()
        is_app_changing_step = any(kw in step_lower for kw in [
            "open ", "launch ", "start ", "activate ", "switch to ",
            "go to ", "navigate to ", "run ",
        ])
        
        if not is_app_changing_step:
            semantic_result = self._fast_semantic_check(macro_step)
            if semantic_result and semantic_result.should_interrupt:
                logger.warning(f"⚡ Semantic mismatch detected (fast path): {semantic_result.reason}")
                self._show("supervisor", f"⚡ Wrong app/window: {semantic_result.reason}", "warning")
                return {
                    "complete": False,
                    "needs_supervisor": True,
                    "reason": semantic_result.reason,
                    "semantic_mismatch": True,
                    "expected_app": semantic_result.expected,
                    "actual_app": semantic_result.actual
                }
        
        # ========== SLOW PATH: Full Screen Analysis ==========
        # Get current screen context
        screen_context = self._capture_screen_context()
        self.state.last_screen_context = screen_context
        self.state.screen_context_history.append(screen_context)
        
        # Generate micro actions based on macro step + screen
        micro_actions = self._generate_micro_actions(macro_step, screen_context)
        
        if not micro_actions:
            # Executor doesn't know what to do - ask supervisor
            return {
                "complete": False,
                "needs_supervisor": True,
                "reason": f"Cannot determine micro actions for: {step_desc}. Current app: {screen_context.app_name}"
            }
        
        # NOTE: We DON'T check expectations BEFORE execution for steps that
        # are meant to CHANGE the screen state (e.g., "open Safari" will
        # change from Terminal to Safari). The expectation check happens
        # AFTER action execution instead.
        
        # Execute the micro actions
        # OPTIMIZATION: Skip confidence gating for pre-planned actions (already validated by planner)
        has_preplanned_actions = bool(macro_step.get("suggested_actions"))
        success = self._execute_micro_actions(micro_actions, skip_confidence_gating=has_preplanned_actions)
        
        # Check expectations AFTER execution if we have expected context
        if success and expected_context:
            # Wait a bit for UI to settle
            time.sleep(0.3)
            
            # Capture fresh screen context after actions
            post_screen = self._capture_screen_context()
            
            # ========== CONNECTION ERROR DETECTION ==========
            # Check if browser shows "can't be reached" or similar errors
            # If so, attempt WARP VPN recovery
            if self._detect_connection_error(post_screen):
                logger.warning("🌐 Connection error detected after navigation")
                if self._handle_connection_error():
                    # Recovery successful, re-capture screen
                    post_screen = self._capture_screen_context()
                    logger.info("✅ Recovered from connection error via WARP")
                else:
                    logger.error("❌ WARP recovery failed")
                    return {"complete": False, "needs_supervisor": True, 
                            "reason": "Website unreachable - WARP recovery failed"}
            
            if not self._screen_matches_expectation(post_screen, expected_context):
                logger.warning(f"Post-execution screen doesn't match expectation: {expected_context}")
                
                # ========== ADAPTIVE RE-PLANNING ==========
                # Screen shows something unexpected (ad page, intermediate screen, etc.)
                # Instead of continuing blindly, re-plan from current state
                self._show("system", "⚠️ Unexpected screen - triggering adaptive re-plan", "warning")
                
                replan_result = self._adaptive_replan(
                    original_task=self.state.plan.task if hasattr(self.state, 'plan') and self.state.plan else "",
                    current_step=step_desc,
                    expected=expected_context,
                    actual_screen=post_screen,
                    remaining_steps=self.state.current_macro_step_index if hasattr(self.state, 'current_macro_step_index') else 0
                )
                
                if replan_result and replan_result.get("new_steps"):
                    # Insert new steps into the plan
                    logger.info(f"🔄 Re-plan generated {len(replan_result['new_steps'])} new steps")
                    self._show("system", f"🔄 Re-planning: {len(replan_result['new_steps'])} new steps to recover", "info")
                    return {"complete": True, "needs_replan": True, "new_steps": replan_result["new_steps"]}
                else:
                    # Just note it for supervisor (fallback)
                    self.state.supervisor_notes.append(
                        f"Step '{step_desc}' executed but screen shows {post_screen.app_name} "
                        f"instead of expected '{expected_context}'"
                    )
        
        return {"complete": success, "needs_supervisor": not success}
    
    def _fast_semantic_check(self, macro_step: Dict) -> Optional['SemanticCheckResult']:
        """
        Fast semantic validation without LLM calls.
        
        Uses the semantic checker to compare:
        - Expected app (extracted from step description)
        - Actual app (from accessibility tree)
        
        Returns None if semantic checking is not available.
        """
        if not SEMANTIC_CHECKER_AVAILABLE:
            return None
        
        try:
            checker = get_semantic_checker()
            result = checker.check_state_match(macro_step)
            
            if result.mismatch_type != SemanticMismatchType.NONE:
                logger.debug(f"Semantic check: {result.mismatch_type.value} - {result.reason}")
            
            return result
        except Exception as e:
            logger.debug(f"Semantic check failed: {e}")
            return None
    
    def _generate_micro_actions(self, macro_step: Dict, screen: ScreenContext) -> List[MicroAction]:
        """
        Generate specific micro actions based on macro step and current screen.
        IMPROVEMENT: Use suggested_actions from planner if available, reducing LLM calls.
        """
        step_desc = macro_step.get("step", "")
        app_name = screen.app_name.lower()
        
        # NEW: Check if planner provided suggested actions (avoid LLM call)
        suggested_actions = macro_step.get("suggested_actions", [])
        if suggested_actions and len(suggested_actions) > 0:
            logger.info(f"✅ Using {len(suggested_actions)} suggested actions from planner (no LLM call needed)")
            self._show("executor", f"✅ Using pre-planned actions ({len(suggested_actions)} actions)", "info")
            
            # Use robust action parser to handle format variations
            from ..utils.action_parser import parse_actions
            parsed = parse_actions(suggested_actions)
            
            micro_actions = []
            for p in parsed:
                micro_actions.append(MicroAction(
                    action_type=p["type"],
                    params=p.get("params", {}),
                    description=p.get("description", ""),
                    requires_screen=p.get("requires_screen", False),
                ))
            
            if micro_actions:
                return micro_actions
        
        # Fallback: Generate with LLM (only if no suggestions provided)
        self._show("executor", f"🧠 Generating actions with LLM: {step_desc[:50]}...", "thinking")
        logger.warning("⚠️ No suggested_actions from planner, calling LLM (slower)")
        
        # Build context for micro action generation
        elements_summary = self._summarize_elements(screen.visible_elements[:20])
        
        # Show current context
        self._show("executor", f"📍 Current app: {screen.app_name} | Window: {screen.window_title[:40]}", "info")
        
        # Check if this is a vision step (requires clicking UI elements)
        step_type = macro_step.get("step_type", "blind")
        is_vision_step = step_type == "vision" or "click" in step_desc.lower() or "find" in step_desc.lower()
        
        prompt = f"""You are a MICRO EXECUTOR. Generate actions to accomplish this step.

MACRO STEP: {macro_step.get('step')}
STEP TYPE: {step_type}
CURRENT APP: {screen.app_name}
WINDOW: {screen.window_title}
VISIBLE ELEMENTS (sample): {elements_summary}

## ACTION TYPES (in order of preference):

{"### VISION STEP - Use CLICK to find and interact with UI elements:" if is_vision_step else "### BLIND STEP - Use keyboard actions:"}

1. **click**: Find and click a UI element using VISION (HUMAN-LIKE - cursor moves to element)
   {{"type": "click", "params": {{"element": "search box"}}, "description": "Click search box"}}
   Use this for: buttons, links, search fields, videos, any clickable UI element
   
2. **type**: Type text into focused field
   {{"type": "type", "params": {{"text": "query"}}, "description": "Type search query"}}
   
3. **key**: Press single key
   {{"type": "key", "params": {{"key": "return"}}, "description": "Submit"}}
   
4. **hotkey**: Press keyboard shortcut (ONLY for system actions)
   {{"type": "hotkey", "params": {{"keys": ["command", "space"]}}, "description": "Open Spotlight"}}
   Use ONLY for: Spotlight (Cmd+Space), Copy (Cmd+C), Paste (Cmd+V), New Tab (Cmd+T), URL bar (Cmd+L)

5. **wait**: Wait for UI to load
   {{"type": "wait", "params": {{"seconds": 1.5}}, "description": "Wait for page"}}

Output JSON:
{{
    "actions": [...],
    "requires_screen_check": true,
    "confidence": 0.9
}}

## CRITICAL RULES:
1. For VISION steps: Use "click" action to find UI elements - the system will use vision to locate them
2. For website interactions: ALWAYS use click, NEVER use hotkeys for website search/buttons
3. For opening apps: Use Spotlight (hotkey:command,space + type + key:return)
4. Be SPECIFIC in element descriptions: "search box at top of page" not just "search"

Generate actions:"""

        try:
            # Show that we're waiting for LLM
            self._show("executor", "⏳ Planning actions...", "thinking")
            llm_start = time.time()
            
            response = self.client.generate_json(prompt, temperature=0.2)
            
            llm_duration = time.time() - llm_start
            logger.debug(f"LLM micro-action generation took {llm_duration:.1f}s")
            
            # Use Pydantic validation for micro actions
            try:
                validated = MicroActionsResponse.model_validate(response)
                confidence = validated.confidence
                
                if confidence < 0.5:
                    logger.warning(f"Low confidence ({confidence:.0%}) for micro actions")
                    return []
                
                micro_actions = []
                for a in validated.actions:
                    micro_actions.append(MicroAction(
                        action_type=a.type,
                        params=a.params.model_dump() if a.params else {},
                        description=a.description,
                        requires_screen=a.requires_screen
                    ))
            except Exception as validation_error:
                logger.warning(f"Pydantic validation failed for micro actions: {validation_error}")
                # Fallback to legacy parsing
                actions = response.get("actions", [])
                confidence = response.get("confidence", 0.5)
                
                if confidence < 0.5:
                    logger.warning(f"Low confidence ({confidence:.0%}) for micro actions")
                    return []
                
                micro_actions = []
                for a in actions:
                    micro_actions.append(MicroAction(
                        action_type=a.get("type", "unknown"),
                        params=a.get("params", {}),
                        description=a.get("description", ""),
                        requires_screen=a.get("requires_screen", False)
                    ))
            
            # Don't show all actions upfront - show them when executing
            # This prevents the "thinking ahead of execution" disconnect
            # But DO show a brief summary so user knows what will happen
            action_types = [ma.action_type for ma in micro_actions]
            action_summary = f"✓ Plan ready: {len(micro_actions)} actions ({', '.join(action_types[:3])}{'...' if len(action_types) > 3 else ''})"
            self._show("executor", action_summary, "success")
            
            return micro_actions
            
        except Exception as e:
            logger.error(f"Micro action generation failed: {e}")
            return []
    
    def _execute_micro_actions(self, actions: List[MicroAction], skip_confidence_gating: bool = False) -> bool:
        """Execute a list of micro actions with event-driven waiting and verification."""
        import pyautogui
        from ..utils.accessibility_reader import get_frontmost_app
        
        # Verify pyautogui is working
        try:
            # Test if we can get mouse position (requires accessibility permissions)
            pos = pyautogui.position()
            logger.debug(f"PyAutoGUI initialized, cursor at: {pos}")
        except Exception as e:
            logger.error(f"❌ PyAutoGUI not working: {e}")
            logger.error("Please grant accessibility permissions to Terminal/iTerm in System Settings > Privacy & Security > Accessibility")
            self._show("executor", "❌ Accessibility permissions required!", "error")
            return False
        
        # Track expected app context for verification
        expected_app = None
        last_activated_app = None
        
        total_actions = len(actions)
        for action_idx, action in enumerate(actions, 1):
            start_time = time.time()
            try:
                # Show what we're about to do FIRST (before any checks)
                action_label = f"[{action_idx}/{total_actions}] {action.action_type}: {action.description}"
                self._show("executor", f"▶ {action_label}", "action")
                
                # ========== CONFIDENCE GATING ==========
                # Rate action before execution using the confidence model
                # OPTIMIZATION: Skip for pre-planned actions (already validated by planner)
                # This matches the working behavior from the 3:33am session.
                
                rating = None
                checkpoint_needed = False
                
                if skip_confidence_gating:
                    # Pre-planned actions from planner - execute directly without rating
                    pass  # No confidence check needed
                elif CONFIDENCE_MODEL_AVAILABLE:
                    context = {
                        "current_app": self._get_current_app_name(),
                        "screen_active": True,
                    }
                    rating = rate_action(
                        action.action_type,
                        action.params,
                        context=context
                    )
                    
                    logger.info(f"📊 Action confidence: {rating.score:.1f}/10 ({rating.level.value})")
                    
                    # Emit to event bus for API / dashboard observers
                    if _event_bus:
                        _event_bus.emit("confidence", {
                            "score": rating.score,
                            "level": rating.level.value,
                            "decision": rating.decision.value,
                            "action": action.description,
                            "action_type": action.action_type,
                        })

                    # TIER 1: HIGH/CRITICAL (7-10) - Execute immediately
                    if rating.score >= 7.0:
                        self._show("executor", f"✅ High confidence ({rating.score:.1f}) - executing", "success")
                        # Proceed with execution below
                    
                    # TIER 2: MODERATE (5-6.9) - Execute with checkpoint for rollback
                    elif rating.score >= 5.0:
                        self._show("executor", f"⚡ Moderate confidence ({rating.score:.1f}) - executing with checkpoint", "info")
                        checkpoint_needed = True
                        # Store checkpoint state for potential rollback
                        self.state.supervisor_notes.append(
                            f"Checkpoint: {action.description} (confidence: {rating.score:.1f})"
                        )
                        # Proceed with execution below
                    
                    # TIER 3: LOW (3-4.9) - Gather more context first
                    elif rating.score >= 3.0:
                        logger.warning(f"⚠️ Low confidence ({rating.score:.1f}), gathering more context")
                        self._show("executor", f"🔍 Low confidence ({rating.score:.1f}) - gathering context", "warning")
                        
                        # Capture fresh screenshot for better understanding
                        time.sleep(0.3)
                        fresh_context = self._capture_screen_context()
                        self.state.last_screen_context = fresh_context
                        
                        # Re-rate with fresh context
                        context["fresh_screen"] = True
                        context["visible_elements"] = len(fresh_context.visible_elements)
                        rating = rate_action(action.action_type, action.params, context=context)
                        
                        if rating.score >= 4.0:
                            self._show("executor", f"📸 Re-rated: {rating.score:.1f} - proceeding", "info")
                            checkpoint_needed = True
                        else:
                            self._show("executor", f"⚠️ Still low confidence - deferring", "warning")
                            self.state.executed_actions.append({
                                "type": action.action_type,
                                "params": action.params,
                                "description": action.description,
                                "timestamp": datetime.now().isoformat(),
                                "confidence_score": rating.score,
                                "deferred": True,
                                "reason": "low_confidence_after_context"
                            })
                            return False  # Trigger supervisor guidance
                    
                    # TIER 4: VERY_LOW/UNCERTAIN (0-2.9) - Defer to supervisor
                    else:
                        logger.warning(f"⚠️ Very low confidence ({rating.score:.1f}), deferring to supervisor")
                        self._show("executor", f"🛑 Very low confidence ({rating.score:.1f}) - needs supervisor", "warning")
                        self.state.executed_actions.append({
                            "type": action.action_type,
                            "params": action.params,
                            "description": action.description,
                            "timestamp": datetime.now().isoformat(),
                            "confidence_score": rating.score,
                            "deferred": True,
                            "reason": "very_low_confidence"
                        })
                        return False  # Will trigger supervisor guidance
                
                # Capture screenshot BEFORE action for state representation
                screenshot_path = None
                if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                    screenshot_path = self._replay_logger.log_screenshot_auto(trigger="pre_action", description=f"Before: {action.description}")
                
                # Log action start to replay system with screenshot
                if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                    self._replay_logger.log_action(action.description, action.action_type, screenshot_path=screenshot_path)
                
                # DEBUG: Log that we're about to execute
                logger.debug(f"Executing action type: {action.action_type} with params: {action.params}")
                
                if action.action_type == "hotkey":
                    keys = action.params.get("keys", [])
                    logger.debug(f"Pressing hotkey: {keys}")
                    
                    # Special handling for app-launching hotkeys (like Cmd+Space for Spotlight)
                    is_spotlight = keys == ["command", "space"] or keys == ["cmd", "space"]
                    
                    pyautogui.hotkey(*keys)
                    logger.debug(f"Hotkey pressed: {keys}")
                    self._smart_wait_after("hotkey")
                    
                    # After spotlight, expect to type app name next
                    if is_spotlight:
                        time.sleep(0.3)  # Extra wait for Spotlight to appear
                    
                    # Log hotkey to replay
                    if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                        self._replay_logger.log_hotkey(keys)
                    
                elif action.action_type == "type":
                    text = action.params.get("text", "")
                    logger.debug(f"Typing text: {text}")
                    
                    # CRITICAL: Verify we're typing in the right place before sending keystrokes
                    current_app = get_frontmost_app()
                    current_app_name = current_app.get("app", "").lower()
                    
                    # If we just launched an app, verify it's now active
                    if last_activated_app and last_activated_app.lower() not in current_app_name:
                        logger.warning(f"⚠️ App mismatch before typing: expected {last_activated_app}, got {current_app_name}")
                        # Try to activate the expected app
                        self._activate_app(last_activated_app)
                        time.sleep(0.5)
                        # Re-check
                        current_app = get_frontmost_app()
                        current_app_name = current_app.get("app", "").lower()
                        if last_activated_app.lower() not in current_app_name:
                            logger.error(f"❌ Failed to activate {last_activated_app}, current: {current_app_name}")
                            return False
                    
                    # Use typewrite for ASCII text (more reliable than write)
                    pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text, interval=0.02)
                    self._smart_wait_after("type")
                    
                    # Log text typing to replay
                    if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                        self._replay_logger.log_text_type(text)
                    
                elif action.action_type == "key":
                    key = action.params.get("key", "")
                    
                    # If pressing return after typing app name, track which app we're launching
                    if key.lower() in ["return", "enter"]:
                        # Check if previous action was typing an app name
                        desc_lower = action.description.lower()
                        if "launch" in desc_lower or "app" in desc_lower or "safari" in desc_lower or "chrome" in desc_lower:
                            # Extract app name from previous type action or description
                            for prev in reversed(self.state.executed_actions[-5:]):
                                if prev.get("type") == "type":
                                    last_activated_app = prev.get("params", {}).get("text", "")
                                    break
                    
                    pyautogui.press(key)
                    self._smart_wait_after("key")
                    
                    # After pressing return to launch app, wait for it to activate
                    if key.lower() in ["return", "enter"] and last_activated_app:
                        logger.info(f"⏳ Waiting for {last_activated_app} to activate...")
                        self._wait_for_app_activation(last_activated_app, timeout=3.0)
                    
                    # Log key press to replay
                    if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                        self._replay_logger.log_key_press(key)
                    
                elif action.action_type == "wait":
                    secs = action.params.get("seconds")
                    
                    # FIX: Handle None seconds - try to extract from description or default
                    if secs is None:
                        # Try to extract duration from description like "Wait 3s" or "Wait for 2 seconds"
                        import re
                        desc = action.description.lower()
                        match = re.search(r'(\d+(?:\.\d+)?)\s*(?:s|sec|second)', desc)
                        if match:
                            secs = float(match.group(1))
                            logger.debug(f"Extracted wait duration from description: {secs}s")
                        else:
                            # Smart default based on context
                            if any(word in desc for word in ['page', 'load', 'content', 'dynamic']):
                                secs = 2.0  # Longer wait for page loads
                            elif any(word in desc for word in ['spotlight', 'app', 'open']):
                                secs = 0.5  # Quick wait for app switching
                            else:
                                secs = 1.0  # Reasonable default
                            logger.debug(f"Using context-based wait duration: {secs}s")
                    
                    # FIX: Always wait AT LEAST the specified duration
                    # Previously, smart wait would exit early when UI appeared stable,
                    # causing "Wait 2s" to complete in ~1.1s
                    start_wait = time.time()
                    time.sleep(secs)  # Guaranteed minimum wait
                    actual_wait = time.time() - start_wait
                    logger.debug(f"Wait action: requested {secs}s, actual {actual_wait:.1f}s")
                    
                elif action.action_type == "click":
                    # Use vision executor for click actions
                    element_desc = action.params.get("element", action.description)
                    click_result = self._vision_click(element_desc)
                    if not click_result.get("success"):
                        logger.warning(f"Click failed: {click_result.get('error')}")
                        # Log failure to replay
                        if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                            duration_ms = (time.time() - start_time) * 1000
                            self._replay_logger.log_action_complete(action.description, False, duration_ms, click_result.get('error'))
                        return False
                    self._smart_wait_after("click")
                
                elif action.action_type == "open_url":
                    # RELIABLE URL opening using AppleScript - avoids typing issues
                    url = action.params.get("url", "")
                    browser = action.params.get("browser", "Safari")
                    
                    if url:
                        success = self._open_url_in_browser(url, browser)
                        if not success:
                            logger.warning(f"Failed to open URL: {url}")
                            return False
                        self._smart_wait_after("click")  # Same wait as click for page load
                
                elif action.action_type == "activate_app":
                    # Direct app activation using AppleScript
                    app_name = action.params.get("app", "")
                    if app_name:
                        success = self._activate_app(app_name)
                        if success:
                            self._wait_for_app_activation(app_name, timeout=2.0)
                        else:
                            logger.warning(f"Failed to activate app: {app_name}")
                            return False
                
                elif action.action_type == "scroll":
                    # Scroll in the specified direction
                    direction = action.params.get("direction", "down").lower()
                    amount = action.params.get("amount", 3)
                    
                    if direction in ("down", "d"):
                        pyautogui.scroll(-amount)
                    elif direction in ("up", "u"):
                        pyautogui.scroll(amount)
                    elif direction in ("left", "l"):
                        pyautogui.hscroll(-amount)
                    elif direction in ("right", "r"):
                        pyautogui.hscroll(amount)
                    
                    logger.debug(f"Scrolled {direction} by {amount}")
                    self._smart_wait_after("click")
                
                elif action.action_type == "drag":
                    # Drag from (start_x,start_y) to (end_x,end_y)
                    sx = action.params.get("start_x")
                    sy = action.params.get("start_y")
                    ex = action.params.get("end_x")
                    ey = action.params.get("end_y")
                    
                    if all(v is not None for v in (sx, sy, ex, ey)):
                        pyautogui.moveTo(sx, sy, duration=0.15)
                        time.sleep(0.05)
                        pyautogui.mouseDown()
                        time.sleep(0.05)
                        pyautogui.moveTo(ex, ey, duration=0.3)
                        time.sleep(0.05)
                        pyautogui.mouseUp()
                        logger.debug(f"Dragged ({sx},{sy}) → ({ex},{ey})")
                    else:
                        # Drag described by element names — use vision to find coordinates
                        desc = action.params.get("description", action.description)
                        logger.warning(f"Drag by description not yet supported: {desc}")
                    self._smart_wait_after("click")
                
                elif action.action_type == "clipboard":
                    # Clipboard operations: copy, cut, paste, select_all
                    op = action.params.get("operation", "paste").lower()
                    # Determine modifier key based on platform
                    mod = "ctrl" if (self._platform and self._platform.name == "linux") else "command"
                    
                    if op == "copy":
                        pyautogui.hotkey(mod, "c")
                    elif op == "cut":
                        pyautogui.hotkey(mod, "x")
                    elif op == "paste":
                        pyautogui.hotkey(mod, "v")
                    elif op == "select_all":
                        pyautogui.hotkey(mod, "a")
                    
                    logger.debug(f"Clipboard: {op}")
                    self._smart_wait_after("hotkey")
                
                # Record action
                duration_ms = (time.time() - start_time) * 1000
                self.state.executed_actions.append({
                    "type": action.action_type,
                    "params": action.params,
                    "description": action.description,
                    "timestamp": datetime.now().isoformat(),
                    "confidence_score": rating.score if rating else None,
                    "success": True,
                    "duration_ms": duration_ms,
                    "checkpoint": checkpoint_needed
                })
                
                # Show completion in thinking window
                self._show("executor", f"✓ Done ({duration_ms:.0f}ms)", "success")
                
                # ========== CHECKPOINT VERIFICATION ==========
                # For moderate-confidence actions, verify the result
                if checkpoint_needed and rating:
                    time.sleep(0.2)  # Brief pause for UI to settle
                    
                    # Quick screen check to verify action had expected effect
                    post_app = self._get_current_app_name()
                    if post_app:
                        # Check if we're still in a reasonable state
                        # (e.g., didn't accidentally close the app or switch away)
                        pre_app = context.get("current_app", "")
                        if pre_app and post_app.lower() != pre_app.lower():
                            # App changed unexpectedly - flag for supervisor
                            logger.warning(f"⚠️ Checkpoint: App changed from {pre_app} to {post_app}")
                            self.state.supervisor_notes.append(
                                f"Checkpoint alert: App changed after '{action.description}'"
                            )
                
                # DELAYED REWARD: Store pending outcome for later commitment
                # Don't record outcome yet - wait for Supervisor/Verifier to confirm
                # This prevents reward poisoning from "successful" clicks on wrong elements
                if CONFIDENCE_MODEL_AVAILABLE and rating:
                    self.state.pending_confidence_outcomes.append({
                        "action_type": action.action_type,
                        "action_params": action.params,
                        "rating": rating,
                        "execution_time": time.time() - start_time,
                        "context": {"app": self._get_current_app_name()},
                        "checkpoint_verified": checkpoint_needed
                    })
                
                # Log action completion to replay
                if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                    duration_ms = (time.time() - start_time) * 1000
                    self._replay_logger.log_action_complete(action.description, True, duration_ms)
                
            except Exception as e:
                logger.error(f"Micro action failed: {action.description} - {e}")
                
                # Immediate failure IS a valid signal - record it now
                # (pyautogui threw an exception, so the action truly failed)
                if CONFIDENCE_MODEL_AVAILABLE and rating:
                    try:
                        record_action_outcome(
                            action_type=action.action_type,
                            action_params=action.params,
                            rating=rating,
                            success=False,
                            execution_time=time.time() - start_time,
                            context={"app": self._get_current_app_name()},
                            error_type=type(e).__name__
                        )
                    except Exception as outcome_err:
                        logger.debug(f"Could not record failed action outcome: {outcome_err}")
                
                # Log failure to replay
                if hasattr(self, '_replay_logger') and self._replay_logger and self._replay_logger.current_session:
                    duration_ms = (time.time() - start_time) * 1000
                    self._replay_logger.log_action_complete(action.description, False, duration_ms, str(e))
                return False
        
        return True
    
    def _smart_wait_after(self, action_type: str):
        """
        Event-driven wait after an action completes.
        Uses UI stability detection instead of fixed sleep.
        """
        if self._ui_wait:
            try:
                result = self._ui_wait.smart_wait_after_action(action_type)
                logger.debug(f"Post-{action_type} wait: {result.waited_ms:.0f}ms")
            except Exception as e:
                logger.debug(f"Smart wait failed, using fallback: {e}")
                time.sleep(0.1)
        else:
            # Fallback to fixed sleeps
            if action_type == "type":
                time.sleep(0.05)
            elif action_type == "click":
                time.sleep(0.15)
            else:
                time.sleep(0.1)
    
    def _activate_app(self, app_name: str) -> bool:
        """
        Activate an application (cross-platform).
        Uses AppleScript on macOS, wmctrl/xdotool on Linux.
        """
        import subprocess
        
        logger.info(f"🚀 Activating app: {app_name}")
        clean_name = app_name.strip()
        
        # Detect platform
        is_linux = self._platform and self._platform.name == "linux"
        
        if is_linux:
            # Linux: use wmctrl or xdotool
            try:
                # Try wmctrl first
                result = subprocess.run(
                    ["wmctrl", "-a", clean_name],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    logger.info(f"✅ Activated {clean_name} via wmctrl")
                    return True
            except FileNotFoundError:
                pass
            
            try:
                # Fallback: xdotool
                result = subprocess.run(
                    ["xdotool", "search", "--name", clean_name, "windowactivate"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    logger.info(f"✅ Activated {clean_name} via xdotool")
                    return True
            except FileNotFoundError:
                pass
            
            logger.warning(f"⚠️ Could not activate {clean_name} on Linux (no wmctrl/xdotool)")
            return False
        
        # macOS: AppleScript
        app_mappings = {
            "safari": "Safari",
            "chrome": "Google Chrome",
            "firefox": "Firefox",
            "terminal": "Terminal",
            "finder": "Finder",
            "youtube": "Safari",
        }
        
        actual_app = app_mappings.get(clean_name.lower(), clean_name)
        
        try:
            script = f'tell application "{actual_app}" to activate'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.info(f"✅ Activated {actual_app}")
                return True
            else:
                logger.warning(f"⚠️ Failed to activate {actual_app}: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"❌ App activation error: {e}")
            return False
    
    def _wait_for_app_activation(self, app_name: str, timeout: float = 3.0) -> bool:
        """
        Wait for an app to become the frontmost application.
        
        CRITICAL FIX: Uses event-driven waiting from ui_wait.py instead of
        polling with fixed sleeps. This ensures the agent properly waits
        for the app to become active before trying to interact with it.
        
        Returns True if app is activated within timeout.
        """
        # Try event-driven wait first (more reliable)
        if self._ui_wait:
            try:
                result = self._ui_wait.wait_for_app_focus(
                    app_name=app_name,
                    timeout_ms=int(timeout * 1000),
                    check_window=True
                )
                if result.success:
                    logger.info(f"✅ {app_name} is now active (waited {result.waited_ms:.0f}ms)")
                    # Extra stabilization wait after app activates
                    time.sleep(0.2)
                    return True
                else:
                    logger.warning(f"⏱️ {result.reason}")
                    return False
            except Exception as e:
                logger.debug(f"Event-driven wait failed: {e}, falling back to polling")
        
        # Fallback to polling-based wait
        from ..utils.accessibility_reader import get_frontmost_app
        
        clean_name = app_name.lower().strip()
        start = time.time()
        
        while time.time() - start < timeout:
            current = get_frontmost_app()
            current_app = current.get("app", "").lower()
            
            # Check if the expected app is now active
            if clean_name in current_app or current_app in clean_name:
                logger.info(f"✅ {app_name} is now active")
                return True
            
            # Special case: if we launched Safari, also check for the app being responsive
            if "safari" in clean_name and "safari" in current_app:
                logger.info(f"✅ Safari is now active")
                return True
            
            time.sleep(0.1)  # Faster polling
        
        logger.warning(f"⏱️ Timeout waiting for {app_name} to activate (last: {current.get('app', 'Unknown')})")
        return False
    
    def _verify_ready_for_input(self, expected_context: str = "") -> bool:
        """
        Verify the current screen state is ready for input.
        Checks for focused text fields, active windows, etc.
        """
        from ..utils.accessibility_reader import get_frontmost_app
        
        current = get_frontmost_app()
        app_name = current.get("app", "")
        window = current.get("window", "")
        
        # Basic check: we have an app and window
        if not app_name:
            logger.warning("No active application detected")
            return False
        
        # If we have an expected context, check it
        if expected_context:
            context_lower = expected_context.lower()
            if app_name.lower() not in context_lower and context_lower not in app_name.lower():
                logger.warning(f"App mismatch: expected context '{expected_context}', got '{app_name}'")
                return False
        
        return True
    
    def _open_url_in_browser(self, url: str, browser: str = "Safari") -> bool:
        """
        Open a URL in a browser (cross-platform).
        Uses AppleScript on macOS, xdg-open on Linux.
        """
        import subprocess
        
        logger.info(f"🌐 Opening URL: {url} in {browser}")
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        is_linux = self._platform and self._platform.name == "linux"
        
        if is_linux:
            try:
                subprocess.run(["xdg-open", url], check=True, timeout=10)
                logger.info(f"✅ Opened URL via xdg-open")
                time.sleep(1.0)
                return True
            except Exception as e:
                logger.warning(f"xdg-open failed: {e}")
                # Fallback: try chromium/firefox directly
                for cmd in ["chromium", "chromium-browser", "google-chrome", "firefox"]:
                    try:
                        subprocess.Popen([cmd, url])
                        logger.info(f"✅ Opened URL via {cmd}")
                        time.sleep(1.0)
                        return True
                    except FileNotFoundError:
                        continue
                return False
        
        # macOS: AppleScript
        browser_lower = browser.lower()
        
        try:
            if "safari" in browser_lower:
                script = f'''
                tell application "Safari"
                    activate
                    if (count of windows) = 0 then
                        make new document
                    end if
                    set URL of current tab of front window to "{url}"
                end tell
                '''
            elif "chrome" in browser_lower:
                script = f'''
                tell application "Google Chrome"
                    activate
                    if (count of windows) = 0 then
                        make new window
                    end if
                    set URL of active tab of front window to "{url}"
                end tell
                '''
            elif "firefox" in browser_lower:
                script = f'''
                tell application "Firefox"
                    activate
                    open location "{url}"
                end tell
                '''
            else:
                # Default: use system open command
                subprocess.run(["open", url], check=True)
                logger.info(f"✅ Opened URL with system default browser")
                return True
            
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                logger.info(f"✅ Opened URL in {browser}")
                # Wait for page to start loading
                time.sleep(0.5)
                return True
            else:
                logger.warning(f"⚠️ Failed to open URL: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Timeout opening URL in {browser}")
            return False
        except Exception as e:
            logger.error(f"❌ Error opening URL: {e}")
            return False
    
    def _vision_click(self, element_description: str) -> Dict:
        """Handle click actions that need screen analysis."""
        try:
            from ..agents.vision_executor import execute_vision_action
            from ..utils.gemini_client import GeminiCLI
            
            # Create a minimal CLI for vision
            cli = GeminiCLI()
            
            # Pass pre-calculated execution params from probability model
            # This ensures dynamic thresholds (min_match_probability, verification_strictness)
            # are actually used by the vision executor
            exec_params = self.state.execution_params if self.state.execution_params else None
            
            return execute_vision_action(
                cli, 
                f"click {element_description}",
                execution_params=exec_params
            )
        except Exception as e:
            logger.error(f"Vision click failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ========== SUPERVISOR: ADAPTIVE CONTROL ==========
    
    def _supervisor_guide_executor(self, macro_step: Dict, reason: str) -> Dict:
        """
        Supervisor guides executor when it's stuck or uncertain.
        Can provide new actions, skip step, or abort.
        
        DUAL-PATH VALIDATION:
        For semantic mismatches (wrong app active), we can often 
        generate corrective actions without an LLM call.
        """
        self.state.supervisor_interventions += 1
        step_desc = macro_step.get("step", "Unknown")
        
        logger.info(f"🔮 Supervisor intervening: {reason}")
        self._show("supervisor", f"Guiding executor: {reason}", "intervention")
        
        # ========== FAST PATH: Handle semantic mismatches without LLM ==========
        if "semantic_mismatch" in reason.lower() or "app mismatch" in reason.lower():
            fast_correction = self._generate_fast_correction(macro_step, reason)
            if fast_correction:
                logger.info(f"⚡ Fast correction generated (no LLM call)")
                return fast_correction
        
        # ========== SLOW PATH: Full LLM analysis ==========
        # Get fresh screen context
        screen = self._capture_screen_context()
        elements_summary = self._summarize_elements(screen.visible_elements[:30])
        
        prompt = f"""You are the SUPERVISOR. The executor is stuck and needs guidance.

ORIGINAL TASK: {self.state.task}
CURRENT MACRO STEP: {step_desc}
REASON FOR INTERVENTION: {reason}

CURRENT SCREEN STATE:
- App: {screen.app_name}
- Window: {screen.window_title}
- Visible Elements: {elements_summary}

ACTIONS EXECUTED SO FAR: {len(self.state.executed_actions)}

DECIDE what to do:
1. Provide specific actions to achieve the step
2. Skip this step if not needed
3. Abort if task seems impossible

Output JSON:
{{
    "decision": "guide" | "skip" | "abort",
    "reason": "Explanation",
    "actions": [  // Only if decision is "guide"
        {{"type": "hotkey", "params": {{"keys": ["command", "l"]}}, "description": "Focus URL bar"}}
    ],
    "note": "Additional context for learning"
}}

Supervisor decision:"""

        try:
            response = self.client.generate_json(prompt, temperature=0.3)
            
            # Use Pydantic validation for supervisor guidance
            try:
                validated = PydanticSupervisorGuidance.model_validate(response)
                decision = validated.decision.value
                reason = validated.reason
                note = validated.note or ""
                validated_actions = validated.actions
            except Exception as validation_error:
                logger.warning(f"Pydantic validation failed for supervisor guidance: {validation_error}")
                decision = response.get("decision", "abort")
                reason = response.get("reason", "Unknown")
                note = response.get("note", "")
                validated_actions = None
            
            self._show("supervisor", f"Decision: {decision} - {reason}", "decision")
            
            if note:
                self.state.supervisor_notes.append(note)
            
            if decision == "abort":
                return {"abort": True, "reason": reason}
            elif decision == "skip":
                return {"skip": True, "reason": reason}
            else:
                # Convert response actions to MicroActions
                new_actions = []
                if validated_actions:
                    for a in validated_actions:
                        new_actions.append(MicroAction(
                            action_type=a.type,
                            params=a.params.model_dump() if a.params else {},
                            description=a.description
                        ))
                else:
                    for a in response.get("actions", []):
                        new_actions.append(MicroAction(
                            action_type=a.get("type", "unknown"),
                            params=a.get("params", {}),
                            description=a.get("description", "")
                        ))
                return {"new_actions": new_actions}
                
        except Exception as e:
            logger.error(f"Supervisor guidance failed: {e}")
            return {"abort": True, "reason": f"Supervisor error: {e}"}
    
    def _generate_fast_correction(self, macro_step: Dict, reason: str) -> Optional[Dict]:
        """
        Generate corrective actions for semantic mismatches without LLM.
        
        This is the FAST PATH of dual-path validation.
        Handles common cases like wrong app being active.
        
        Returns:
            Dict with 'new_actions' if correction is possible, None otherwise.
        """
        if not SEMANTIC_CHECKER_AVAILABLE:
            return None
        
        try:
            step_desc = macro_step.get("step", "").lower()
            
            # Extract expected app from the step
            from ..supervisor.semantic_checker import extract_expected_app, normalize_app_name
            expected_app = extract_expected_app(step_desc)
            
            if not expected_app:
                return None  # Can't determine expected app, fall back to LLM
            
            # Use DIRECT AppleScript activation instead of Spotlight
            # This is more reliable and faster
            normalized = normalize_app_name(expected_app)
            
            self._show("supervisor", 
                      f"⚡ Fast correction: activating {expected_app} directly", 
                      "fast_fix")
            
            # Activate the app directly via AppleScript
            if self._activate_app(expected_app):
                # Wait for app to be ready
                if self._wait_for_app_activation(expected_app, timeout=2.0):
                    logger.info(f"✅ Fast correction succeeded: {expected_app} is now active")
                    
                    # Return success with no new actions needed - app is already activated
                    return {
                        "new_actions": [],  # No actions needed, app is already active
                        "fast_path": True,
                        "correction_type": "direct_activation",
                        "target_app": expected_app,
                        "skip": False  # Don't skip the step, retry it now that correct app is active
                    }
                else:
                    logger.warning(f"⚠️ App activated but not ready: {expected_app}")
            
            # If direct activation failed, fall back to Spotlight method
            logger.info(f"📍 Falling back to Spotlight for {expected_app}")
            correction_actions = [
                MicroAction(
                    action_type="hotkey",
                    params={"keys": ["command", "space"]},
                    description=f"Open Spotlight to launch {expected_app}"
                ),
                MicroAction(
                    action_type="wait",
                    params={"seconds": 0.5},
                    description="Wait for Spotlight"
                ),
                MicroAction(
                    action_type="type",
                    params={"text": expected_app},
                    description=f"Type '{expected_app}' in Spotlight"
                ),
                MicroAction(
                    action_type="wait",
                    params={"seconds": 0.3},
                    description="Wait for search results"
                ),
                MicroAction(
                    action_type="key",
                    params={"key": "return"},
                    description=f"Launch {expected_app}"
                ),
                MicroAction(
                    action_type="wait",
                    params={"seconds": 1.0},
                    description=f"Wait for {expected_app} to fully open"
                ),
            ]
            
            return {
                "new_actions": correction_actions,
                "fast_path": True,
                "correction_type": "spotlight_fallback",
                "target_app": expected_app
            }
            
        except Exception as e:
            logger.debug(f"Fast correction failed: {e}")
            return None  # Fall back to LLM
    
    def _commit_pending_outcomes(self, success: bool):
        """
        Commit all pending confidence outcomes to the ExecutionConfidenceModel.
        
        DELAYED REWARD PATTERN:
        - Actions are executed and their ratings are stored as "pending"
        - Only when the Supervisor/Verifier confirms the macro-step outcome
          do we commit these outcomes to the model
        - This prevents reward poisoning: clicking the wrong element "succeeds"
          mechanically but fails semantically
        
        Args:
            success: Whether the macro-step was verified as successful
        """
        if not CONFIDENCE_MODEL_AVAILABLE:
            return
        
        pending = self.state.pending_confidence_outcomes
        if not pending:
            return
        
        logger.info(f"📊 Committing {len(pending)} delayed outcomes (success={success})")
        
        for outcome in pending:
            try:
                record_action_outcome(
                    action_type=outcome["action_type"],
                    action_params=outcome["action_params"],
                    rating=outcome["rating"],
                    success=success,  # Use verified outcome, not mechanical success
                    execution_time=outcome["execution_time"],
                    context=outcome.get("context")
                )
            except Exception as e:
                logger.debug(f"Could not commit outcome: {e}")
        
        # Clear pending outcomes after commitment
        self.state.pending_confidence_outcomes.clear()
    
    def _supervisor_verify_completion(self) -> Dict:
        """
        Supervisor verifies if the task is actually complete.
        Takes screen info and analyzes against success criteria.
        """
        logger.info("🔍 Supervisor verifying task completion...")
        self._show("supervisor", "Verifying task completion", "verifying")
        
        # Get final screen state
        screen = self._capture_screen_context()
        elements_summary = self._summarize_elements(screen.visible_elements[:30])
        
        success_criteria = self.state.macro_plan.success_criteria if self.state.macro_plan else "Task completed"
        expected_outcome = self.state.macro_plan.expected_outcome if self.state.macro_plan else "Goal achieved"
        
        # ZERO-ELEMENT SCREENS: Video players, full-screen content, etc.
        # The accessibility API may return 0 elements. Instead of auto-completing,
        # we take a screenshot for visual verification and cap confidence.
        zero_element_mode = len(screen.visible_elements) == 0
        screenshot_description = None
        if zero_element_mode:
            logger.info("  ℹ️  Zero accessible elements - using screenshot-based verification")
            self._show("supervisor", "Zero elements detected - verifying via screenshot", "verifying")
            
            # Try to capture a screenshot for visual context
            screenshot_description = self._describe_screenshot_for_verification()
            if screenshot_description:
                elements_summary = f"(no accessibility elements - screenshot analysis: {screenshot_description})"
            else:
                elements_summary = "(no elements detected, no screenshot available)"
        
        prompt = f"""You are the SUPERVISOR. Verify if the task is ACTUALLY complete.

ORIGINAL TASK: {self.state.task}
EXPECTED OUTCOME: {expected_outcome}
SUCCESS CRITERIA: {success_criteria}

FINAL SCREEN STATE:
- App: {screen.app_name}  
- Window: {screen.window_title}
- Visible Elements: {elements_summary}

EXECUTION SUMMARY:
- Macro Steps Completed: {self.state.current_macro_step_idx}/{len(self.state.macro_plan.macro_steps) if self.state.macro_plan else 0}
- Total Actions: {len(self.state.executed_actions)}
- Supervisor Interventions: {self.state.supervisor_interventions}

ANALYZE the screen state against the success criteria.
Is the task ACTUALLY complete?

Output JSON:
{{
    "complete": true | false,
    "confidence": 0.0-1.0,
    "reason": "Explanation of decision",
    "what_is_missing": "If incomplete, what needs to be done",
    "corrective_steps": [  // Only if incomplete
        {{"step": "What to do", "context": "What to look for"}}
    ]
}}

Verification result:"""

        try:
            response = self.client.generate_json(prompt, temperature=0.2)
            
            # Use Pydantic validation for verification result
            try:
                validated = PydanticVerificationResult.model_validate(response)
                complete = validated.complete
                confidence = validated.confidence
                reason = validated.reason
                what_is_missing = validated.what_is_missing
                corrective_steps = [step.model_dump() for step in validated.corrective_steps]
            except Exception as validation_error:
                logger.warning(f"Pydantic validation failed for verification: {validation_error}")
                complete = response.get("complete", False)
                confidence = response.get("confidence", 0.0)
                reason = response.get("reason", "Unknown")
                what_is_missing = response.get("what_is_missing", "")
                corrective_steps = response.get("corrective_steps", [])
            
            self._show("supervisor", 
                      f"{'✅ Complete' if complete else '❌ Incomplete'} ({confidence:.0%}): {reason}", 
                      "verification")
            
            # Cap confidence when zero-element mode was used (no accessibility data)
            # With screenshot analysis: allow up to 0.80 (can still pass the gate)
            # Without screenshot: cap at 0.65 (blocks auto-completion, forces evolution)
            if zero_element_mode:
                has_screenshot_evidence = screenshot_description is not None
                max_confidence = (
                    _cfg("zero_element_screenshot_cap", 0.80) if has_screenshot_evidence 
                    else _cfg("zero_element_no_screenshot_cap", 0.65)
                )
                if confidence > max_confidence:
                    logger.info(f"  ⚠️ Capping confidence from {confidence:.0%} to {max_confidence:.0%} (zero-element, screenshot={'yes' if has_screenshot_evidence else 'no'})")
                    confidence = max_confidence
            
            # Require high confidence for completion to avoid false positives
            completion_threshold = _cfg("completion_confidence_threshold", 0.75)
            if complete and confidence >= completion_threshold:
                logger.info(f"✅ Task verified complete: {reason}")
                # COMMIT DELAYED REWARDS: Now we know the macro step truly succeeded
                self._commit_pending_outcomes(success=True)
                return {"complete": True, "confidence": confidence}
            else:
                logger.warning(f"⚠️ Task not complete: {what_is_missing or 'Unknown'}")
                # COMMIT DELAYED REWARDS: Actions didn't achieve the goal
                self._commit_pending_outcomes(success=False)
                return {
                    "complete": False,
                    "reason": reason,
                    "what_is_missing": what_is_missing or "",
                    "corrective_steps": corrective_steps
                }
                
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return {"complete": False, "reason": f"Verification error: {e}"}
    
    def _supervisor_evolve_task(self, verification: Dict) -> bool:
        """
        Supervisor takes over planning when verification fails.
        Tells executor its mistakes and what to do now.
        This enables real-time task evolution.
        
        IMPROVED: Now enforces max evolution attempts to prevent infinite loops.
        """
        self.state.evolution_count += 1
        self.state.evolution_attempt_count += 1
        
        # Check if we've exceeded max evolution attempts
        if self.state.evolution_attempt_count > self.state.max_evolution_attempts:
            logger.warning(f"⚠️ Max evolution attempts ({self.state.max_evolution_attempts}) reached")
            self._show("supervisor", "Max evolution attempts reached - task may be complete enough", "warning")
            
            # Stop evolution - task could not be completed within allowed attempts
            logger.warning("❌ Task incomplete after max evolution attempts - marking as failed")
            return False  # Signal that evolution should stop (sets phase to FAILED)
        
        logger.info("🔄 Supervisor evolving task...")
        self._show("supervisor", "Evolving task based on current state", "evolving")
        
        what_is_missing = verification.get("what_is_missing", "Unknown")
        corrective_steps = verification.get("corrective_steps", [])
        
        # If we have corrective steps, add them to the plan
        if corrective_steps:
            logger.info(f"📝 Adding {len(corrective_steps)} corrective steps")
            
            # Convert corrective steps to macro steps
            if self.state.macro_plan:
                self.state.macro_plan.macro_steps.extend(corrective_steps)
            
            for i, step in enumerate(corrective_steps, 1):
                self._show("supervisor", f"New Step {i}: {step.get('step', 'Unknown')}", "evolution")
            
            return True
        
        # Otherwise, generate a new micro plan from current state
        screen = self._capture_screen_context()
        
        prompt = f"""You are the SUPERVISOR taking over planning.
The executor may have completed parts of the task. Analyze current state and create steps to FINISH (not restart).

ORIGINAL TASK: {self.state.task}
WHAT IS MISSING: {what_is_missing}

CURRENT STATE:
- App: {screen.app_name}
- Window: {screen.window_title}

ALREADY COMPLETED STEPS:
{self._summarize_completed_steps()}

EXECUTOR MISTAKES ANALYSIS:
{self._analyze_executor_mistakes()}

IMPORTANT: Do NOT suggest steps that duplicate already completed work.
Only suggest steps that CONTINUE from the current state.
If the app is already open and navigated, do NOT add "Open Safari" or "Navigate to YouTube" again.

Output JSON:
{{
    "executor_mistakes": "What the executor did wrong (if any)",
    "correction_message": "What to do next (continue from current state)",
    "new_steps": [
        {{"step": "What to do now", "context": "What to look for"}}
    ]
}}

Evolution plan:"""

        try:
            response = self.client.generate_json(prompt, temperature=0.3)
            
            mistakes = response.get("executor_mistakes", "Unknown")
            correction = response.get("correction_message", "")
            new_steps = response.get("new_steps", [])
            
            logger.warning(f"📌 Executor mistakes: {mistakes}")
            self._show("supervisor", f"Executor error: {mistakes}", "correction")
            self._show("supervisor", f"Correction: {correction}", "correction")
            
            if new_steps and self.state.macro_plan:
                self.state.macro_plan.macro_steps.extend(new_steps)
                logger.info(f"📝 Added {len(new_steps)} evolved steps")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Task evolution failed: {e}")
            return False
    
    def _analyze_executor_mistakes(self) -> str:
        """Analyze what went wrong in execution."""
        if not self.state.executed_actions:
            return "No actions were executed."
        
        summary = []
        for i, action in enumerate(self.state.executed_actions[-10:], 1):
            summary.append(f"{i}. {action.get('type')}: {action.get('description')}")
        
        return "\n".join(summary)
    
    def _summarize_completed_steps(self) -> str:
        """Summarize what steps have been completed for evolution context."""
        if not self.state.macro_plan:
            return "No plan available"
        
        completed = []
        for i in range(self.state.current_macro_step_idx):
            if i < len(self.state.macro_plan.macro_steps):
                step = self.state.macro_plan.macro_steps[i]
                step_desc = step.get("step", "Unknown") if isinstance(step, dict) else str(step)
                completed.append(f"  ✓ Step {i+1}: {step_desc}")
        
        if not completed:
            return "No steps completed yet"
        
        return "\n".join(completed)
    
    def _app_matches_task(self, app_name: str, task: str) -> bool:
        """Check if current app matches what the task expects."""
        app_lower = app_name.lower()
        task_lower = task.lower()
        
        # Browser tasks (video, search, web)
        browser_keywords = ["youtube", "video", "google", "web", "search online", "play a", "watch"]
        if any(kw in task_lower for kw in browser_keywords):
            return app_lower in ["safari", "google chrome", "firefox", "arc", "brave", "edge"]
        
        # App-specific tasks  
        if "whatsapp" in task_lower:
            return "whatsapp" in app_lower
        if "messages" in task_lower:
            return "messages" in app_lower
        if "notes" in task_lower:
            return "notes" in app_lower
        if "mail" in task_lower or "email" in task_lower:
            return "mail" in app_lower or "outlook" in app_lower
        if "calendar" in task_lower:
            return "calendar" in app_lower
        if "spotify" in task_lower or "music" in task_lower:
            return "spotify" in app_lower or "music" in app_lower
        
        # Conservative default: reject unknown task-app mappings
        # This prevents false completion when we can't verify the right app is open
        logger.debug(f"  ⚠️ _app_matches_task: no known mapping for task='{task[:50]}' app='{app_name}'")
        return False
    
    # ========== SCREEN CONTEXT ==========
    
    def _describe_screenshot_for_verification(self) -> Optional[str]:
        """
        Take a screenshot and describe it using a vision model.
        Used as fallback when accessibility elements are unavailable (e.g. video players).
        Returns a text description of the screen, or None if screenshot fails.
        """
        try:
            import subprocess, tempfile, os
            
            # Take screenshot using macOS screencapture
            fd, screenshot_path = tempfile.mkstemp(suffix=".png", prefix="verify_")
            os.close(fd)
            subprocess.run(["screencapture", "-x", screenshot_path], check=True, capture_output=True)
            
            if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) == 0:
                return None
            
            # Try to use LLM with vision to describe the screenshot
            try:
                import base64
                with open(screenshot_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                
                response = self.client.generate(
                    prompt="Describe what you see on this screen in 2-3 sentences. Focus on: which app is open, what content is visible, and any notable UI state (dialogs, errors, loading).",
                    images=[img_data],
                    temperature=0.1
                )
                return response.strip() if response else None
            except Exception as vision_err:
                logger.debug(f"Vision-based screenshot description unavailable: {vision_err}")
                # Fallback: return basic file info as evidence screenshot was taken
                file_size = os.path.getsize(screenshot_path)
                return f"Screenshot captured ({file_size} bytes) but vision model unavailable"
            finally:
                try:
                    os.unlink(screenshot_path)
                except OSError:
                    pass
                    
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return None
    
    def _capture_screen_context(self) -> ScreenContext:
        """Capture current screen state using the platform abstraction layer."""
        try:
            # Use platform bundle when available (works on macOS + Linux)
            if self._platform:
                app_info = self._platform.accessibility.get_frontmost_app_info()
                tree = self._platform.accessibility.get_ui_tree(max_depth=3)
                elements = []
                if tree:
                    # Flatten tree to element list for compatibility
                    def _collect(node, out, limit=50):
                        if len(out) >= limit:
                            return
                        out.append(node)
                        for child in (node.children or []):
                            _collect(child, out, limit)
                    _collect(tree, elements)

                return ScreenContext(
                    app_name=app_info.get("app", "Unknown"),
                    window_title=app_info.get("window", ""),
                    visible_elements=elements,
                )

            # Fallback: direct macOS accessibility reader
            from ..utils.accessibility_reader import get_frontmost_app, get_ui_elements_applescript
            
            app_info = get_frontmost_app()
            elements = get_ui_elements_applescript(max_elements=50)
            
            return ScreenContext(
                app_name=app_info.get("app", "Unknown"),
                window_title=app_info.get("window", ""),
                visible_elements=elements
            )
        except Exception as e:
            logger.warning(f"Screen capture failed: {e}")
            return ScreenContext(
                app_name="Unknown",
                window_title="",
                visible_elements=[]
            )
    
    def _screen_matches_expectation(self, screen: ScreenContext, expected: str) -> bool:
        """Check if screen matches expected context."""
        if not expected:
            return True
        
        expected_lower = expected.lower()
        app_lower = screen.app_name.lower()
        window_lower = screen.window_title.lower()
        
        # Check if expected keywords are in app or window
        keywords = expected_lower.split()
        for keyword in keywords:
            if keyword in app_lower or keyword in window_lower:
                return True
        
        return False
    
    # ========== CONNECTION ERROR HANDLING & WARP VPN RECOVERY ==========
    
    def _detect_connection_error(self, screen: ScreenContext) -> bool:
        """
        Detect if the current browser screen shows a connection error.
        
        Checks for common error patterns in window title and page content.
        """
        window_lower = screen.window_title.lower()
        
        # Common browser connection error patterns
        error_patterns = [
            "can't be reached",
            "cannot be reached", 
            "err_connection",
            "dns_probe",
            "no internet",
            "check your connection",
            "server dns address could not be found",
            "err_name_not_resolved",
            "this site can't be reached",
            "unable to connect",
            "connection refused",
            "connection timed out",
            "network error",
        ]
        
        for pattern in error_patterns:
            if pattern in window_lower:
                logger.warning(f"🌐 Connection error detected: '{pattern}' in window title")
                return True
        
        # Also check visible elements for error text
        for elem in screen.visible_elements[:20]:
            elem_text = str(elem.get("title", "") + " " + elem.get("description", "")).lower()
            for pattern in error_patterns:
                if pattern in elem_text:
                    logger.warning(f"🌐 Connection error detected in UI: '{pattern}'")
                    return True
        
        return False
    
    def _enable_warp_vpn(self) -> bool:
        """
        Enable Cloudflare WARP VPN by clicking the menu bar icon.
        
        Steps:
        1. Click Cloudflare WARP icon in menu bar
        2. Wait for menu to appear
        3. Click Connect/toggle
        4. Wait for VPN to establish connection
        
        Returns True if WARP was successfully enabled.
        """
        import pyautogui
        import time
        
        try:
            self._show("system", "🔌 Enabling Cloudflare WARP VPN...", "info")
            logger.info("🔌 Attempting to enable Cloudflare WARP VPN")
            
            # Try to use vision to find and click WARP icon in menu bar
            # WARP icon is usually in the top-right menu bar area
            try:
                from ..agents.vision_executor import execute_vision_action
                
                # Click the WARP menu bar icon
                result = execute_vision_action(
                    self.client,
                    "click: Cloudflare WARP icon in the macOS menu bar (top right, looks like a 1.1.1.1 or orange/blue icon)",
                    max_attempts=2
                )
                
                if not result.get("success"):
                    logger.warning("Could not find WARP icon via vision, trying coordinate fallback")
                    # Fallback: Click near typical menu bar icon location (right side)
                    screen_width, _ = pyautogui.size()
                    # WARP is usually around 100-200px from right edge
                    pyautogui.click(screen_width - 150, 12)
                
                time.sleep(0.5)  # Wait for menu to appear
                
                # Click Connect or the toggle switch
                result = execute_vision_action(
                    self.client,
                    "click: Connect button or toggle switch in the WARP menu (to enable VPN connection)",
                    max_attempts=2
                )
                
                if not result.get("success"):
                    # Fallback: try clicking center of menu that just appeared
                    screen_width, _ = pyautogui.size()
                    pyautogui.click(screen_width - 150, 80)
                
                # Wait for WARP to connect (5-10 seconds typically)
                self._show("system", "⏳ Waiting for WARP VPN to connect...", "info")
                time.sleep(8)
                
                # Click elsewhere to close menu
                pyautogui.click(screen_width // 2, 400)
                time.sleep(0.3)
                
                logger.info("✅ WARP VPN should now be connected")
                self._show("system", "✅ WARP VPN connected", "success")
                return True
                
            except ImportError:
                logger.error("Vision executor not available for WARP recovery")
                return False
                
        except Exception as e:
            logger.error(f"Failed to enable WARP VPN: {e}")
            self._show("system", f"❌ WARP enable failed: {e}", "error")
            return False
    
    def _handle_connection_error(self, url: str = None) -> bool:
        """
        Handle a detected connection error by enabling WARP and reloading.
        
        Args:
            url: Optional URL to reload (if known)
            
        Returns True if recovery was successful.
        """
        import pyautogui
        import time
        
        self._show("system", "🌐 Connection error detected - attempting WARP recovery", "warning")
        
        # Step 1: Enable WARP VPN
        if not self._enable_warp_vpn():
            logger.error("WARP VPN recovery failed")
            return False
        
        # Step 2: Reload the page
        self._show("system", "🔄 Reloading page...", "info")
        pyautogui.hotkey("command", "r")
        
        # Step 3: Wait longer for page to load (connection may be slow initially)
        time.sleep(7)
        
        # Step 4: Check if error is resolved
        screen = self._capture_screen_context()
        if self._detect_connection_error(screen):
            logger.warning("Connection error persists after WARP - may need more time")
            self._show("system", "⏳ Waiting more for page to load...", "info")
            time.sleep(5)
            
            # Final check
            screen = self._capture_screen_context()
            if self._detect_connection_error(screen):
                self._show("system", "❌ Connection still failing after WARP", "error")
                return False
        
        self._show("system", "✅ Connection recovered!", "success")
        return True

    def _adaptive_replan(
        self, 
        original_task: str, 
        current_step: str, 
        expected: str, 
        actual_screen: ScreenContext,
        remaining_steps: int = 0
    ) -> Optional[Dict]:
        """
        Adaptive re-planning when the screen state is unexpected.
        
        Instead of continuing blindly with the original plan, analyze the current
        screen state and generate new steps to recover and complete the task.
        
        This handles cases like:
        - Ad popups that need to be dismissed
        - Intermediate pages (captchas, age verification, etc.)
        - Wrong page landed on
        - Navigation derailment
        
        Args:
            original_task: The original user task description
            current_step: The step that was just executed
            expected: What screen we expected to see
            actual_screen: What screen we actually see
            remaining_steps: How many original steps remain
            
        Returns:
            Dict with 'new_steps' list or None if re-plan failed
        """
        logger.info(f"🔄 Adaptive re-planning from unexpected screen state")
        self._show("planner", "🔄 Analyzing current screen for recovery plan...", "thinking")
        
        # Build context about current situation
        visible_elements_summary = self._summarize_elements(actual_screen.visible_elements[:15])
        
        prompt = f"""The automation agent has encountered an unexpected screen and needs to re-plan.

ORIGINAL TASK: {original_task}

JUST EXECUTED STEP: {current_step}
EXPECTED SCREEN: {expected}
ACTUAL SCREEN:
- App: {actual_screen.app_name}
- Window: {actual_screen.window_title}
- Visible Elements: {visible_elements_summary}

The screen doesn't match what we expected. This could be:
1. An ad popup that needs closing (click X or close button)
2. An intermediate page (captcha, verification, countdown timer)
3. Wrong page navigation
4. A dialog/modal that appeared

Analyze the current screen and generate 1-5 recovery steps to get back on track towards completing the original task.

Respond in JSON format:
{{
    "analysis": "Brief explanation of what went wrong and why",
    "recovery_strategy": "How to recover from this state", 
    "new_steps": [
        {{"step": "Close the popup/ad", "step_type": "vision", "suggested_actions": ["click:close button or X icon"]}},
        {{"step": "Wait for page to load", "step_type": "blind", "suggested_actions": ["wait:3"]}},
        ...
    ]
}}

IMPORTANT:
- Keep suggested_actions in the format: "type:text", "click:element description", "key:keyname", "wait:seconds", "hotkey:cmd,key"
- Focus on immediate recovery, not re-doing the whole task
- If it looks like an ad page, include closing the ad
- If it looks like a countdown timer, include waiting
- If on completely wrong page, include navigation back"""

        try:
            response = self.client.generate_json(prompt, temperature=0.3)
            
            if response and isinstance(response, dict):
                analysis = response.get("analysis", "")
                strategy = response.get("recovery_strategy", "")
                new_steps = response.get("new_steps", [])
                
                if analysis:
                    logger.info(f"📋 Re-plan analysis: {analysis}")
                if strategy:
                    logger.info(f"📋 Recovery strategy: {strategy}")
                    self._show("planner", f"Recovery: {strategy[:60]}...", "info")
                
                if new_steps and len(new_steps) > 0:
                    for i, step in enumerate(new_steps, 1):
                        step_desc = step.get("step", f"Step {i}")
                        self._show("planner", f"Recovery Step {i}: {step_desc}", "thinking")
                    
                    return {"new_steps": new_steps, "analysis": analysis}
                    
            return None
            
        except Exception as e:
            logger.error(f"Adaptive re-planning failed: {e}")
            return None
    
    def _verify_step_completion(self, macro_step: Dict) -> bool:
        """
        Verify if a macro step has been completed by checking the current screen state.
        
        This is crucial for detecting when navigation/launch steps are complete
        even if confidence scoring failed.
        
        Returns True if step appears complete based on screen state.
        """
        step_desc = macro_step.get("step", "").lower()
        context_hint = macro_step.get("context", "").lower()
        
        # Get fresh screen context
        screen = self._capture_screen_context()
        app_lower = screen.app_name.lower()
        window_lower = screen.window_title.lower()
        
        # Extract keywords from step description for matching
        step_keywords = self._extract_step_keywords(step_desc, context_hint)
        
        if not step_keywords:
            # Can't determine expected state, assume not complete
            return False
        
        # Check if any expected keyword is in current app or window
        for keyword in step_keywords:
            if keyword in app_lower or keyword in window_lower:
                logger.info(f"✅ Step verified complete: found '{keyword}' in screen state")
                return True
        
        # Special case: browser open but on different page
        if any(browser in app_lower for browser in ["safari", "chrome", "firefox", "arc", "edge", "brave"]):
            # Check if step was about opening a website
            website_keywords = ["youtube", "google", "facebook", "twitter", "instagram", "reddit", "github"]
            for site in website_keywords:
                if site in step_desc or site in context_hint:
                    if site in window_lower:
                        logger.info(f"✅ Step verified: {site} is visible in browser")
                        return True
        
        return False
    
    def _extract_step_keywords(self, step_desc: str, context_hint: str) -> List[str]:
        """
        Extract keywords from step description that indicate expected screen state.
        
        Examples:
        - "Launch Safari browser" -> ["safari"]
        - "Navigate to YouTube" -> ["youtube"]
        - "Open WhatsApp" -> ["whatsapp"]
        - "Search for MKBHD" -> ["mkbhd", "search"]
        """
        keywords = []
        
        # Common app names
        apps = ["safari", "chrome", "firefox", "whatsapp", "messages", "finder",
                "music", "spotify", "youtube", "google", "settings", "system preferences",
                "terminal", "notes", "mail", "calendar", "photos", "preview"]
        
        # Check step description for app names
        combined = (step_desc + " " + context_hint).lower()
        for app in apps:
            if app in combined:
                keywords.append(app)
        
        # Extract domain names (e.g., "youtube.com" -> "youtube")
        import re
        domain_pattern = r'([a-zA-Z0-9-]+)\.(com|org|net|io|app)'
        domains = re.findall(domain_pattern, combined)
        for domain, tld in domains:
            if domain not in keywords:
                keywords.append(domain.lower())
        
        return keywords
    
    def _summarize_elements(self, elements: List[Dict]) -> str:
        """Create a summary of visible UI elements."""
        if not elements:
            return "(no elements detected)"
        
        summary = []
        for e in elements[:15]:
            role = e.get("role", "unknown")
            name = e.get("name", "")[:30]
            if name:
                summary.append(f"{role}: {name}")
        
        return ", ".join(summary) if summary else "(no named elements)"
    
    # ========== HELPERS ==========
    
    def _show(self, component: str, message: str, msg_type: str = "info"):
        """Show message in thinking window and emit to the API dashboard."""
        if _event_bus:
            _event_bus.emit("thinking", {
                "component": component,
                "message": message,
                "type": msg_type,
                "phase": self.state.phase.value if self.state else None,
            })
        if not self.enable_thinking_window:
            return

        try:
            if component == "planner":
                show_planner_thinking(message)
            elif component == "executor":
                show_executor_thinking(message)
            elif component == "supervisor":
                show_supervisor_thinking(message)
            else:
                show_thinking(component, message, msg_type)
        except:
            pass

    def _capture_screen_context(self) -> Optional[ScreenContext]:
        """Capture current screen context and broadcast screenshot for the dashboard."""
        context = self.__capture_screen_context()
        if context and context.screenshot_path:
            try:
                from pathlib import Path
                img_bytes = Path(context.screenshot_path).read_bytes()
                import base64
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                if _event_bus:
                    _event_bus.emit("screenshot", {
                        "image_base64": f"data:image/png;base64,{b64}",
                        "timestamp": context.timestamp.isoformat(),
                    })
            except Exception:
                pass
        return context

    def __capture_screen_context(self) -> Optional[ScreenContext]:
        return self._old_capture_screen_context()

    def _old_capture_screen_context(self) -> Optional[ScreenContext]:
        """Original screen capture logic (renamed)."""
