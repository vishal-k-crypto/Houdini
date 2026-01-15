# Loop module for continuous execution
from .loop_state import LoopState
from .executor_loop import ExecutorLoop
from .supervisor_loop import SupervisorLoop
from .loop_coordinator import LoopCoordinator
from .recovery_handler import RecoveryHandler
from .adaptive_coordinator import AdaptiveLoopCoordinator, AdaptiveState, AdaptivePhase

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
    "AdaptiveLoopCoordinator",
    "AdaptiveState",
    "AdaptivePhase",
    # LangGraph exports
    "LangGraphCoordinator",
    "run_with_langgraph",
    "HoudiniAgentState",
    "LangGraphAgentPhase",
    "create_initial_state",
    "LANGGRAPH_AVAILABLE",
]
