"""
macOS backend — wraps existing PyObjC accessibility, screencapture, and
cursor controller behind the cross-platform interfaces.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logging import logger
from .base import (
    AccessibilityBackend,
    CursorBackend,
    HealthCheckBackend,
    ScreenCaptureBackend,
    UINode,
)

# ── Accessibility ──────────────────────────────────────────────────


class MacOSAccessibility(AccessibilityBackend):
    """macOS AXUIElement-based accessibility backend."""

    def __init__(self):
        from ..utils.accessibility_api import AccessibilityAPI, AXElement

        self._api = AccessibilityAPI()
        self._AXElement = AXElement

    # -- helpers -------------------------------------------------

    def _to_node(self, ax: Any) -> UINode:
        """Convert an ``AXElement`` to a ``UINode``."""
        children = [self._to_node(c) for c in (ax.children or [])]
        return UINode(
            role=ax.role or "",
            name=ax.title,
            value=ax.value,
            description=ax.description,
            position=ax.position,
            size=ax.size,
            enabled=ax.enabled,
            focused=ax.focused,
            actions=[_normalise_action(a) for a in (ax.actions or [])],
            children=children,
            native_handle=ax,
        )

    def _get_native(self, node: UINode) -> Any:
        """Retrieve the backing ``AXElement`` from a UINode."""
        return node.native_handle

    # -- interface -----------------------------------------------

    def get_ui_tree(self, max_depth: int = 8) -> Optional[UINode]:
        tree = self._api.get_ui_tree(max_depth=max_depth)
        return self._to_node(tree) if tree else None

    def find_elements_by_role(self, role: str) -> List[UINode]:
        ax_role = _to_ax_role(role)
        return [self._to_node(e) for e in self._api.find_elements_by_role(ax_role)]

    def find_elements_by_text(self, text: str) -> List[UINode]:
        return [self._to_node(e) for e in self._api.find_elements_by_text(text)]

    def find_element_by_text(self, text: str) -> Optional[UINode]:
        e = self._api.find_element_by_text(text)
        return self._to_node(e) if e else None

    def perform_action(self, node: UINode, action: str = "press") -> bool:
        native = self._get_native(node)
        if native is None:
            return False
        ax_action = _from_normalised_action(action)
        return self._api.perform_action(native, ax_action)

    def set_value(self, node: UINode, value: str) -> bool:
        native = self._get_native(node)
        if native is None:
            return False
        return self._api.set_value(native, value)

    def get_element_at_position(self, x: int, y: int) -> Optional[UINode]:
        e = self._api.get_element_at_position(x, y)
        return self._to_node(e) if e else None

    def get_frontmost_app_info(self) -> Dict[str, str]:
        return self._api.get_frontmost_app_info()

    def get_running_apps(self) -> List[Dict[str, Any]]:
        return self._api.get_running_apps()

    def invalidate_cache(self):
        self._api.invalidate_cache()


# ── Screen capture ─────────────────────────────────────────────────


class MacOSScreenCapture(ScreenCaptureBackend):
    """macOS ``screencapture`` CLI tool."""

    def capture(self, path: str) -> bool:
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-C", path],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0 and Path(path).exists()
        except Exception as exc:
            logger.error(f"screencapture failed: {exc}")
            return False

    def capture_bytes(self) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            if self.capture(tmp_path):
                return Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        # fallback: grey placeholder
        from PIL import Image
        import io

        img = Image.new("RGB", self.get_screen_size(), color="gray")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def get_screen_size(self) -> Tuple[int, int]:
        try:
            import AppKit

            screen = AppKit.NSScreen.mainScreen()
            if screen:
                frame = screen.frame()
                return (int(frame.size.width), int(frame.size.height))
        except Exception:
            pass
        try:
            import pyautogui

            return pyautogui.size()
        except Exception:
            pass
        return (1920, 1080)

    def get_scale_factor(self) -> float:
        try:
            import AppKit

            screen = AppKit.NSScreen.mainScreen()
            if screen:
                return float(screen.backingScaleFactor())
        except Exception:
            pass
        return 1.0


# ── Cursor / input ─────────────────────────────────────────────────


class MacOSCursor(CursorBackend):
    """Wraps the existing human-like cursor + pyautogui."""

    def __init__(self, human_like: bool = True):
        self._human_like = human_like
        self._human_cursor = None
        if human_like:
            try:
                from ..utils.cursor_controller import HumanCursor

                self._human_cursor = HumanCursor()
            except Exception:
                logger.warning("HumanCursor unavailable, falling back to pyautogui")
        import pyautogui

        self._pyag = pyautogui

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        if self._human_cursor:
            self._human_cursor.move_to(x, y)
        else:
            self._pyag.moveTo(x, y, duration=duration)

    def click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if self._human_cursor and x is not None and y is not None:
            self._human_cursor.move_to(x, y)
            self._human_cursor.click()
        elif x is not None and y is not None:
            self._pyag.click(x, y)
        else:
            self._pyag.click()

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
            self._pyag.doubleClick(x, y)
        else:
            self._pyag.doubleClick()

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
            self._pyag.rightClick(x, y)
        else:
            self._pyag.rightClick()

    def type_text(self, text: str, interval: float = 0.0) -> None:
        self._pyag.typewrite(text, interval=interval)

    def hotkey(self, *keys: str) -> None:
        self._pyag.hotkey(*keys)

    def key_press(self, key: str) -> None:
        self._pyag.press(key)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        self._pyag.scroll(clicks, x=x, y=y)

    def get_position(self) -> Tuple[int, int]:
        pos = self._pyag.position()
        return (pos.x, pos.y)


# ── Health checks ──────────────────────────────────────────────────

OK = "✅"
WARN = "⚠️"
FAIL = "❌"


class MacOSHealthCheck(HealthCheckBackend):

    def check_accessibility_permission(self) -> Tuple[str, str]:
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first process',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return OK, "Accessibility permission granted"
            return FAIL, "Accessibility not granted — enable in System Settings → Privacy → Accessibility"
        except Exception as exc:
            return FAIL, f"Accessibility check failed: {exc}"

    def check_screen_capture_permission(self) -> Tuple[str, str]:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-C", tmp_path],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0 and Path(tmp_path).stat().st_size > 100:
                return OK, "Screen capture permission granted"
            return FAIL, "Screen capture may not be permitted"
        except Exception as exc:
            return FAIL, f"Screen capture check failed: {exc}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ── Helpers ────────────────────────────────────────────────────────

# Normalise macOS AX action names to cross-platform short names
_ACTION_MAP = {
    "AXPress": "press",
    "AXShowMenu": "show_menu",
    "AXRaise": "raise",
    "AXDecrement": "decrement",
    "AXIncrement": "increment",
    "AXConfirm": "confirm",
    "AXCancel": "cancel",
    "AXPick": "pick",
}
_ACTION_REVERSE = {v: k for k, v in _ACTION_MAP.items()}


def _normalise_action(ax_action: str) -> str:
    return _ACTION_MAP.get(ax_action, ax_action)


def _from_normalised_action(action: str) -> str:
    return _ACTION_REVERSE.get(action, action)


# Map short role names → AX role constants
_ROLE_MAP = {
    "button": "AXButton",
    "textField": "AXTextField",
    "staticText": "AXStaticText",
    "window": "AXWindow",
    "group": "AXGroup",
    "list": "AXList",
    "table": "AXTable",
    "cell": "AXCell",
    "checkbox": "AXCheckBox",
    "radioButton": "AXRadioButton",
    "menuItem": "AXMenuItem",
    "link": "AXLink",
    "image": "AXImage",
    "scrollArea": "AXScrollArea",
    "tabGroup": "AXTabGroup",
    "toolbar": "AXToolbar",
    "popUpButton": "AXPopUpButton",
    "comboBox": "AXComboBox",
    "slider": "AXSlider",
}


def _to_ax_role(role: str) -> str:
    return _ROLE_MAP.get(role, role)
