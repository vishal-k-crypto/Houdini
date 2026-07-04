"""
Platform factory — detects the current OS and returns the correct backends.

Usage:
    from src.platform import get_platform
    p = get_platform()
    tree = p.accessibility.get_ui_tree()
"""

import sys
from dataclasses import dataclass
from typing import Optional

from ..utils.logging import logger
from .base import (
    AccessibilityBackend,
    CursorBackend,
    HealthCheckBackend,
    ScreenCaptureBackend,
)


@dataclass
class PlatformBundle:
    """Holds one instance of each backend for the detected platform."""

    name: str  # "macos", "linux", "windows"
    accessibility: AccessibilityBackend
    screen: ScreenCaptureBackend
    cursor: CursorBackend
    health: HealthCheckBackend


_cached_platform: Optional[PlatformBundle] = None


def get_platform(force: Optional[str] = None) -> PlatformBundle:
    """
    Return a ``PlatformBundle`` for the current OS (or *force* override).

    The result is cached so repeated calls are cheap.

    Args:
        force: Override auto-detection with ``"macos"``, ``"linux"``, or
               ``"windows"``.  Mostly useful for testing.
    """
    global _cached_platform
    if _cached_platform is not None and force is None:
        return _cached_platform

    platform_name = force or _detect_platform()

    if platform_name == "macos":
        bundle = _build_macos()
    elif platform_name == "linux":
        bundle = _build_linux()
    elif platform_name == "windows":
        bundle = _build_windows()
    else:
        raise RuntimeError(f"Unsupported platform: {platform_name}")

    if force is None:
        _cached_platform = bundle
    return bundle


def _detect_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    else:
        return "linux"


# ── Builders ────────────────────────────────────────────────────────


def _build_macos() -> PlatformBundle:
    from .macos_backend import (
        MacOSAccessibility,
        MacOSCursor,
        MacOSHealthCheck,
        MacOSScreenCapture,
    )

    logger.info("Platform: macOS (PyObjC + screencapture)")
    return PlatformBundle(
        name="macos",
        accessibility=MacOSAccessibility(),
        screen=MacOSScreenCapture(),
        cursor=MacOSCursor(),
        health=MacOSHealthCheck(),
    )


def _build_linux() -> PlatformBundle:
    from .linux_backend import (
        LinuxAccessibility,
        LinuxCursor,
        LinuxHealthCheck,
        LinuxScreenCapture,
    )

    logger.info("Platform: Linux (AT-SPI2 + scrot/grim)")
    return PlatformBundle(
        name="linux",
        accessibility=LinuxAccessibility(),
        screen=LinuxScreenCapture(),
        cursor=LinuxCursor(),
        health=LinuxHealthCheck(),
    )


def _build_windows() -> PlatformBundle:
    from .windows_backend import (
        WindowsAccessibility,
        WindowsCursor,
        WindowsHealthCheck,
        WindowsScreenCapture,
    )

    logger.info("Platform: Windows (UI Automation + PIL)")
    return PlatformBundle(
        name="windows",
        accessibility=WindowsAccessibility(),
        screen=WindowsScreenCapture(),
        cursor=WindowsCursor(),
        health=WindowsHealthCheck(),
    )
