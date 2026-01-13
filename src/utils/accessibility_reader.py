"""
macOS Accessibility Reader
Parses UI element trees for any application without screenshots.
Uses macOS Accessibility APIs (AXUIElement) via pyobjc.
"""

import subprocess
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from ..utils.logging import logger

# Try to import pyobjc accessibility bindings
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


@dataclass
class UIElement:
    """Represents a UI element."""
    role: str  # button, textField, link, etc.
    title: str  # Display text
    value: str  # Current value (for text fields)
    x: int
    y: int
    width: int
    height: int
    enabled: bool = True
    focused: bool = False
    
    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def __str__(self):
        return f"{self.role}: '{self.title or self.value}' at ({self.x}, {self.y})"


def get_frontmost_app() -> Dict[str, str]:
    """Get info about the frontmost application."""
    script = '''
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
            ["osascript", "-e", script],
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
                            elements.append(UIElement(
                                role=parts[0],
                                title=parts[1],
                                value=parts[1],
                                x=int(float(parts[2])),
                                y=int(float(parts[3])),
                                width=int(float(parts[4])),
                                height=int(float(parts[5]))
                            ))
                        except:
                            pass
    except Exception as e:
        logger.error(f"AppleScript UI fetch failed: {e}")
    
    return elements[:max_elements]


def get_ui_tree() -> Dict:
    """
    Get the full UI tree for the frontmost application.
    Returns structured data similar to DOM.
    """
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


def find_element_by_text(search_text: str) -> Optional[UIElement]:
    """
    Find a UI element by its text content.
    Returns element with click coordinates.
    """
    elements = get_ui_elements_applescript()
    search_lower = search_text.lower()
    
    for elem in elements:
        if search_lower in (elem.title or "").lower() or search_lower in (elem.value or "").lower():
            return elem
    
    return None


def click_element(element: UIElement):
    """Click on a UI element using its center coordinates."""
    import pyautogui
    cx, cy = element.center
    pyautogui.click(cx, cy)
    logger.info(f"Clicked: {element}")
