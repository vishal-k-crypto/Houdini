"""
macOS Accessibility Reader
Parses UI element trees for any application without screenshots.
Uses macOS Accessibility APIs (AXUIElement) via pyobjc.

IMPORTANT: macOS uses bottom-left origin, PyAutoGUI uses top-left origin.
Coordinates must be converted!

This module now uses the enhanced accessibility_api.py as primary method,
with AppleScript as fallback.
"""

import subprocess
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from ..utils.logging import logger

# Try to import new native API
try:
    from .accessibility_api import AccessibilityAPI, AXElement as NativeAXElement
    NATIVE_API_AVAILABLE = True
except ImportError:
    NATIVE_API_AVAILABLE = False
    logger.warning("Native accessibility_api not available, using AppleScript only")

# Try to import pyobjc accessibility bindings (for fallback)
try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyAttributeNames,
        AXUIElementCopyElementAtPosition,
        AXUIElementPerformAction,
        kAXErrorSuccess
    )
    from Quartz import CGEventGetLocation, CGEventCreate
    import AppKit
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False
    logger.warning("pyobjc not available, using AppleScript fallback")


# Screen dimensions cache
_screen_height = None
_screen_info_cached = None


def get_screen_height() -> int:
    """
    Get screen height for coordinate conversion.
    
    IMPORTANT: Handles Retina displays properly by checking multiple sources:
    1. CGDisplayBounds (native resolution)
    2. NSScreen (logical resolution - what PyAutoGUI uses)
    3. PyAutoGUI fallback
    
    Uses the logical resolution to match PyAutoGUI's coordinate system.
    """
    global _screen_height, _screen_info_cached
    if _screen_height is not None:
        return _screen_height
    
    try:
        # Try NSScreen first - gives logical resolution matching PyAutoGUI
        import AppKit
        screen = AppKit.NSScreen.mainScreen()
        if screen:
            frame = screen.frame()
            _screen_height = int(frame.size.height)
            logger.debug(f"Screen height from NSScreen: {_screen_height} (logical)")
            return _screen_height
    except Exception as e:
        logger.debug(f"NSScreen failed: {e}")
    
    try:
        # Fallback to PyAutoGUI
        import pyautogui
        _, _screen_height = pyautogui.size()
        logger.debug(f"Screen height from PyAutoGUI: {_screen_height}")
    except:
        _screen_height = 1080  # Default fallback
        logger.warning("Using default screen height 1080")
    
    return _screen_height


def get_screen_info() -> dict:
    """Get comprehensive screen info for debugging coordinate issues."""
    global _screen_info_cached
    if _screen_info_cached:
        return _screen_info_cached
    
    info = {
        "pyautogui_size": None,
        "nsscreen_size": None,
        "cgdisplay_size": None,
        "backing_scale": 1.0,
        "is_retina": False,
    }
    
    try:
        import pyautogui
        info["pyautogui_size"] = pyautogui.size()
    except:
        pass
    
    try:
        import AppKit
        screen = AppKit.NSScreen.mainScreen()
        if screen:
            frame = screen.frame()
            info["nsscreen_size"] = (int(frame.size.width), int(frame.size.height))
            # Get backing scale factor for Retina detection
            info["backing_scale"] = screen.backingScaleFactor()
            info["is_retina"] = info["backing_scale"] > 1.0
    except:
        pass
    
    try:
        from Quartz import CGMainDisplayID, CGDisplayBounds
        bounds = CGDisplayBounds(CGMainDisplayID())
        info["cgdisplay_size"] = (int(bounds.size.width), int(bounds.size.height))
    except:
        pass
    
    _screen_info_cached = info
    return info


