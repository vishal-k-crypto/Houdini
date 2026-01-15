"""
LangGraph Coordinator for Houdini Agent.

This replaces the manual AdaptiveLoopCoordinator with LangGraph-based
execution flow. Benefits:

1. Built-in State Management: No manual state tracking
2. Checkpointing: Automatic state persistence for crash recovery
3. Human-in-the-Loop: Easy to add approval points
4. Visualization: Graph can be visualized for debugging
5. Streaming: Built-in support for streaming updates

Graph Structure:
    ┌─────────────┐
    │  __start__  │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   analyze   │  (probability model + initial setup)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   planner   │  (macro planning)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐◄─────────────────────┐
    │  executor   │  (micro actions)     │
    └──────┬──────┘                      │
           │                             │
           ▼                             │
    ┌─────────────┐   needs_supervisor   │
    │  router     │──────────────────────┤
    └──────┬──────┘                      │
           │ step_complete               │
           ▼                             │
    ┌─────────────┐                      │
    │  verifier   │                      │
    └──────┬──────┘                      │
           │                             │
           ▼                             │
    ┌─────────────┐   incomplete         │
    │  evolver    │──────────────────────┘
    └──────┬──────┘
           │ complete
           ▼
    ┌─────────────┐
    │  __end__    │
    └─────────────┘
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal

# LangGraph imports - require installation: pip install langgraph langchain-core
try:
    from langgraph.graph import StateGraph, END, START
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.checkpoint.sqlite import SqliteSaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None
    START = None
    MemorySaver = None
    SqliteSaver = None

from .langgraph_state import (
    HoudiniAgentState,
    AgentPhase,
    MacroStep,
    MicroAction,
    ScreenContext,
    ActionRecord,
    SupervisorIntervention,
    create_initial_state,
    state_to_context_prompt,
)
from ..utils.logging import logger
from ..utils.ollama_client import OllamaClient
from ..ui.thinking_window import (
    show_planner_thinking,
    show_executor_thinking,
    show_supervisor_thinking,
    show_thinking,
    set_window_status,
)

# Import probability model if available
try:
    from ..utils.probability_model import (
        analyze_task_flexibility,
        get_flexible_execution_params,
    )
    PROBABILITY_MODEL_AVAILABLE = True
except ImportError:
    PROBABILITY_MODEL_AVAILABLE = False
    logger.debug("Probability model not available")

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


class LangGraphCoordinator:
    """
    LangGraph-based coordinator for Houdini Agent.
    
    Replaces the manual loop management in AdaptiveLoopCoordinator
    with a declarative graph structure that provides:
    
    - Automatic state management
    - Built-in checkpointing for crash recovery
    - Human-in-the-loop hooks
    - Clear execution flow visualization
    """
    
    def __init__(
        self,
        client: OllamaClient,
        enable_thinking_window: bool = True,
        max_iterations: int = 100,
        max_evolutions: int = 3,
        checkpoint_path: Optional[str] = None,
        enable_human_approval: bool = False,
    ):
        """
        Initialize the LangGraph coordinator.
        
        Args:
            client: Ollama client for LLM calls
            enable_thinking_window: Whether to show thinking window
            max_iterations: Maximum execution iterations
            max_evolutions: Maximum task evolutions
            checkpoint_path: SQLite path for persistent checkpoints (None = memory only)
            enable_human_approval: Whether to pause for human approval at key points
        """
        # Check if LangGraph is available
        if not LANGGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraph is not installed. Please install it with:\n"
                "  pip install langgraph langchain-core\n"
                "Or use the adaptive coordinator instead (remove --langgraph flag)"
            )
        
        self.client = client
        self.enable_thinking_window = enable_thinking_window
        self.max_iterations = max_iterations
        self.max_evolutions = max_evolutions
        self.enable_human_approval = enable_human_approval
        
        # Setup checkpointing
        if checkpoint_path:
            self.checkpointer = SqliteSaver.from_conn_string(checkpoint_path)
        else:
            self.checkpointer = MemorySaver()
        
        # Event-driven wait system
        self._ui_wait: Optional[UIWaitSystem] = None
        if UI_WAIT_AVAILABLE:
            try:
                self._ui_wait = get_ui_wait_system()
                logger.debug("LangGraphCoordinator: Event-driven UI wait system initialized")
            except Exception as e:
                logger.debug(f"Could not init UI wait system: {e}")
        
        # Build the graph
        self.graph = self._build_graph()
        
        # Compile with checkpointing
        self.app = self.graph.compile(checkpointer=self.checkpointer)
    
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
    
    def _build_graph(self) -> "StateGraph":
        """Build the LangGraph execution graph."""
        
        # Create the graph with our state schema
        graph = StateGraph(HoudiniAgentState)
        
        # Add nodes
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("planner", self._planner_node)
        graph.add_node("executor", self._executor_node)
        graph.add_node("supervisor", self._supervisor_node)
        graph.add_node("verifier", self._verifier_node)
        graph.add_node("evolver", self._evolver_node)
        
        # Optional human-in-the-loop node
        if self.enable_human_approval:
            graph.add_node("human_approval", self._human_approval_node)
        
        # Define edges
        graph.add_edge(START, "analyze")
        graph.add_edge("analyze", "planner")
        graph.add_edge("planner", "executor")
        
        # Conditional routing after executor
        graph.add_conditional_edges(
            "executor",
            self._route_after_executor,
            {
                "supervisor": "supervisor",
                "verifier": "verifier",
                "executor": "executor",
                "end": END,
            }
        )
        
        # After supervisor, go back to executor
        graph.add_edge("supervisor", "executor")
        
        # Conditional routing after verifier
        graph.add_conditional_edges(
            "verifier",
            self._route_after_verifier,
            {
                "evolver": "evolver",
                "end": END,
            }
        )
        
        # After evolver, either continue or end
        graph.add_conditional_edges(
            "evolver",
            self._route_after_evolver,
            {
                "executor": "executor",
                "end": END,
            }
        )
        
        return graph
    
    # ========== NODE IMPLEMENTATIONS ==========
    
    def _analyze_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Initial analysis node.
        - Analyzes task with probability model
        - Sets up execution parameters
        """
        logger.info(f"🔍 Analyzing task: {state['task']}")
        self._show("system", f"Analyzing: {state['task']}", "info")
        
        updates: Dict[str, Any] = {
            "phase": AgentPhase.PLANNING.value,
        }
        
        # Probability model analysis
        if PROBABILITY_MODEL_AVAILABLE:
            try:
                flexibility = analyze_task_flexibility(
                    state["task"],
                    context={"current_app": self._get_current_app_name()}
                )
                
                updates["uncertainty_score"] = flexibility.overall_uncertainty
                updates["execution_params"] = get_flexible_execution_params(state["task"])
                updates["task_flexibility"] = {
                    "completeness": flexibility.task_completeness.overall_score,
                    "macro_micro_position": flexibility.macro_micro.position,
                    "strategy": flexibility.macro_micro.execution_strategy,
                    "intent": flexibility.intent.primary_intent,
                    "intent_confidence": flexibility.intent.confidence,
                    "ambiguity": flexibility.intent.ambiguity_score,
                    "missing_info": flexibility.task_completeness.missing_info,
                    "predicted_info": flexibility.task_completeness.predicted_info,
                    "recommended_approach": flexibility.recommended_approach,
                }
                
                logger.info(f"   Completeness: {flexibility.task_completeness.overall_score:.0%}")
                logger.info(f"   Uncertainty: {flexibility.overall_uncertainty:.0%}")
                
            except Exception as e:
                logger.warning(f"Probability analysis failed: {e}")
                updates["uncertainty_score"] = 0.5
        
        return updates
    
    def _planner_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Macro planning node.
        Generates high-level steps for the task.
        """
        logger.info(f"📋 Planning: {state['task']}")
        self._show("planner", f"Creating macro plan for: {state['task']}", "planning")
        
        # Build flexibility context if available
        flexibility_context = ""
        if state.get("task_flexibility"):
            flex = state["task_flexibility"]
            flexibility_context = f"""
