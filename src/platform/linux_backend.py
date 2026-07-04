"""
Linux backend — AT-SPI2 for accessibility, scrot/grim for screen capture,
xdotool/ydotool for input.

Dependencies:
    pip install pyatspi   (or system package python3-pyatspi)
    apt install scrot xdotool   (X11)
    apt install grim ydotool    (Wayland alternative)
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

# ── Accessibility (AT-SPI2) ────────────────────────────────────────

_ATSPI_AVAILABLE = False
try:
    import pyatspi  # type: ignore[import-untyped]

    _ATSPI_AVAILABLE = True
except ImportError:
    pass

# Role mapping: AT-SPI role enum → short name
_ATSPI_ROLE_NAMES: Dict[int, str] = {}


def _init_role_names():
    global _ATSPI_ROLE_NAMES
    if _ATSPI_ROLE_NAMES or not _ATSPI_AVAILABLE:
        return
    for attr in dir(pyatspi):
        if attr.startswith("ROLE_"):
            _ATSPI_ROLE_NAMES[getattr(pyatspi, attr)] = attr[5:]  # strip ROLE_


class LinuxAccessibility(AccessibilityBackend):
    """AT-SPI2-based accessibility backend for Linux / X11 / Wayland."""

    def __init__(self):
        if not _ATSPI_AVAILABLE:
            raise RuntimeError(
                "pyatspi not available. Install: pip install pyatspi  "
                "or  apt install python3-pyatspi"
            )
        _init_role_names()
        self._desktop = pyatspi.Registry.getDesktop(0)

    # -- helpers -------------------------------------------------

    def _to_node(self, obj: Any, depth: int = 0, max_depth: int = 8) -> Optional[UINode]:
        """Convert an AT-SPI Accessible object to a UINode."""
        try:
            role_id = obj.getRole()
            role_name = _ATSPI_ROLE_NAMES.get(role_id, str(role_id))

            name = obj.name or None
            description = obj.description or None

            # Value
            value = None
            try:
                vi = obj.queryValue()
                value = str(vi.currentValue)
            except Exception:
                pass
            try:
                ti = obj.queryText()
                if ti:
                    value = ti.getText(0, ti.characterCount)
            except Exception:
                pass

            # Position & size via Component interface
            position = None
            size = None
            try:
                comp = obj.queryComponent()
                bbox = comp.getExtents(pyatspi.DESKTOP_COORDS)
                position = (bbox.x, bbox.y)
                size = (bbox.width, bbox.height)
            except Exception:
                pass

            # State
            state_set = obj.getState()
            enabled = state_set.contains(pyatspi.STATE_ENABLED)
            focused = state_set.contains(pyatspi.STATE_FOCUSED)

            # Actions
            actions: List[str] = []
            try:
                ai = obj.queryAction()
                for i in range(ai.nActions):
                    actions.append(ai.getName(i))
            except Exception:
                pass

            children: List[UINode] = []
            if depth < max_depth:
                for i in range(obj.childCount):
                    try:
                        child = obj.getChildAtIndex(i)
                        if child:
                            cn = self._to_node(child, depth + 1, max_depth)
                            if cn:
                                children.append(cn)
                    except Exception:
                        continue

            return UINode(
                role=role_name,
                name=name,
                value=value,
                description=description,
                position=position,
                size=size,
                enabled=enabled,
                focused=focused,
                actions=actions,
                children=children,
                native_handle=obj,
            )
        except Exception as exc:
            logger.debug(f"AT-SPI conversion error: {exc}")
            return None

    def _get_active_app(self) -> Any:
        """Return the AT-SPI Accessible for the currently active application."""
        for i in range(self._desktop.childCount):
            try:
                app = self._desktop.getChildAtIndex(i)
                if app is None:
                    continue
                for j in range(app.childCount):
                    win = app.getChildAtIndex(j)
                    if win and win.getState().contains(pyatspi.STATE_ACTIVE):
                        return app
            except Exception:
                continue
        # fallback: first app
        if self._desktop.childCount > 0:
            return self._desktop.getChildAtIndex(0)
        return None

    # -- interface -----------------------------------------------

    def get_ui_tree(self, max_depth: int = 8) -> Optional[UINode]:
        app = self._get_active_app()
        if app is None:
            return None
        return self._to_node(app, max_depth=max_depth)

    def find_elements_by_role(self, role: str) -> List[UINode]:
        tree = self.get_ui_tree()
        if tree is None:
            return []
        results: List[UINode] = []
        self._walk(tree, results, role_filter=role.upper())
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
        obj = node.native_handle
        if obj is None:
            return False
        try:
            ai = obj.queryAction()
            # Map "press" → first action (usually "click")
            target = action if action != "press" else "click"
            for i in range(ai.nActions):
                if ai.getName(i).lower() == target.lower():
                    return ai.doAction(i)
            # fallback: try action 0
            if ai.nActions > 0:
                return ai.doAction(0)
        except Exception as exc:
            logger.warning(f"AT-SPI action failed: {exc}")
        return False

    def set_value(self, node: UINode, value: str) -> bool:
        obj = node.native_handle
        if obj is None:
            return False
        try:
            ti = obj.queryEditableText()
            if ti:
                ti.setTextContents(value)
                return True
        except Exception:
            pass
        try:
            vi = obj.queryValue()
            vi.currentValue = float(value)
            return True
        except Exception:
            pass
        return False

    def get_element_at_position(self, x: int, y: int) -> Optional[UINode]:
        app = self._get_active_app()
        if app is None:
            return None
        try:
            comp = app.queryComponent()
            obj = comp.getAccessibleAtPoint(x, y, pyatspi.DESKTOP_COORDS)
            if obj:
                return self._to_node(obj, max_depth=0)
        except Exception:
            pass
        return None

    def get_frontmost_app_info(self) -> Dict[str, str]:
        app = self._get_active_app()
        if app is None:
            return {"app": "Unknown", "window": ""}
        app_name = app.name or "Unknown"
        window_title = ""
        try:
            for i in range(app.childCount):
                win = app.getChildAtIndex(i)
                if win and win.getState().contains(pyatspi.STATE_ACTIVE):
                    window_title = win.name or ""
                    break
        except Exception:
            pass
        return {"app": app_name, "window": window_title}

    def get_running_apps(self) -> List[Dict[str, Any]]:
        apps: List[Dict[str, Any]] = []
        for i in range(self._desktop.childCount):
            try:
                app = self._desktop.getChildAtIndex(i)
                if app:
                    apps.append({"name": app.name or "Unknown", "pid": app.get_process_id()})
            except Exception:
                continue
        return apps

    def invalidate_cache(self):
        pass  # AT-SPI doesn't cache locally

    # -- tree walk -----------------------------------------------

    @staticmethod
    def _walk(
        node: UINode,
        results: List[UINode],
        role_filter: Optional[str] = None,
        text_filter: Optional[str] = None,
    ):
        match = True
        if role_filter and node.role != role_filter:
            match = False
        if text_filter:
            t = text_filter.lower()
            if not any(
                t in (s or "").lower()
                for s in (node.name, node.value, node.description)
            ):
                match = False
        if match:
            results.append(node)
        for child in node.children:
            LinuxAccessibility._walk(child, results, role_filter, text_filter)


# ── Screen capture ─────────────────────────────────────────────────


class LinuxScreenCapture(ScreenCaptureBackend):
    """scrot (X11) or grim (Wayland) screen capture."""

    def __init__(self):
        self._tool: Optional[str] = None
        if os.environ.get("WAYLAND_DISPLAY"):
            if shutil.which("grim"):
                self._tool = "grim"
        if self._tool is None and shutil.which("scrot"):
            self._tool = "scrot"
        if self._tool is None and shutil.which("grim"):
            self._tool = "grim"
        if self._tool is None:
            logger.warning("No screen capture tool found (install scrot or grim)")

    def capture(self, path: str) -> bool:
        if self._tool is None:
            return False
        try:
            if self._tool == "grim":
                result = subprocess.run(
                    ["grim", path], capture_output=True, timeout=5
                )
            else:
                result = subprocess.run(
                    ["scrot", path], capture_output=True, timeout=5
                )
            return result.returncode == 0 and Path(path).exists()
        except Exception as exc:
            logger.error(f"Screen capture failed: {exc}")
            return False

    def capture_bytes(self) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            if self.capture(tmp_path):
                return Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        from PIL import Image
        import io

        img = Image.new("RGB", self.get_screen_size(), color="gray")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def get_screen_size(self) -> Tuple[int, int]:
        try:
            output = subprocess.check_output(
                ["xdpyinfo"], stderr=subprocess.DEVNULL, timeout=3
            ).decode()
            for line in output.splitlines():
                if "dimensions:" in line:
                    dims = line.split()[1]  # e.g. "1920x1080"
                    w, h = dims.split("x")
                    return (int(w), int(h))
        except Exception:
            pass
        try:
            import pyautogui

            return pyautogui.size()
        except Exception:
            pass
        return (1920, 1080)

    def get_scale_factor(self) -> float:
        # Wayland compositors may set GDK_SCALE or QT_SCALE_FACTOR
        for var in ("GDK_SCALE", "QT_SCALE_FACTOR"):
            val = os.environ.get(var)
            if val:
                try:
                    return float(val)
                except ValueError:
                    pass
        return 1.0


# ── Cursor / input (xdotool + pyautogui fallback) ─────────────────


class LinuxCursor(CursorBackend):
    """xdotool (X11) or ydotool (Wayland) + pyautogui fallback."""

    def __init__(self):
        self._use_xdotool = shutil.which("xdotool") is not None
        self._use_ydotool = (
            not self._use_xdotool
            and os.environ.get("WAYLAND_DISPLAY")
            and shutil.which("ydotool") is not None
        )
        import pyautogui

        self._pyag = pyautogui

    def move_to(self, x: int, y: int, duration: float = 0.0) -> None:
        if self._use_xdotool:
            subprocess.run(
                ["xdotool", "mousemove", str(x), str(y)],
                capture_output=True,
            )
        else:
            self._pyag.moveTo(x, y, duration=duration)

    def click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
        if self._use_xdotool:
            subprocess.run(["xdotool", "click", "1"], capture_output=True)
        else:
            self._pyag.click()

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
        if self._use_xdotool:
            subprocess.run(
                ["xdotool", "click", "--repeat", "2", "--delay", "50", "1"],
                capture_output=True,
            )
        else:
            self._pyag.doubleClick()

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
        if self._use_xdotool:
            subprocess.run(["xdotool", "click", "3"], capture_output=True)
        else:
            self._pyag.rightClick()

    def type_text(self, text: str, interval: float = 0.0) -> None:
        if self._use_xdotool:
            subprocess.run(
                ["xdotool", "type", "--delay", str(int(interval * 1000)), text],
                capture_output=True,
            )
        else:
            self._pyag.typewrite(text, interval=interval)

    def hotkey(self, *keys: str) -> None:
        if self._use_xdotool:
            combo = "+".join(keys)
            subprocess.run(["xdotool", "key", combo], capture_output=True)
        else:
            self._pyag.hotkey(*keys)

    def key_press(self, key: str) -> None:
        if self._use_xdotool:
            subprocess.run(["xdotool", "key", key], capture_output=True)
        else:
            self._pyag.press(key)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
        self._pyag.scroll(clicks)

    def get_position(self) -> Tuple[int, int]:
        if self._use_xdotool:
            try:
                output = subprocess.check_output(
                    ["xdotool", "getmouselocation"], timeout=2
                ).decode()
                # output: "x:123 y:456 screen:0 window:..."
                parts = output.split()
                x = int(parts[0].split(":")[1])
                y = int(parts[1].split(":")[1])
                return (x, y)
            except Exception:
                pass
        pos = self._pyag.position()
        return (pos.x, pos.y)


# ── Health checks ──────────────────────────────────────────────────

OK = "✅"
WARN = "⚠️"
FAIL = "❌"


class LinuxHealthCheck(HealthCheckBackend):

    def check_accessibility_permission(self) -> Tuple[str, str]:
        if _ATSPI_AVAILABLE:
            return OK, "AT-SPI2 available"
        return FAIL, "pyatspi not installed — apt install python3-pyatspi"

    def check_screen_capture_permission(self) -> Tuple[str, str]:
        for tool in ("scrot", "grim"):
            if shutil.which(tool):
                return OK, f"Screen capture tool available ({tool})"
        return FAIL, "No screen capture tool — apt install scrot (X11) or grim (Wayland)"
