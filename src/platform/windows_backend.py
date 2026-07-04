"""
Windows backend — UI Automation via comtypes/uiautomation for accessibility,
Win32 API for screen capture, pyautogui for input.

Dependencies:
    pip install comtypes uiautomation pyautogui pillow
"""

import os
import shutil
import subprocess
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

# ── Accessibility (UI Automation) ──────────────────────────────────

_UIA_AVAILABLE = False
try:
    import uiautomation as auto  # type: ignore[import-untyped]

    _UIA_AVAILABLE = True
except ImportError:
    pass

# Control type ID → human-readable name
_CONTROL_TYPE_NAMES = {
    50000: "button",
    50001: "calendar",
    50002: "checkBox",
    50003: "comboBox",
    50004: "edit",
    50005: "hyperlink",
    50006: "image",
    50007: "listItem",
    50008: "list",
    50009: "menu",
    50010: "menuBar",
    50011: "menuItem",
    50012: "progressBar",
    50013: "radioButton",
    50014: "scrollBar",
    50015: "slider",
    50016: "spinner",
    50017: "statusBar",
    50018: "tab",
    50019: "tabItem",
    50020: "text",
    50021: "toolBar",
    50022: "toolTip",
    50023: "tree",
    50024: "treeItem",
    50025: "custom",
    50026: "group",
    50027: "thumb",
    50028: "dataGrid",
    50029: "dataItem",
    50030: "document",
    50031: "splitButton",
    50032: "window",
    50033: "pane",
    50034: "header",
    50035: "headerItem",
    50036: "table",
    50037: "titleBar",
    50038: "separator",
}


class WindowsAccessibility(AccessibilityBackend):
    """Windows UI Automation-based accessibility backend."""

    def __init__(self):
        if not _UIA_AVAILABLE:
            raise RuntimeError(
                "uiautomation not available. Install: pip install uiautomation"
            )

    # -- helpers -------------------------------------------------

    def _to_node(
        self, ctrl: Any, depth: int = 0, max_depth: int = 8
    ) -> Optional[UINode]:
        try:
            role = _CONTROL_TYPE_NAMES.get(ctrl.ControlType, str(ctrl.ControlType))
            name = ctrl.Name or None
            value = None

            # Try to get value via ValuePattern
            try:
                vp = ctrl.GetValuePattern()
                if vp:
                    value = vp.Value
            except Exception:
                pass

            # Bounding rectangle
            position = None
            size = None
            try:
                rect = ctrl.BoundingRectangle
                if rect and rect.width() > 0:
                    position = (rect.left, rect.top)
                    size = (rect.width(), rect.height())
            except Exception:
                pass

            # Enabled / focused
            enabled = ctrl.IsEnabled
            focused = ctrl.HasKeyboardFocus if hasattr(ctrl, "HasKeyboardFocus") else False

            # Available patterns as "actions"
            actions: List[str] = []
            try:
                if ctrl.GetInvokePattern():
                    actions.append("invoke")
            except Exception:
                pass
            try:
                if ctrl.GetTogglePattern():
                    actions.append("toggle")
            except Exception:
                pass
            try:
                if ctrl.GetExpandCollapsePattern():
                    actions.append("expand_collapse")
            except Exception:
                pass
            try:
                if ctrl.GetSelectionItemPattern():
                    actions.append("select")
            except Exception:
                pass

            children: List[UINode] = []
            if depth < max_depth:
                try:
                    for child in ctrl.GetChildren():
                        cn = self._to_node(child, depth + 1, max_depth)
                        if cn:
                            children.append(cn)
                except Exception:
                    pass

            return UINode(
                role=role,
                name=name,
                value=value,
                description=None,
                position=position,
                size=size,
                enabled=enabled,
                focused=focused,
                actions=actions,
                children=children,
                native_handle=ctrl,
            )
        except Exception as exc:
            logger.debug(f"UIA conversion error: {exc}")
            return None

    # -- interface -----------------------------------------------

    def get_ui_tree(self, max_depth: int = 8) -> Optional[UINode]:
        try:
            fg = auto.GetForegroundControl()
            if fg is None:
                return None
            return self._to_node(fg, max_depth=max_depth)
        except Exception as exc:
            logger.error(f"Failed to get UI tree: {exc}")
            return None

    def find_elements_by_role(self, role: str) -> List[UINode]:
        tree = self.get_ui_tree()
        if tree is None:
            return []
        results: List[UINode] = []
        self._walk(tree, results, role_filter=role)
        return results

    def find_elements_by_text(self, text: str) -> List[UINode]:
        tree = self.get_ui_tree()
        if tree is None:
            return []
        results: List[UINode] = []
        self._walk(tree, results, text_filter=text)
        return results

    def find_element_by_text(self, text: str) -> Optional[UINode]:
        elems = self.find_elements_by_text(text)
        return elems[0] if elems else None

    def perform_action(self, node: UINode, action: str = "press") -> bool:
        ctrl = node.native_handle
        if ctrl is None:
            return False
        try:
            if action in ("press", "invoke", "click"):
                ip = ctrl.GetInvokePattern()
                if ip:
                    ip.Invoke()
                    return True
            elif action == "toggle":
                tp = ctrl.GetTogglePattern()
                if tp:
                    tp.Toggle()
                    return True
            elif action in ("expand", "expand_collapse"):
                ecp = ctrl.GetExpandCollapsePattern()
                if ecp:
                    ecp.Expand()
                    return True
            elif action == "collapse":
                ecp = ctrl.GetExpandCollapsePattern()
                if ecp:
                    ecp.Collapse()
                    return True
            elif action == "select":
                sip = ctrl.GetSelectionItemPattern()
                if sip:
                    sip.Select()
                    return True
        except Exception as exc:
            logger.warning(f"UIA action '{action}' failed: {exc}")
        return False

    def set_value(self, node: UINode, value: str) -> bool:
        ctrl = node.native_handle
        if ctrl is None:
            return False
        try:
            vp = ctrl.GetValuePattern()
            if vp:
                vp.SetValue(value)
                return True
        except Exception:
            pass
        return False

    def get_element_at_position(self, x: int, y: int) -> Optional[UINode]:
        try:
            ctrl = auto.ControlFromPoint(x, y)
            if ctrl:
                return self._to_node(ctrl, max_depth=0)
        except Exception:
            pass
        return None

    def get_frontmost_app_info(self) -> Dict[str, str]:
        try:
            fg = auto.GetForegroundControl()
            if fg:
                return {"app": fg.Name or "Unknown", "window": fg.Name or ""}
        except Exception:
            pass
        return {"app": "Unknown", "window": ""}

    def get_running_apps(self) -> List[Dict[str, Any]]:
        apps: List[Dict[str, Any]] = []
        try:
            root = auto.GetRootControl()
            for child in root.GetChildren():
                try:
                    apps.append({
                        "name": child.Name or "Unknown",
                        "pid": child.ProcessId,
                    })
                except Exception:
                    continue
        except Exception:
            pass
        return apps

    def invalidate_cache(self):
        pass

    @staticmethod
    def _walk(
        node: UINode,
        results: List[UINode],
        role_filter: Optional[str] = None,
        text_filter: Optional[str] = None,
    ):
        match = True
        if role_filter and node.role.lower() != role_filter.lower():
            match = False
        if text_filter:
            t = text_filter.lower()
            if not any(
                t in (s or "").lower() for s in (node.name, node.value, node.description)
            ):
                match = False
        if match:
            results.append(node)
        for child in node.children:
            WindowsAccessibility._walk(child, results, role_filter, text_filter)


