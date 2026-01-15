"""
Supervisor module for Houdini Agent.

Contains:
- OllamaSupervisor: LLM-based supervision using Qwen
- Supervisor (qwen_validator): Local validation with llama.cpp
- SemanticChecker: Fast dual-path validation without LLM calls
"""

from .ollama_supervisor import OllamaSupervisor, ExecutorHistory
from .qwen_validator import Supervisor
from .semantic_checker import (
    SemanticChecker,
    SemanticCheckResult,
    SemanticMismatchType,
    get_semantic_checker,
    quick_semantic_check,
)

__all__ = [
    # LLM-based supervisors
    "OllamaSupervisor",
    "ExecutorHistory",
    "Supervisor",
    # Fast semantic checking
    "SemanticChecker",
    "SemanticCheckResult",
    "SemanticMismatchType",
    "get_semantic_checker",
    "quick_semantic_check",
]