TASK ANALYSIS:
- Completeness: {flex.get('completeness', 0):.0%}
- Intent: {flex.get('intent', 'unknown')}
- Missing info: {', '.join(flex.get('missing_info', []))}
- Recommended approach: {flex.get('recommended_approach', 'standard')}
"""
        
        prompt = f"""You are a MACRO PLANNER. Your job is to understand the task at a HIGH LEVEL only.
DO NOT give specific keyboard shortcuts or detailed actions.
Give broad steps that a human would understand.
{flexibility_context}
TASK: {state['task']}

Output JSON:
{{
    "macro_steps": [
        {{
            "step": "High-level description of what to do",
            "context": "What should be visible/achieved after this step",
            "potential_issues": "What could go wrong"
        }}
    ],
    "expected_outcome": "What success looks like",
    "success_criteria": "How to verify the task is complete"
}}

Keep steps BROAD and CONCEPTUAL. The executor will figure out the details.

Generate the macro plan:"""
        
        try:
            response = self.client.generate_json(prompt, temperature=0.3)
            
            macro_steps = response.get("macro_steps", [])
            if not macro_steps:
                return {
                    "phase": AgentPhase.FAILED.value,
                    "error": "No macro steps generated",
                    "should_abort": True,
                }
            
            logger.info(f"   Generated {len(macro_steps)} macro steps")
            for i, step in enumerate(macro_steps, 1):
                self._show("planner", f"Step {i}: {step.get('step', 'Unknown')}", "planning")
            
            return {
                "macro_steps": macro_steps,
                "expected_outcome": response.get("expected_outcome", "Task completed"),
                "success_criteria": response.get("success_criteria", "Goal achieved"),
                "phase": AgentPhase.EXECUTING.value,
            }
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return {
                "phase": AgentPhase.FAILED.value,
                "error": f"Planning failed: {e}",
                "should_abort": True,
            }
    
    def _executor_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Micro executor node.
        Takes current macro step + screen context → generates and executes micro actions.
        """
        import pyautogui
        
        # Check iteration limit
        iteration = state.get("iteration", 0) + 1
        if iteration > state.get("max_iterations", 100):
            return {
                "phase": AgentPhase.FAILED.value,
                "error": "Max iterations exceeded",
                "should_abort": True,
            }
        
        current_idx = state.get("current_macro_step_idx", 0)
        macro_steps = state.get("macro_steps", [])
        
        # Check if all steps complete
        if current_idx >= len(macro_steps):
            return {
                "iteration": iteration,
                "phase": AgentPhase.VERIFYING.value,
            }
        
        current_step = macro_steps[current_idx]
        step_desc = current_step.get("step", "Unknown")
        
        logger.info(f"▶️ Executing step {current_idx + 1}/{len(macro_steps)}: {step_desc}")
        self._show("executor", f"━━━ Step {current_idx + 1}: {step_desc} ━━━", "executing")
        
        # Capture screen context
        screen_context = self._capture_screen_context()
        
        # Show current context
        self._show("executor", f"📍 Current: {screen_context.get('app_name', 'Unknown')} | {screen_context.get('window_title', '')[:40]}", "info")
        
        # Generate micro actions
        elements_summary = self._summarize_elements(screen_context.get("visible_elements", [])[:20])
        
        # Show thinking indicator before LLM call
        self._show("executor", "⏳ Planning actions...", "thinking")
        
        prompt = f"""You are a MICRO EXECUTOR. Generate specific cursor/keyboard actions.

MACRO STEP: {step_desc}
CURRENT APP: {screen_context.get('app_name', 'Unknown')}
WINDOW: {screen_context.get('window_title', '')}
VISIBLE ELEMENTS: {elements_summary}

Generate SPECIFIC actions. Format each action as:
- hotkey:key1,key2 (e.g., hotkey:command,space)
- type:text to type
- key:keyname (e.g., key:return)
- wait:seconds
- click:element_description

Output JSON:
{{
    "actions": [
        {{"type": "hotkey", "params": {{"keys": ["command", "space"]}}, "description": "Open Spotlight"}},
        {{"type": "type", "params": {{"text": "Safari"}}, "description": "Type app name"}},
        {{"type": "key", "params": {{"key": "return"}}, "description": "Launch app"}}
    ],
    "confidence": 0.9
}}

RULES:
1. Use keyboard shortcuts when possible (faster than clicking)
2. On macOS: Cmd+Space for Spotlight, Cmd+L for URL bar, Cmd+T for new tab
3. For "click:" actions, be specific about what to click

Generate micro actions:"""
        
        try:
            response = self.client.generate_json(prompt, temperature=0.2)
            
            actions = response.get("actions", [])
            confidence = response.get("confidence", 0.5)
            
            if confidence < 0.5 or not actions:
                return {
                    "iteration": iteration,
                    "current_screen": screen_context,
                    "screen_history": [screen_context],
                    "needs_supervisor": True,
                    "supervisor_reason": f"Low confidence ({confidence:.0%}) for: {step_desc}",
                    "phase": AgentPhase.SUPERVISOR_GUIDE.value,
                }
            
            # Show action plan summary
            action_types = [a.get("type", "?") for a in actions]
            self._show("executor", f"✓ Plan ready: {len(actions)} actions ({', '.join(action_types[:3])}{'...' if len(action_types) > 3 else ''})", "success")
            
            # Execute actions
            executed = []
            success = True
            error_msg = None
            action_start_time = None
            pending_outcomes = []  # DELAYED REWARD: Store outcomes until verification
            
            total_actions = len(actions)
            for action_idx, action in enumerate(actions, 1):
                action_type = action.get("type", "")
                params = action.get("params", {})
                description = action.get("description", "")
                rating = None  # Track confidence rating for outcome recording
                action_start_time = time.time()
                
                # Show what we're about to do FIRST
                action_label = f"[{action_idx}/{total_actions}] {action_type}: {description}"
                self._show("executor", f"▶ {action_label}", "action")
                
                try:
                    # ========== CONFIDENCE GATING ==========
                    # Rate action before execution using the confidence model
                    if CONFIDENCE_MODEL_AVAILABLE:
                        context = {
                            "current_app": screen_context.get("app_name", "unknown"),
                            "screen_active": True,
                        }
                        rating = rate_action(
                            action_type,
                            params,
                            context=context
                        )
                        
                        logger.info(f"📊 Action confidence: {rating.score:.1f}/10 ({rating.level.value})")
                        
                        # Defer to supervisor if confidence too low
                        if rating.score < 3.0:
                            logger.warning(f"⚠️ Low confidence ({rating.score:.1f}), deferring to supervisor")
                            return {
                                "iteration": iteration,
                                "current_screen": screen_context,
                                "screen_history": [screen_context],
                                "needs_supervisor": True,
                                "supervisor_reason": f"Action '{description}' has low confidence ({rating.score:.1f}/10)",
                                "phase": AgentPhase.SUPERVISOR_GUIDE.value,
                            }
                    
                    self._show("executor", f"→ {action_type}: {description}", "action")
                    
                    if action_type == "hotkey":
                        keys = params.get("keys", [])
                        pyautogui.hotkey(*keys)
                        self._smart_wait_after("hotkey")
                    elif action_type == "type":
                        text = params.get("text", "")
                        pyautogui.write(text, interval=0.02)
                        self._smart_wait_after("type")
                    elif action_type == "key":
                        key = params.get("key", "")
                        pyautogui.press(key)
                        self._smart_wait_after("key")
                    elif action_type == "wait":
                        secs = params.get("seconds", 0.5)
                        # Use event-driven wait if available
                        if self._ui_wait and secs >= 0.3:
                            result = self._ui_wait.wait_for_ui_stable(
                                max_wait_ms=int(secs * 1000),
                                stability_ms=150
                            )
                            logger.debug(f"Smart wait: requested {secs}s, actual {result.waited_ms:.0f}ms")
                        else:
                            time.sleep(secs)
                    elif action_type == "click":
                        # Pass pre-calculated execution params from probability model
                        exec_params = state.get("execution_params")
                        click_result = self._vision_click(
                            params.get("element", description),
                            execution_params=exec_params
                        )
                        if not click_result.get("success"):
                            raise Exception(click_result.get("error", "Click failed"))
                        self._smart_wait_after("click")
                    
                    duration_ms = (time.time() - action_start_time) * 1000
                    
                    executed.append(ActionRecord(
                        type=action_type,
                        params=params,
                        description=description,
                        timestamp=datetime.now().isoformat(),
                        success=True,
                        error=None,
                    ))
                    
                    # Show completion in thinking window
                    self._show("executor", f"✓ Done ({duration_ms:.0f}ms)", "success")
                    
                    # DELAYED REWARD: Store pending outcome for later commitment
                    # Don't record outcome yet - wait for Verifier to confirm macro-step success
                    # This prevents reward poisoning from "successful" clicks on wrong elements
                    if CONFIDENCE_MODEL_AVAILABLE and rating:
                        pending_outcomes.append({
                            "action_type": action_type,
                            "action_params": params,
                            "rating": rating,
                            "execution_time": time.time() - action_start_time,
                            "context": {"app": screen_context.get("app_name", "unknown")}
                        })
                    
                except Exception as e:
                    logger.error(f"Action failed: {description} - {e}")
                    executed.append(ActionRecord(
                        type=action_type,
                        params=params,
                        description=description,
                        timestamp=datetime.now().isoformat(),
                        success=False,
                        error=str(e),
                    ))
                    
                    # Immediate failure IS a valid signal - record it now
                    # (pyautogui threw an exception, so the action truly failed)
                    if CONFIDENCE_MODEL_AVAILABLE and rating:
                        try:
                            record_action_outcome(
                                action_type=action_type,
                                action_params=params,
                                rating=rating,
                                success=False,
                                execution_time=time.time() - action_start_time if action_start_time else 0,
                                context={"app": screen_context.get("app_name", "unknown")},
                                error_type=type(e).__name__
                            )
                        except Exception as outcome_err:
                            logger.debug(f"Could not record failed action outcome: {outcome_err}")
                    
                    success = False
                    error_msg = str(e)
                    break
            
            # Move to next step if successful
            next_idx = current_idx + 1 if success else current_idx
            
            return {
                "iteration": iteration,
                "current_screen": screen_context,
                "screen_history": [screen_context],
                "executed_actions": executed,
                "current_macro_step_idx": next_idx,
                "last_action_success": success,
                "last_action_error": error_msg,
                "needs_supervisor": not success,
                "supervisor_reason": error_msg if not success else None,
                "phase": AgentPhase.SUPERVISOR_GUIDE.value if not success else AgentPhase.EXECUTING.value,
                "pending_confidence_outcomes": pending_outcomes,  # Pass pending outcomes to state
            }
            
        except Exception as e:
            logger.error(f"Executor failed: {e}")
            return {
                "iteration": iteration,
                "current_screen": screen_context,
                "screen_history": [screen_context],
                "needs_supervisor": True,
                "supervisor_reason": f"Executor error: {e}",
                "phase": AgentPhase.SUPERVISOR_GUIDE.value,
            }
    
    def _supervisor_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Supervisor guidance node.
        Provides guidance when executor is stuck or uncertain.
        """
        reason = state.get("supervisor_reason", "Unknown issue")
        current_idx = state.get("current_macro_step_idx", 0)
        macro_steps = state.get("macro_steps", [])
        
        current_step = macro_steps[current_idx] if current_idx < len(macro_steps) else {}
        step_desc = current_step.get("step", "Unknown")
        
        logger.info(f"🔮 Supervisor intervention: {reason}")
        self._show("supervisor", f"Guiding executor: {reason}", "intervention")
        
        screen = self._capture_screen_context()
        elements_summary = self._summarize_elements(screen.get("visible_elements", [])[:30])
        
        prompt = f"""You are the SUPERVISOR. The executor is stuck and needs guidance.