# ── Screen capture ─────────────────────────────────────────────────


class WindowsScreenCapture(ScreenCaptureBackend):
    """Win32 / PIL screen capture."""

    def capture(self, path: str) -> bool:
        try:
            from PIL import ImageGrab  # type: ignore[import-untyped]

            img = ImageGrab.grab()
            img.save(path)
            return Path(path).exists()
        except Exception as exc:
            logger.error(f"Screen capture failed: {exc}")
            return False

    def capture_bytes(self) -> bytes:
        import io

        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            from PIL import Image

            img = Image.new("RGB", self.get_screen_size(), color="gray")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    def get_screen_size(self) -> Tuple[int, int]:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            w = user32.GetSystemMetrics(0)
            h = user32.GetSystemMetrics(1)
            return (w, h)
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
            import ctypes

            # Windows 8.1+
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return dpi / 96.0
        except Exception:
            return 1.0


# ── Cursor / input ─────────────────────────────────────────────────


class WindowsCursor(CursorBackend):
    """pyautogui-based cursor control on Windows."""

    def __init__(self):
        import pyautogui

        self._pyag = pyautogui

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        self._pyag.moveTo(x, y, duration=duration)

    def click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
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


class WindowsHealthCheck(HealthCheckBackend):

    def check_accessibility_permission(self) -> Tuple[str, str]:
        if _UIA_AVAILABLE:
            return OK, "UI Automation available"
        return FAIL, "uiautomation not installed — pip install uiautomation"

    def check_screen_capture_permission(self) -> Tuple[str, str]:
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            if img.size[0] > 0:
                return OK, "Screen capture working"
        except Exception as exc:
            return FAIL, f"Screen capture failed: {exc}"
        return WARN, "Screen capture may not work correctly"