def convert_macos_to_pyautogui_coords(x: int, y: int) -> Tuple[int, int]:
    """
    Convert macOS coordinates to PyAutoGUI coordinates.
    
    macOS Accessibility API: Origin at TOP-LEFT of screen (not bottom-left!)
    PyAutoGUI: Origin at TOP-LEFT of screen
    
    IMPORTANT: Despite common misconception, AXPosition coordinates from
    Accessibility API are ALREADY in screen coordinates with (0,0) at top-left.
    No Y-axis flip is needed for position values from AXUIElement.
    
    The only conversion needed is for Retina displays if the APIs report
    different resolutions.
    """
    # AXPosition is already in screen coords (top-left origin)
    # Just return as-is since both systems use same origin
    return (int(x), int(y))


@dataclass
class UIElement:
    """Represents a UI element."""
    role: str  # button, textField, link, etc.
    title: str  # Display text
    value: str  # Current value (for text fields)
    x: int  # Already converted to PyAutoGUI coords
    y: int  # Already converted to PyAutoGUI coords
    width: int
    height: int
    enabled: bool = True
    focused: bool = False
    
    @property
    def center(self) -> Tuple[int, int]:
        """Return center coordinates (already in PyAutoGUI coordinate system)."""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def __str__(self):
        return f"{self.role}: '{self.title or self.value}' at ({self.x}, {self.y})"


# Apps to skip when detecting frontmost app (IDEs, terminals running the agent)
AGENT_SKIP_APPS = [
    "electron",       # VS Code, other Electron apps
    "code",           # VS Code 
    "code - insiders", # VS Code Insiders
    "cursor",         # Cursor IDE
    "terminal",       # Terminal running the agent
    "iterm",          # iTerm2 running the agent
    "iterm2",
    "warp",           # Warp terminal
    "alacritty",      # Alacritty terminal
    "kitty",          # Kitty terminal
    "hyper",          # Hyper terminal
]


def get_frontmost_app(skip_agent_apps: bool = True) -> Dict[str, str]:
    """
    Get info about the frontmost application.
    
    Args:
        skip_agent_apps: If True, skip known IDE/editor/terminal apps that might
                        be running the agent itself, and return the next app.
    """
    # Script to get all visible application windows in order
    script = '''
    tell application "System Events"
        set output to ""
        set allProcs to every application process whose visible is true
        repeat with proc in allProcs
            set appName to name of proc
            set isFront to frontmost of proc
            try
                set windowTitle to name of window 1 of proc
            on error
                set windowTitle to ""
            end try
            set output to output & appName & "|" & windowTitle & "|" & isFront & "\\n"
        end repeat
        return output
    end tell
    '''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            frontmost_app = None
            other_apps = []
            
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    app_name = parts[0].strip()
                    window_title = parts[1].strip()
                    is_front = parts[2].strip().lower() == "true"
                    
                    app_info = {"app": app_name, "window": window_title}
                    
                    if is_front:
                        frontmost_app = app_info
                    else:
                        other_apps.append(app_info)
            
            # If skip_agent_apps is enabled and frontmost is an agent-related app,
            # try to return the next visible app instead
            if skip_agent_apps and frontmost_app:
                app_lower = frontmost_app["app"].lower()
                if any(skip_app in app_lower for skip_app in AGENT_SKIP_APPS):
                    logger.debug(f"Skipping agent app '{frontmost_app['app']}', looking for next app")
                    # Return the first non-agent app from other visible apps
                    for other_app in other_apps:
                        other_lower = other_app["app"].lower()
                        if not any(skip_app in other_lower for skip_app in AGENT_SKIP_APPS):
                            logger.debug(f"Found target app: {other_app['app']}")
                            return other_app
                    # All apps are agent apps - return frontmost anyway
                    logger.debug("No target app found, returning frontmost")
                    return frontmost_app
            
            if frontmost_app:
                return frontmost_app
    except Exception as e:
        logger.debug(f"get_frontmost_app advanced script failed: {e}")
    
    # Fallback to simple script
    simple_script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        set appName to name of frontApp
        try
            set windowTitle to name of window 1 of frontApp
        on error
            set windowTitle to ""
        end try
        return appName & "|" & windowTitle
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", simple_script],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            return {"app": parts[0], "window": parts[1] if len(parts) > 1 else ""}
    except:
        pass
    return {"app": "Unknown", "window": ""}


