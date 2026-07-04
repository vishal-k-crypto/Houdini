# Loop module for continuous execution
#
# PRIMARY ARCHITECTURE: AdaptiveLoopCoordinator (default)
#   - Macro planner → micro executor → adaptive supervisor
#   - Self-healing with real-time task evolution
#
# EXPERIMENTAL: LangGraphCoordinator (opt-in via --langgraph)
#   - State machine with built-in checkpointing
#
# DEPRECATED: LoopCoordinator / ExecutorLoop / SupervisorLoop (--legacy)
#   - Original architecture, kept for backwards compatibility
#
from .loop_state import LoopState
from .executor_loop import ExecutorLoop  # Used by legacy LoopCoordinator
from .supervisor_loop import SupervisorLoop  # Used by legacy LoopCoordinator
from .loop_coordinator import LoopCoordinator  # DEPRECATED: use AdaptiveLoopCoordinator
from .recovery_handler import RecoveryHandler, RecoveryRouter, FailureCategory, RecoveryStrategy
from .adaptive_coordinator import AdaptiveLoopCoordinator, AdaptiveState, AdaptivePhase
from .fast_executor import FastExecutor, ExecutionResult

# LangGraph-based coordinator (new architecture)
try:
    from .langgraph_coordinator import LangGraphCoordinator, run_with_langgraph
    from .langgraph_state import (
        HoudiniAgentState, 
        AgentPhase as LangGraphAgentPhase,
        create_initial_state,
    )
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    LangGraphCoordinator = None
    run_with_langgraph = None
    HoudiniAgentState = None
    LangGraphAgentPhase = None
    create_initial_state = None

__all__ = [
    "LoopState", 
    "ExecutorLoop", 
    "SupervisorLoop", 
    "LoopCoordinator", 
    "RecoveryHandler",
    "RecoveryRouter",
    "FailureCategory",
    "RecoveryStrategy",
    "AdaptiveLoopCoordinator",
    "AdaptiveState",
    "AdaptivePhase",
    "FastExecutor",
    "ExecutionResult",
    # LangGraph exports
    "LangGraphCoordinator",
    "run_with_langgraph",
    "HoudiniAgentState",
    "LangGraphAgentPhase",
    "create_initial_state",
    "LANGGRAPH_AVAILABLE",
]
