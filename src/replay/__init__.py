"""
Replay Module - Time Travel Debugging for Houdini Agent.

Provides the ability to replay past executions step-by-step, showing:
- Cursor positions and movements
- Thinking window content at each moment
- Screenshots at checkpoints
- Action timing and success/failure states

Usage:
    python -m src.main --replay                    # Interactive session picker
    python -m src.main --replay <task_id>          # Replay specific task
    python -m src.main --replay --list             # List available sessions
"""

from .execution_logger import ExecutionLogger, ExecutionEvent, EventType
from .replay_engine import ReplayEngine, ReplaySession
from .replay_ui import ReplayUI

__all__ = [
    'ExecutionLogger',
    'ExecutionEvent', 
    'EventType',
    'ReplayEngine',
    'ReplaySession',
    'ReplayUI',
]