def get_ui_elements_applescript(max_elements: int = 50) -> List[UIElement]:
    """
    Get UI elements using AppleScript (slower but reliable fallback).
    """
    script = '''
    set output to ""
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        try
            set frontWindow to window 1 of frontApp
            
            -- Get buttons
            repeat with btn in buttons of frontWindow
                try
                    set btnName to name of btn
                    set btnPos to position of btn
                    set btnSize to size of btn
                    set output to output & "button|" & btnName & "|" & (item 1 of btnPos) & "|" & (item 2 of btnPos) & "|" & (item 1 of btnSize) & "|" & (item 2 of btnSize) & "\\n"
                end try
            end repeat
            
            -- Get text fields
            repeat with tf in text fields of frontWindow
                try
                    set tfValue to value of tf
                    set tfPos to position of tf
                    set tfSize to size of tf
                    set output to output & "textField|" & tfValue & "|" & (item 1 of tfPos) & "|" & (item 2 of tfPos) & "|" & (item 1 of tfSize) & "|" & (item 2 of tfSize) & "\\n"
                end try
            end repeat
            
            -- Get static text
            repeat with st in static texts of frontWindow
                try
                    set stValue to value of st
                    set stPos to position of st
                    set stSize to size of st
                    set output to output & "staticText|" & stValue & "|" & (item 1 of stPos) & "|" & (item 2 of stPos) & "|" & (item 1 of stSize) & "|" & (item 2 of stSize) & "\\n"
                end try
            end repeat
            
            -- Get links (for web views)
            repeat with lnk in links of frontWindow
                try
                    set lnkName to name of lnk
                    set lnkPos to position of lnk
                    set lnkSize to size of lnk
                    set output to output & "link|" & lnkName & "|" & (item 1 of lnkPos) & "|" & (item 2 of lnkPos) & "|" & (item 1 of lnkSize) & "|" & (item 2 of lnkSize) & "\\n"
                end try
            end repeat
            
        end try
    end tell
    return output
    '''
    
    elements = []
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 6:
                        try:
                            # Parse macOS coordinates
                            macos_x = int(float(parts[2]))
                            macos_y = int(float(parts[3]))
                            width = int(float(parts[4]))
                            height = int(float(parts[5]))
                            
                            # Convert to PyAutoGUI coordinates
                            pyautogui_x, pyautogui_y = convert_macos_to_pyautogui_coords(macos_x, macos_y)
                            
                            elements.append(UIElement(
                                role=parts[0],
                                title=parts[1],
                                value=parts[1],
                                x=pyautogui_x,
                                y=pyautogui_y,
                                width=width,
                                height=height
                            ))
                        except Exception as e:
                            logger.debug(f"Failed to parse element: {e}")
                            pass
    except Exception as e:
        logger.error(f"AppleScript UI fetch failed: {e}")
    
    return elements[:max_elements]


def get_ui_tree(use_native: bool = True) -> Dict:
    """
    Get the full UI tree for the frontmost application.
    Returns structured data similar to DOM.
    
    Args:
        use_native: Try native AccessibilityAPI first (faster)
    """
    # Try native API first
    if use_native and NATIVE_API_AVAILABLE:
        try:
            api = AccessibilityAPI()
            tree = api.get_ui_tree(max_depth=5)
            
            if tree:
                # Convert to old format for compatibility
                elements = []
                def collect(elem):
                    if elem.position and elem.role != "AXWindow":
                        # Convert NativeAXElement to UIElement format
                        x, y = elem.position
                        w, h = elem.size if elem.size else (0, 0)
                        elements.append(UIElement(
                            role=elem.role,
                            title=elem.title or "",
                            value=elem.value or "",
                            x=x, y=y, width=w, height=h,
                            enabled=elem.enabled,
                            focused=elem.focused
                        ))
                    for child in elem.children:
                        collect(child)
                
                collect(tree)
                app_info = api.get_frontmost_app_info()
                
                logger.info(f"Native API: {len(elements)} elements")
                return {
                    "app": app_info.get("app", "Unknown"),
                    "window": app_info.get("window", ""),
                    "elements": elements,
                    "count": len(elements)
                }
        except Exception as e:
            logger.warning(f"Native API failed, falling back to AppleScript: {e}")
    
    # Fallback to AppleScript
    app_info = get_frontmost_app()
    elements = get_ui_elements_applescript()
    
    return {
        "app": app_info["app"],
        "window": app_info["window"],
        "elements": elements,
        "count": len(elements)
    }


