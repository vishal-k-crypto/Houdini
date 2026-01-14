"""
UI components for Houdini Agent.
"""

from .thinking_window import (
    ThinkingWindow,
    get_thinking_window,
    start_thinking_window,
    stop_thinking_window,
    show_thinking,
    show_planner_thinking,
    show_executor_thinking,
    show_supervisor_thinking,
    set_window_status
)

__all__ = [
    'ThinkingWindow',
    'get_thinking_window',
    'start_thinking_window',
    'stop_thinking_window',
    'show_thinking',
    'show_planner_thinking',
    'show_executor_thinking',
    'show_supervisor_thinking',
    'set_window_status'
]