ORIGINAL TASK: {state['task']}
CURRENT MACRO STEP: {step_desc}
REASON FOR INTERVENTION: {reason}

CURRENT SCREEN:
- App: {screen.get('app_name', 'Unknown')}
- Window: {screen.get('window_title', '')}
- Elements: {elements_summary}

DECIDE what to do:
1. "guide" - Provide specific actions
2. "skip" - Skip this step
3. "abort" - Task is impossible

Output JSON:
{{
    "decision": "guide" | "skip" | "abort",
    "reason": "Explanation",
    "actions": [  // Only if decision is "guide"
        {{"type": "hotkey", "params": {{"keys": ["command", "l"]}}, "description": "Focus URL bar"}}
    ]
}}

Supervisor decision:"""
        
        try:
            response = self.client.generate_json(prompt, temperature=0.3)
            
            decision = response.get("decision", "abort")
            decision_reason = response.get("reason", "Unknown")
            
            self._show("supervisor", f"Decision: {decision} - {decision_reason}", "decision")
            
            intervention = SupervisorIntervention(
                timestamp=datetime.now().isoformat(),
                reason=reason,
                decision=decision,
                correction=decision_reason,
            )
            
            if decision == "abort":
                return {
                    "interventions": [intervention],
                    "phase": AgentPhase.FAILED.value,
                    "error": f"Supervisor aborted: {decision_reason}",
                    "should_abort": True,
                }
            elif decision == "skip":
                return {
                    "interventions": [intervention],
                    "current_macro_step_idx": current_idx + 1,
                    "needs_supervisor": False,
                    "supervisor_reason": None,
                    "phase": AgentPhase.EXECUTING.value,
                }
            else:
                # Execute supervisor-provided actions
                import pyautogui
                
                actions = response.get("actions", [])
                executed = []
                pending_outcomes = []
                
                for action in actions:
                    action_type = action.get("type", "")
                    params = action.get("params", {})
                    description = action.get("description", "")
                    action_start_time = time.time()
                    rating = None
                    
                    try:
                        # ========== CONFIDENCE GATING FOR SUPERVISOR ACTIONS ==========
                        # Rate supervisor actions too, but use a lower threshold since 
                        # the supervisor is already providing corrective guidance
                        if CONFIDENCE_MODEL_AVAILABLE:
                            context = {
                                "current_app": state.get("current_screen", {}).get("app_name", "unknown"),
                                "screen_active": True,
                                "is_supervisor_action": True,  # Flag for special handling
                            }
                            rating = rate_action(
                                action_type,
                                params,
                                context=context
                            )
                            
                            logger.info(f"📊 [Supervisor] Action confidence: {rating.score:.1f}/10 ({rating.level.value})")
                            self._show("supervisor", f"Confidence: {rating.score:.1f}/10", "info")
                            
                            # Supervisor actions use lower threshold (2.0) since they're corrective
                            # But still warn if confidence is very low
                            if rating.score < 2.0:
                                logger.warning(f"⚠️ Very low confidence ({rating.score:.1f}) for supervisor action: {description}")
                                self._show("supervisor", f"Low confidence action - proceeding cautiously", "warning")
                        
                        if action_type == "hotkey":
                            pyautogui.hotkey(*params.get("keys", []))
                            self._smart_wait_after("hotkey")
                        elif action_type == "type":
                            pyautogui.write(params.get("text", ""), interval=0.02)
                            self._smart_wait_after("type")
                        elif action_type == "key":
                            pyautogui.press(params.get("key", ""))
                            self._smart_wait_after("key")
                        elif action_type == "wait":
                            secs = params.get("seconds", 0.5)
                            if self._ui_wait and secs >= 0.3:
                                self._ui_wait.wait_for_ui_stable(
                                    max_wait_ms=int(secs * 1000),
                                    stability_ms=150
                                )
                            else:
                                time.sleep(secs)
                        
                        executed.append(ActionRecord(
                            type=action_type,
                            params=params,
                            description=f"[supervisor] {description}",
                            timestamp=datetime.now().isoformat(),
                            success=True,
                            error=None,
                        ))
                        
                        # Store pending outcome for delayed reward
                        if CONFIDENCE_MODEL_AVAILABLE and rating:
                            pending_outcomes.append({
                                "action_type": action_type,
                                "action_params": params,
                                "rating": rating,
                                "execution_time": time.time() - action_start_time,
                                "context": {"app": state.get("current_screen", {}).get("app_name", "unknown"), "is_supervisor": True}
                            })
                        
                    except Exception as e:
                        logger.warning(f"Supervisor action failed: {e}")
                        
                        # Record immediate failure
                        if CONFIDENCE_MODEL_AVAILABLE and rating:
                            try:
                                record_action_outcome(
                                    action_type=action_type,
                                    action_params=params,
                                    rating=rating,
                                    success=False,
                                    execution_time=time.time() - action_start_time,
                                    context={"app": state.get("current_screen", {}).get("app_name", "unknown"), "is_supervisor": True},
                                    error_type=type(e).__name__
                                )
                            except Exception as outcome_err:
                                logger.debug(f"Could not record failed supervisor action outcome: {outcome_err}")
                
                return {
                    "interventions": [intervention],
                    "executed_actions": executed,
                    "needs_supervisor": False,
                    "supervisor_reason": None,
                    "phase": AgentPhase.EXECUTING.value,
                    "pending_confidence_outcomes": pending_outcomes,  # Include supervisor action outcomes
                }
                
        except Exception as e:
            logger.error(f"Supervisor failed: {e}")
            return {
                "phase": AgentPhase.FAILED.value,
                "error": f"Supervisor error: {e}",
                "should_abort": True,
            }
    
    def _verifier_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Verification node.
        Checks if task is actually complete by analyzing screen state.
        """
        logger.info("🔍 Verifying task completion...")
        self._show("supervisor", "Verifying task completion", "verifying")
        
        screen = self._capture_screen_context()
        elements_summary = self._summarize_elements(screen.get("visible_elements", [])[:30])
        
        prompt = f"""You are the SUPERVISOR. Verify if the task is ACTUALLY complete.

TASK: {state['task']}
EXPECTED OUTCOME: {state.get('expected_outcome', 'Task completed')}
SUCCESS CRITERIA: {state.get('success_criteria', 'Goal achieved')}

FINAL SCREEN:
- App: {screen.get('app_name', 'Unknown')}
- Window: {screen.get('window_title', '')}
- Elements: {elements_summary}

EXECUTION SUMMARY:
- Steps Completed: {state.get('current_macro_step_idx', 0)}/{len(state.get('macro_steps', []))}
- Actions Executed: {len(state.get('executed_actions', []))}
- Interventions: {len(state.get('interventions', []))}

Is the task ACTUALLY complete?

Output JSON:
{{
    "complete": true | false,
    "confidence": 0.0-1.0,
    "reason": "Explanation",
    "what_is_missing": "If incomplete, what needs to be done",
    "corrective_steps": [
        {{"step": "What to do", "context": "What to look for"}}
    ]
}}

Verification:"""
        
        try:
            response = self.client.generate_json(prompt, temperature=0.2)
            
            complete = response.get("complete", False)
            confidence = response.get("confidence", 0.0)
            reason = response.get("reason", "Unknown")
            
            self._show("supervisor", 
                f"{'✅ Complete' if complete else '❌ Incomplete'} ({confidence:.0%}): {reason}",
                "verification")
            
            if complete and confidence >= 0.7:
                logger.info(f"✅ Task verified complete: {reason}")
                # COMMIT DELAYED REWARDS: Now we know the task truly succeeded
                self._commit_pending_outcomes(state, success=True)
                return {
                    "verification_complete": True,
                    "verification_confidence": confidence,
                    "verification_reason": reason,
                    "phase": AgentPhase.COMPLETED.value,
                    "completed_at": datetime.now().isoformat(),
                    "pending_confidence_outcomes": [],  # Clear after commitment
                }
            else:
                corrective = response.get("corrective_steps", [])
                # COMMIT DELAYED REWARDS: Actions didn't achieve the goal
                self._commit_pending_outcomes(state, success=False)
                return {
                    "verification_complete": False,
                    "verification_confidence": confidence,
                    "verification_reason": reason,
                    "corrective_steps": corrective,
                    "phase": AgentPhase.EVOLVING.value,
                    "pending_confidence_outcomes": [],  # Clear after commitment
                }
                
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return {
                "verification_complete": False,
                "verification_confidence": 0.0,
                "verification_reason": f"Error: {e}",
                "phase": AgentPhase.EVOLVING.value,
            }
    
    def _evolver_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Task evolution node.
        Modifies the plan when verification fails.
        """
        evolution_count = state.get("evolution_count", 0) + 1
        
        if evolution_count > state.get("max_evolutions", 3):
            return {
                "evolution_count": evolution_count,
                "phase": AgentPhase.FAILED.value,
                "error": "Max evolutions exceeded",
                "should_abort": True,
            }
        
        logger.info(f"🔄 Evolving task (attempt {evolution_count})...")
        self._show("supervisor", "Evolving task plan", "evolving")
        
        corrective_steps = state.get("corrective_steps", [])
        
        if corrective_steps:
            # Add corrective steps to macro plan
            logger.info(f"   Adding {len(corrective_steps)} corrective steps")
            
            current_steps = state.get("macro_steps", [])
            new_steps = current_steps + corrective_steps
            
            for step in corrective_steps:
                self._show("supervisor", f"New step: {step.get('step', 'Unknown')}", "evolution")
            
            return {
                "macro_steps": new_steps,
                "evolution_count": evolution_count,
                "corrective_steps": [],
                "phase": AgentPhase.EXECUTING.value,
            }
        
        # Generate new steps from current state
        screen = self._capture_screen_context()
        
        prompt = f"""You are the SUPERVISOR taking over planning.
