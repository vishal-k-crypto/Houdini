"""
Abstract base classes for platform-specific backends.

Every platform (macOS, Linux, Windows) must implement these interfaces.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Unified UI element (platform-agnostic) ─────────────────────────

@dataclass
class UINode:
    """Platform-agnostic representation of a UI element."""

    role: str  # e.g. "button", "textField", "window"
    name: Optional[str] = None  # label / title
    value: Optional[str] = None
    description: Optional[str] = None
    position: Optional[Tuple[int, int]] = None  # (x, y) top-left origin
    size: Optional[Tuple[int, int]] = None  # (width, height)
    enabled: bool = True
    focused: bool = False
    actions: List[str] = field(default_factory=list)
    children: List["UINode"] = field(default_factory=list)
    native_handle: Any = None  # opaque platform reference

    @property
    def center(self) -> Optional[Tuple[int, int]]:
        if self.position and self.size:
            x, y = self.position
            w, h = self.size
            return (x + w // 2, y + h // 2)
        return None

    @property
    def bounds(self) -> Optional[Tuple[int, int, int, int]]:
        if self.position and self.size:
            x, y = self.position
            w, h = self.size
            return (x, y, x + w, y + h)
        return None

    def __str__(self):
        text = self.name or self.value or self.description or ""
        pos = f"at {self.position}" if self.position else ""
        return f"[{self.role}] '{text}' {pos}"


# ── Accessibility backend ──────────────────────────────────────────

class AccessibilityBackend(ABC):
    """Read and manipulate the GUI accessibility tree."""

    @abstractmethod
    def get_ui_tree(self, max_depth: int = 8) -> Optional[UINode]:
        """Return the UI tree for the frontmost application."""

    @abstractmethod
    def find_elements_by_role(self, role: str) -> List[UINode]:
        """Find all elements with a specific role."""

    @abstractmethod
    def find_elements_by_text(self, text: str) -> List[UINode]:
        """Find elements whose name/value/description contain *text*."""

    @abstractmethod
    def find_element_by_text(self, text: str) -> Optional[UINode]:
        """Return the first element matching *text*."""

    @abstractmethod
    def perform_action(self, node: UINode, action: str = "press") -> bool:
        """Execute an action (press, show_menu, set_value, …)."""

    @abstractmethod
    def set_value(self, node: UINode, value: str) -> bool:
        """Set the value of a text-entry element."""

    @abstractmethod
    def get_element_at_position(self, x: int, y: int) -> Optional[UINode]:
        """Return the UI element at screen coordinates (top-left origin)."""

    @abstractmethod
    def get_frontmost_app_info(self) -> Dict[str, str]:
        """Return ``{"app": …, "window": …}`` for the frontmost app."""

    @abstractmethod
    def get_running_apps(self) -> List[Dict[str, Any]]:
        """List running GUI applications."""

    def invalidate_cache(self):
        """Flush any element caches."""


# ── Screen capture backend ─────────────────────────────────────────

class ScreenCaptureBackend(ABC):
    """Capture the screen to a file or raw bytes."""

    @abstractmethod
    def capture(self, path: str) -> bool:
        """Capture the full screen and save to *path*. Return True on success."""

    @abstractmethod
    def capture_bytes(self) -> bytes:
        """Capture the full screen as PNG bytes."""

    @abstractmethod
    def get_screen_size(self) -> Tuple[int, int]:
        """Return (width, height) in logical pixels."""

    @abstractmethod
    def get_scale_factor(self) -> float:
        """Return the display scale factor (e.g. 2.0 for Retina)."""


# ── Cursor / input backend ─────────────────────────────────────────

class CursorBackend(ABC):
    """Mouse and keyboard control."""

    @abstractmethod
    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        """Move the cursor to (x, y)."""

    @abstractmethod
    def click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Click at the current position, or at (x, y) if given."""

    @abstractmethod
    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Double-click."""

    @abstractmethod
    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Right-click / context-click."""

    @abstractmethod
    def type_text(self, text: str, interval: float = 0.0) -> None:
        """Type a string character-by-character."""

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """Press a keyboard shortcut (e.g. ``hotkey("ctrl", "c")``)."""

    @abstractmethod
    def key_press(self, key: str) -> None:
        """Press and release a single key."""

    @abstractmethod
    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Scroll *clicks* notches (positive = up, negative = down)."""

    @abstractmethod
    def get_position(self) -> Tuple[int, int]:
        """Return the current cursor position."""


# ── Health-check backend ───────────────────────────────────────────

class HealthCheckBackend(ABC):
    """Platform-specific pre-flight checks."""

    @abstractmethod
    def check_accessibility_permission(self) -> Tuple[str, str]:
        """Return (status_emoji, description)."""

    @abstractmethod
    def check_screen_capture_permission(self) -> Tuple[str, str]:
        """Return (status_emoji, description)."""
