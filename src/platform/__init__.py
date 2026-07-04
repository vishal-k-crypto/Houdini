"""
Cross-platform abstraction layer for Houdini Agent.

Provides unified interfaces for accessibility, screen capture, and cursor
control across macOS, Linux, and Windows.

Usage:
    from src.platform import get_platform
    platform = get_platform()
    tree = platform.accessibility.get_ui_tree()
    platform.screen.capture("/tmp/shot.png")
    platform.cursor.move_to(100, 200)
"""

from .factory import get_platform, PlatformBundle

__all__ = ["get_platform", "PlatformBundle"]