The executor failed to complete the task.

TASK: {state['task']}
WHAT IS MISSING: {state.get('verification_reason', 'Unknown')}
CURRENT APP: {screen.get('app_name', 'Unknown')}

Create new steps to complete the task.

Output JSON:
{{
    "new_steps": [
        {{"step": "What to do", "context": "What to expect"}}
    ]
}}

Evolution:"""
        
        try:
            response = self.client.generate_json(prompt, temperature=0.3)
            new_steps = response.get("new_steps", [])
            
            if new_steps:
                current_steps = state.get("macro_steps", [])
                
                return {
                    "macro_steps": current_steps + new_steps,
                    "evolution_count": evolution_count,
                    "phase": AgentPhase.EXECUTING.value,
                }
            
            return {
                "evolution_count": evolution_count,
                "phase": AgentPhase.FAILED.value,
                "error": "Could not evolve task",
                "should_abort": True,
            }
            
        except Exception as e:
            logger.error(f"Evolution failed: {e}")
            return {
                "evolution_count": evolution_count,
                "phase": AgentPhase.FAILED.value,
                "error": f"Evolution error: {e}",
                "should_abort": True,
            }
    
    def _human_approval_node(self, state: HoudiniAgentState) -> Dict[str, Any]:
        """
        Human-in-the-loop approval node.
        Pauses execution and waits for human input.
        """
        # This is called when we need human approval
        # In a real implementation, this would trigger a UI prompt
        logger.info("⏸️ Awaiting human approval...")
        
        return {
            "awaiting_human_input": True,
            "human_input_prompt": state.get("human_input_prompt", "Approve next action?"),
        }
    
    # ========== ROUTING FUNCTIONS ==========
    
    def _route_after_executor(
        self, state: HoudiniAgentState
    ) -> Literal["supervisor", "verifier", "executor", "end"]:
        """Route after executor node."""
        
        if state.get("should_abort"):
            return "end"
        
        if state.get("needs_supervisor"):
            return "supervisor"
        
        phase = state.get("phase", "")
        
        if phase == AgentPhase.VERIFYING.value:
            return "verifier"
        
        if phase == AgentPhase.COMPLETED.value:
            return "end"
        
        if phase == AgentPhase.FAILED.value:
            return "end"
        
        # Check if all steps done
        current_idx = state.get("current_macro_step_idx", 0)
        macro_steps = state.get("macro_steps", [])
        
        if current_idx >= len(macro_steps):
            return "verifier"
        
        return "executor"
    
    def _route_after_verifier(
        self, state: HoudiniAgentState
    ) -> Literal["evolver", "end"]:
        """Route after verifier node."""
        
        if state.get("should_abort"):
            return "end"
        
        if state.get("verification_complete"):
            return "end"
        
        return "evolver"
    
    def _route_after_evolver(
        self, state: HoudiniAgentState
    ) -> Literal["executor", "end"]:
        """Route after evolver node."""
        
        if state.get("should_abort"):
            return "end"
        
        phase = state.get("phase", "")
        
        if phase == AgentPhase.FAILED.value:
            return "end"
        
        return "executor"
    
    # ========== HELPER METHODS ==========
    
    def _capture_screen_context(self) -> ScreenContext:
        """Capture current screen state."""
        try:
            from ..utils.accessibility_reader import get_frontmost_app, get_ui_elements_applescript
            
            app_info = get_frontmost_app()
            elements = get_ui_elements_applescript(max_elements=50)
            
            return ScreenContext(
                app_name=app_info.get("app", "Unknown"),
                window_title=app_info.get("window", ""),
                visible_elements=elements,
                screenshot_path=None,
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            logger.warning(f"Screen capture failed: {e}")
            return ScreenContext(
                app_name="Unknown",
                window_title="",
                visible_elements=[],
                screenshot_path=None,
                timestamp=datetime.now().isoformat(),
            )
    
    def _get_current_app_name(self) -> Optional[str]:
        """Get current frontmost app name."""
        try:
            from ..utils.accessibility_reader import get_frontmost_app
            return get_frontmost_app().get("app")
        except:
            return None
    
    def _commit_pending_outcomes(self, state: HoudiniAgentState, success: bool):
        """
        Commit all pending confidence outcomes to the ExecutionConfidenceModel.
        
        DELAYED REWARD PATTERN:
        - Actions are executed and their ratings are stored as "pending"
        - Only when the Verifier confirms the task outcome do we commit these outcomes
        - This prevents reward poisoning: clicking the wrong element "succeeds"
          mechanically but fails semantically
        
        Args:
            state: Current agent state containing pending_confidence_outcomes
            success: Whether the task was verified as successful
        """
        if not CONFIDENCE_MODEL_AVAILABLE:
            return
        
        pending = state.get("pending_confidence_outcomes", [])
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
    
    def _summarize_elements(self, elements: List[Dict]) -> str:
        """Summarize visible UI elements."""
        if not elements:
            return "(no elements)"
        
        summary = []
        for e in elements[:15]:
            role = e.get("role", "unknown")
            name = e.get("name", "")[:30]
            if name:
                summary.append(f"{role}: {name}")
        
        return ", ".join(summary) if summary else "(no named elements)"
    
    def _vision_click(self, element_description: str, execution_params: Optional[Dict] = None) -> Dict:
        """Handle click actions that need screen analysis."""
        try:
            from ..agents.vision_executor import execute_vision_action
            
            # Pass pre-calculated execution params from probability model
            # This ensures dynamic thresholds (min_match_probability, verification_strictness)
            # are actually used by the vision executor
            return execute_vision_action(
                self.client, 
                f"click {element_description}",
                execution_params=execution_params
            )
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _show(self, component: str, message: str, msg_type: str = "info"):
        """Show message in thinking window."""
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
    
    # ========== PUBLIC API ==========
    
    def execute(self, task: str, thread_id: Optional[str] = None) -> Dict:
        """
        Execute a task using the LangGraph-based system.
        
        Args:
            task: Natural language task description
            thread_id: Optional thread ID for checkpointing (allows resume)
        
        Returns:
            Execution result dict
        """
        start_time = time.time()
        
        logger.info(f"🎯 LangGraph Coordinator starting: {task}")
        
        if self.enable_thinking_window:
            set_window_status(f"Planning: {task[:40]}...")
        
        # Create initial state
        initial_state = create_initial_state(
            task=task,
            max_iterations=self.max_iterations,
            max_evolutions=self.max_evolutions,
        )
        
        # Configure execution
        config = {"configurable": {"thread_id": thread_id or initial_state["task_id"]}}
        
        try:
            # Run the graph
            final_state = None
            
            for event in self.app.stream(initial_state, config):
                # Event contains the node name and output
                for node_name, node_output in event.items():
                    logger.debug(f"Node '{node_name}' output: {node_output}")
                    final_state = node_output if isinstance(node_output, dict) else None
            
            # Get final state from checkpoint
            final_state = self.app.get_state(config).values
            
            elapsed = time.time() - start_time
            
            success = final_state.get("phase") == AgentPhase.COMPLETED.value
            
            if self.enable_thinking_window:
                if success:
                    set_window_status("✅ Completed")
                    show_thinking("system", f"Task completed in {elapsed:.1f}s", "success")
                else:
                    set_window_status("❌ Failed")
                    show_thinking("system", f"Task failed: {final_state.get('error')}", "error")
            
            logger.info("\n" + "=" * 50)
            logger.info("📊 Execution Complete")
            logger.info("=" * 50)
            logger.info(f"   Success: {success}")
            logger.info(f"   Time: {elapsed:.1f}s")
            logger.info(f"   Actions: {len(final_state.get('executed_actions', []))}")
            logger.info(f"   Interventions: {len(final_state.get('interventions', []))}")
            logger.info(f"   Evolutions: {final_state.get('evolution_count', 0)}")
            
            return {
                "success": success,
                "elapsed": elapsed,
                "phase": final_state.get("phase"),
                "error": final_state.get("error"),
                "total_actions": len(final_state.get("executed_actions", [])),
                "interventions": len(final_state.get("interventions", [])),
                "evolution_count": final_state.get("evolution_count", 0),
                "thread_id": config["configurable"]["thread_id"],
                "state": final_state,
            }
            
        except Exception as e:
            logger.error(f"❌ LangGraph execution error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "elapsed": time.time() - start_time}
    
    def resume(self, thread_id: str, human_input: Optional[str] = None) -> Dict:
        """
        Resume a previously checkpointed execution.
        
        Args:
            thread_id: The thread ID to resume
            human_input: Optional human input if paused for approval
        
        Returns:
            Execution result dict
        """
        config = {"configurable": {"thread_id": thread_id}}
        
        # Get current state
        state = self.app.get_state(config)
        
        if not state.values:
            return {"success": False, "error": "No checkpoint found for thread_id"}
        
        logger.info(f"🔄 Resuming execution from checkpoint: {thread_id}")
        
        # If human input provided, update state
        updates = {}
        if human_input is not None:
            updates["human_input_response"] = human_input
            updates["awaiting_human_input"] = False
        
        if updates:
            self.app.update_state(config, updates)
        
        # Continue execution
        return self.execute(state.values["task"], thread_id=thread_id)
    
    def get_state(self, thread_id: str) -> Optional[Dict]:
        """
        Get the current state for a thread.
        
        Args:
            thread_id: The thread ID
        
        Returns:
            Current state dict or None
        """
        config = {"configurable": {"thread_id": thread_id}}
        state = self.app.get_state(config)
        return state.values if state else None
    
    def get_graph_visualization(self) -> str:
        """Get ASCII visualization of the graph structure."""
        return """
