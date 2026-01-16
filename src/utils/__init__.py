# Utils package - core utilities for Houdini Agent

from .pattern_store import pattern_store, PatternStore, Pattern
from .choice_tracker import choice_tracker, ChoiceTracker
from .action_optimizer import action_optimizer, ActionOptimizer
from .execution_confidence import (
    ExecutionConfidenceModel,
    ConfidenceRating,
    ConfidenceLevel,
    ActionDecision,
    get_confidence_model,
    rate_action,
    should_execute_action,
    record_action_outcome,
)
from .lesson_store import lesson_store, LessonStore, Lesson
from .embedding_client import embedding_client, EmbeddingClient

# New modules for improved learning
try:
    from .app_knowledge import app_knowledge, AppKnowledge, AppProfile
    from .enhanced_rl import enhanced_rl_agent, EnhancedRLAgent
    APP_KNOWLEDGE_AVAILABLE = True
    ENHANCED_RL_AVAILABLE = True
except ImportError:
    app_knowledge = None
    enhanced_rl_agent = None
    APP_KNOWLEDGE_AVAILABLE = False
    ENHANCED_RL_AVAILABLE = False

# Web interaction policy for vision-first web interactions
try:
    from .web_interaction_policy import (
        get_policy, 
        WebInteractionPolicy, 
        check_action_requires_vision,
        validate_hotkey_for_web,
        InteractionMode
    )
    WEB_POLICY_AVAILABLE = True
except ImportError:
    get_policy = None
    WebInteractionPolicy = None
    check_action_requires_vision = None
    validate_hotkey_for_web = None
    InteractionMode = None
    WEB_POLICY_AVAILABLE = False

__all__ = [
    "pattern_store",
    "PatternStore", 
    "Pattern",
    "choice_tracker",
    "ChoiceTracker",
    "action_optimizer",
    "ActionOptimizer",
    # Execution Confidence
    "ExecutionConfidenceModel",
    "ConfidenceRating",
    "ConfidenceLevel",
    "ActionDecision",
    "get_confidence_model",
    "rate_action",
    "should_execute_action",
    "record_action_outcome",
    # Lesson Store (RAG-based learning)
    "lesson_store",
    "LessonStore",
    "Lesson",
    "embedding_client",
    "EmbeddingClient",
    # App Knowledge & Enhanced RL
    "app_knowledge",
    "AppKnowledge",
    "AppProfile",
    "enhanced_rl_agent",
    "EnhancedRLAgent",
    "APP_KNOWLEDGE_AVAILABLE",
    "ENHANCED_RL_AVAILABLE",
    # Web Interaction Policy
    "get_policy",
    "WebInteractionPolicy",
    "check_action_requires_vision",
    "validate_hotkey_for_web",
    "InteractionMode",
    "WEB_POLICY_AVAILABLE",
]