def format_ui_for_llm(max_elements: int = 30) -> str:
    """
    Format UI tree as text for LLM consumption.
    Much faster than OCR + screenshot.
    """
    tree = get_ui_tree()
    
    lines = [
        f"=== ACTIVE APP: {tree['app']} ===",
        f"Window: {tree['window']}",
        f"Elements ({tree['count']}):",
    ]
    
    for elem in tree["elements"][:max_elements]:
        cx, cy = elem.center
        lines.append(f"  [{elem.role}] '{elem.title or elem.value}' → click({cx}, {cy})")
    
    return "\n".join(lines)


def find_element_by_text(search_text: str, use_native: bool = True) -> Optional[UIElement]:
    """
    Find a UI element by its text content.
    Returns element with click coordinates.
    
    Args:
        search_text: Text to search for
        use_native: Try native API first
    """
    # Try native API first
    if use_native and NATIVE_API_AVAILABLE:
        try:
            api = AccessibilityAPI()
            elements = api.find_elements_by_text(search_text)
            
            if elements:
                elem = elements[0]
                if elem.position and elem.size:
                    x, y = elem.position
                    w, h = elem.size
                    return UIElement(
                        role=elem.role,
                        title=elem.title or "",
                        value=elem.value or "",
                        x=x, y=y, width=w, height=h,
                        enabled=elem.enabled,
                        focused=elem.focused
                    )
        except Exception as e:
            logger.warning(f"Native search failed: {e}")
    
    # Fallback to AppleScript
    elements = get_ui_elements_applescript()
    search_lower = search_text.lower()
    
    for elem in elements:
        if search_lower in (elem.title or "").lower() or search_lower in (elem.value or "").lower():
            return elem
    
    return None


def click_element(element: UIElement, duration: float = 0.3, human_like: bool = True):
    """Click on a UI element using its center coordinates with smooth cursor movement.
    
    Args:
        element: UIElement to click
        duration: Movement duration (ignored if human_like=True)
        human_like: Use human-like cursor movement (HumanCursor vs pyautogui)
    """
    # Try to use HumanCursor for more natural movement
    if human_like:
        try:
            from .cursor_controller import HumanCursor
            cursor = HumanCursor()
            cursor.click_element(element)
            return
        except ImportError:
            logger.warning("cursor_controller not available, using pyautogui")
    
    # Fallback to simple pyautogui
    import pyautogui
    
    # Get current cursor position
    current_x, current_y = pyautogui.position()
    
    # Get target position
    target_x, target_y = element.center
    
    # Calculate distance for logging
    distance = ((target_x - current_x)**2 + (target_y - current_y)**2)**0.5
    
    logger.info(f"Moving cursor: ({current_x}, {current_y}) → ({target_x}, {target_y}) [distance: {distance:.0f}px]")
    
    # Move cursor smoothly to target (visible movement)
    pyautogui.moveTo(target_x, target_y, duration=duration)
    
    # Small pause before clicking
    import time
    time.sleep(0.05)
    
    # Click at current position
    pyautogui.click()
    
    logger.info(f"Clicked: {element}")