LangGraph Execution Flow:
========================

    ┌─────────────┐
    │  __start__  │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   analyze   │  (probability model)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   planner   │  (macro planning)
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐◄──────────────────┐
    │  executor   │  (micro actions)  │
    └──────┬──────┘                   │
           │                          │
           ▼                          │
    ┌─────────────┐   needs_help      │
    │   router    │───────────────────┤
    └──────┬──────┘                   │
           │ all_done                 │
           ▼                          │
    ┌─────────────┐                   │
    │  verifier   │                   │
    └──────┬──────┘                   │
           │                          │
           ▼                          │
    ┌─────────────┐   incomplete      │
    │   evolver   │───────────────────┘
    └──────┬──────┘
           │ complete
           ▼
    ┌─────────────┐
    │   __end__   │
    └─────────────┘
"""


def run_with_langgraph(
    task: str,
    model: str = "qwen2.5-coder:32b",
    cloud_endpoint: Optional[str] = None,
    enable_thinking_window: bool = True,
    checkpoint_path: Optional[str] = None,
) -> Dict:
    """
    Convenience function to run a task with LangGraph.
    
    Args:
        task: Natural language task description
        model: Ollama model to use
        cloud_endpoint: Optional cloud endpoint
        enable_thinking_window: Whether to show thinking window
        checkpoint_path: SQLite path for persistent checkpoints
    
    Returns:
        Execution result dict
    """
    client = OllamaClient(model_name=model, cloud_endpoint=cloud_endpoint)
    
    coordinator = LangGraphCoordinator(
        client=client,
        enable_thinking_window=enable_thinking_window,
        checkpoint_path=checkpoint_path,
    )
    
    return coordinator.execute(task)
