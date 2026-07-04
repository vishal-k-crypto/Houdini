"""
Centralized configuration for Houdini Agent.

All tunable parameters live here. Values are loaded from (in priority order):
1. Environment variables (highest priority)
2. .env file (auto-loaded)
3. Defaults defined below (lowest priority)

Usage:
    from config.settings import settings
    model = settings.ollama_default_model
    threshold = settings.completion_confidence_threshold
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Load .env file if present (does NOT override existing env vars)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(_env_path, override=False)
except ImportError:
    pass

# Project root (houdini-agent/)
PROJECT_ROOT = Path(__file__).parent.parent


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key, str(default)))


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, str(default)).lower()
    return val in ("true", "1", "yes")


@dataclass(frozen=True)
class HoudiniSettings:
    """All tunable settings for the Houdini Agent."""

    # ================================================================
    # Models
    # ================================================================
    ollama_default_model: str = field(
        default_factory=lambda: _env("OLLAMA_DEFAULT_MODEL", "qwen3-coder:480b-cloud")
    )
    ollama_endpoint: Optional[str] = field(
        default_factory=lambda: os.environ.get("OLLAMA_ENDPOINT")
    )
    ollama_embedding_model: str = field(
        default_factory=lambda: _env("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )
    supervisor_model: str = field(
        default_factory=lambda: _env("SUPERVISOR_MODEL", "qwen2.5-coder:32b")
    )
    local_supervisor_model_path: str = field(
        default_factory=lambda: _env(
            "LOCAL_SUPERVISOR_MODEL_PATH",
            str(PROJECT_ROOT / "models" / "qwen2.5-7b-instruct-q5_k_m.gguf")
        )
    )
    tinyclick_model_id: str = field(
        default_factory=lambda: _env("TINYCLICK_MODEL_ID", "Krystianz/TinyClick")
    )
    gemini_model: str = field(
        default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.0-flash-exp")
    )

    # ================================================================
    # LLM Parameters
    # ================================================================
    ollama_default_temperature: float = field(
        default_factory=lambda: _env_float("OLLAMA_DEFAULT_TEMPERATURE", 0.7)
    )
    ollama_max_tokens: int = field(
        default_factory=lambda: _env_int("OLLAMA_MAX_TOKENS", 4096)
    )
    ollama_retry_count: int = field(
        default_factory=lambda: _env_int("OLLAMA_RETRY_COUNT", 3)
    )
    planner_temperature: float = field(
        default_factory=lambda: _env_float("PLANNER_TEMPERATURE", 0.3)
    )
    supervisor_analysis_temperature: float = field(
        default_factory=lambda: _env_float("SUPERVISOR_ANALYSIS_TEMPERATURE", 0.3)
    )
    validator_temperature: float = field(
        default_factory=lambda: _env_float("VALIDATOR_TEMPERATURE", 0.1)
    )
    validator_max_tokens: int = field(
        default_factory=lambda: _env_int("VALIDATOR_MAX_TOKENS", 128)
    )

    # ================================================================
    # Confidence Thresholds
    # ================================================================
    completion_confidence_threshold: float = field(
        default_factory=lambda: _env_float("COMPLETION_CONFIDENCE_THRESHOLD", 0.75)
    )
    task_verifier_confidence_threshold: float = field(
        default_factory=lambda: _env_float("TASK_VERIFIER_CONFIDENCE_THRESHOLD", 0.65)
    )
    supervisor_confidence_threshold: float = field(
        default_factory=lambda: _env_float("SUPERVISOR_CONFIDENCE_THRESHOLD", 0.7)
    )
    pattern_similarity_threshold: float = field(
        default_factory=lambda: _env_float("PATTERN_SIMILARITY_THRESHOLD", 0.7)
    )
    high_confidence_pattern_threshold: float = field(
        default_factory=lambda: _env_float("HIGH_CONFIDENCE_PATTERN_THRESHOLD", 0.85)
    )
    zero_element_screenshot_cap: float = field(
        default_factory=lambda: _env_float("ZERO_ELEMENT_SCREENSHOT_CAP", 0.80)
    )
    zero_element_no_screenshot_cap: float = field(
        default_factory=lambda: _env_float("ZERO_ELEMENT_NO_SCREENSHOT_CAP", 0.65)
    )

    # ================================================================
    # Execution Limits
    # ================================================================
    max_iterations: int = field(
        default_factory=lambda: _env_int("MAX_ITERATIONS", 100)
    )
    max_step_attempts: int = field(
        default_factory=lambda: _env_int("MAX_STEP_ATTEMPTS", 5)
    )
    max_evolution_attempts: int = field(
        default_factory=lambda: _env_int("MAX_EVOLUTION_ATTEMPTS", 3)
    )
    vision_action_max_attempts: int = field(
        default_factory=lambda: _env_int("VISION_ACTION_MAX_ATTEMPTS", 3)
    )
    max_retries: int = field(
        default_factory=lambda: _env_int("MAX_RETRIES", 5)
    )

    # ================================================================
    # Timeouts (seconds)
    # ================================================================
    ollama_generate_timeout: int = field(
        default_factory=lambda: _env_int("OLLAMA_GENERATE_TIMEOUT", 60)
    )
    gemini_cli_timeout: int = field(
        default_factory=lambda: _env_int("GEMINI_CLI_TIMEOUT", 30)
    )
    screen_capture_timeout: int = field(
        default_factory=lambda: _env_int("SCREEN_CAPTURE_TIMEOUT", 5)
    )
    stuck_detection_threshold: float = field(
        default_factory=lambda: _env_float("STUCK_DETECTION_THRESHOLD", 15.0)
    )
    stuck_timeout: float = field(
        default_factory=lambda: _env_float("STUCK_TIMEOUT", 10.0)
    )
    ui_settle_wait: float = field(
        default_factory=lambda: _env_float("UI_SETTLE_WAIT", 0.5)
    )
    browser_load_wait: int = field(
        default_factory=lambda: _env_int("BROWSER_LOAD_WAIT", 8)
    )
    action_delay: float = field(
        default_factory=lambda: _env_float("ACTION_DELAY", 0.05)
    )

    # ================================================================
    # File Paths (relative to PROJECT_ROOT)
    # ================================================================
    data_dir: str = field(
        default_factory=lambda: _env("DATA_DIR", str(PROJECT_ROOT / "data"))
    )
    executor_history_file: str = field(
        default_factory=lambda: _env(
            "EXECUTOR_HISTORY_FILE",
            str(PROJECT_ROOT / "data" / "executor_history.json")
        )
    )
    replay_sessions_dir: str = field(
        default_factory=lambda: _env(
            "REPLAY_SESSIONS_DIR",
            str(PROJECT_ROOT / "data" / "replay_sessions")
        )
    )
    screenshots_dir: str = field(
        default_factory=lambda: _env(
            "SCREENSHOTS_DIR",
            str(PROJECT_ROOT / "data" / "screenshots")
        )
    )
    training_sessions_dir: str = field(
        default_factory=lambda: _env(
            "TRAINING_SESSIONS_DIR",
            str(PROJECT_ROOT / "data" / "training_sessions")
        )
    )
    tinyclick_venv_path: str = field(
        default_factory=lambda: _env("TINYCLICK_VENV_PATH", ".tinyclick-venv")
    )

    # ================================================================
    # Screen & Display
    # ================================================================
    fallback_screen_width: int = field(
        default_factory=lambda: _env_int("SCREEN_WIDTH", 1920)
    )
    fallback_screen_height: int = field(
        default_factory=lambda: _env_int("SCREEN_HEIGHT", 1080)
    )

    # ================================================================
    # Smart Router
    # ================================================================
    smart_router_enabled: bool = field(
        default_factory=lambda: _env_bool("HOUDINI_SMART_ROUTER_ENABLED", False)
    )
    smart_router_prefer_local: bool = field(
        default_factory=lambda: _env_bool("HOUDINI_PREFER_LOCAL", False)
    )
    smart_router_budget_cap_usd: Optional[float] = field(
        default_factory=lambda: _env_float("HOUDINI_BUDGET_CAP_USD", 0.0) or None
    )
    smart_router_latency_budget_ms: Optional[float] = field(
        default_factory=lambda: _env_float("HOUDINI_LATENCY_BUDGET_MS", 0.0) or None
    )

    # ================================================================
    # Infrastructure
    # ================================================================
    redis_url: str = field(
        default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379")
    )
    worker_id: str = field(
        default_factory=lambda: _env("WORKER_ID", "worker-default")
    )

    # ================================================================
    # Authentication (Phase 4)
    # ================================================================
    auth_enabled: bool = field(
        default_factory=lambda: _env_bool("HOUDINI_AUTH_ENABLED", False)
    )
    jwt_secret: str = field(
        default_factory=lambda: _env("HOUDINI_JWT_SECRET", "")
    )
    jwt_expire_minutes: int = field(
        default_factory=lambda: _env_int("HOUDINI_JWT_EXPIRE_MINUTES", 480)
    )

    # ================================================================
    # Task Scheduling (Phase 4)
    # ================================================================
    queue_max_size: int = field(
        default_factory=lambda: _env_int("HOUDINI_QUEUE_MAX_SIZE", 1000)
    )
    scheduler_max_workers: int = field(
        default_factory=lambda: _env_int("HOUDINI_SCHEDULER_WORKERS", 1)
    )
    scheduler_default_timeout: float = field(
        default_factory=lambda: _env_float("HOUDINI_SCHEDULER_TIMEOUT", 3600.0)
    )


# Singleton instance — import this everywhere
settings = HoudiniSettings()
