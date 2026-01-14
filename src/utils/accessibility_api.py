"""
Native macOS Accessibility API Integration
Uses PyObjC to directly access AXUIElement tree - much faster than AppleScript.

This module provides:
- Recursive UI element tree traversal
- Fast element search by role, title, value
- Direct element action execution (AXPress, etc.)
- Coordinate handling with proper origin conversion
"""

import time
from typing import List, Dict, Optional, Tuple, Any, Set
from dataclasses import dataclass
from ..utils.logging import logger

try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyAttributeNames,
        AXUIElementCopyElementAtPosition,
        AXUIElementPerformAction,
        AXUIElementCopyActionNames,
        kAXErrorSuccess,
        kAXErrorNoValue,
        kAXErrorInvalidUIElement,
        kAXErrorCannotComplete,
        kAXErrorAttributeUnsupported,
        kAXErrorActionUnsupported,
    )
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        CGMainDisplayID,
        CGDisplayBounds,
    )
    from Cocoa import NSWorkspace
    import AppKit
    PYOBJC_AVAILABLE = True
except ImportError:
    PYOBJC_AVAILABLE = False
    logger.error("PyObjC frameworks not available. Install: pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ApplicationServices")


@dataclass
class AXElement:
    """Represents an accessible UI element with all its properties."""
    ax_ref: Any  # AXUIElementRef
    role: str
    title: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    position: Optional[Tuple[int, int]] = None  # (x, y) in screen coordinates (top-left origin)
    size: Optional[Tuple[int, int]] = None  # (width, height)
    enabled: bool = True
    focused: bool = False
    actions: List[str] = None
    children: List['AXElement'] = None
    
    def __post_init__(self):
        if self.actions is None:
            self.actions = []
        if self.children is None:
            self.children = []
    
    @property
    def center(self) -> Optional[Tuple[int, int]]:
        """Get center coordinates of element."""
        if self.position and self.size:
            x, y = self.position
            w, h = self.size
            return (x + w // 2, y + h // 2)
        return None
    
    @property
    def bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """Get bounding box as (x1, y1, x2, y2)."""
        if self.position and self.size:
            x, y = self.position
            w, h = self.size
            return (x, y, x + w, y + h)
        return None
    
    def __str__(self):
        text = self.title or self.value or self.description or ""
        pos = f"at {self.position}" if self.position else ""
        return f"[{self.role}] '{text}' {pos}"


class AccessibilityAPI:
    """
    Native macOS Accessibility API interface.
    Provides fast, semantic UI element access.
    """
    
    def __init__(self):
        if not PYOBJC_AVAILABLE:
            raise RuntimeError("PyObjC not available. Cannot use AccessibilityAPI.")
        
        self._screen_height = self._get_screen_height()
        self._element_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 2.0  # Cache valid for 2 seconds
        
    def _get_screen_height(self) -> int:
        """Get main display height for coordinate conversion."""
        try:
            display_bounds = CGDisplayBounds(CGMainDisplayID())
            return int(display_bounds.size.height)
        except:
            return 1080  # Fallback
    
    def _convert_coords_to_screen(self, macos_x: float, macos_y: float) -> Tuple[int, int]:
        """
        Convert macOS coordinates (bottom-left origin) to screen (top-left origin).
        
        macOS: (0, 0) = bottom-left, y increases upward
        Screen: (0, 0) = top-left, y increases downward
        """
        screen_y = self._screen_height - int(macos_y)
        return (int(macos_x), screen_y)
    
    def _get_attribute(self, element: Any, attribute: str) -> Optional[Any]:
        """Safely get an attribute from an AXUIElement."""
        try:
            error, value = AXUIElementCopyAttributeValue(element, attribute, None)
            if error == kAXErrorSuccess:
                return value
            elif error == kAXErrorNoValue:
                return None
            else:
                return None
        except Exception as e:
            logger.debug(f"Error getting attribute {attribute}: {e}")
            return None
    
    def _element_to_axelement(self, ax_ref: Any, include_children: bool = False, max_depth: int = 3, current_depth: int = 0) -> Optional[AXElement]:
        """Convert AXUIElementRef to our AXElement dataclass."""
        try:
            # Get basic properties
            role = self._get_attribute(ax_ref, "AXRole")
            if not role:
                return None
            
            title = self._get_attribute(ax_ref, "AXTitle") or ""
            value = self._get_attribute(ax_ref, "AXValue")
            if value and not isinstance(value, str):
                value = str(value)
            
            description = self._get_attribute(ax_ref, "AXDescription") or ""
            
            # Get position and size
            position = None
            size = None
            ax_position = self._get_attribute(ax_ref, "AXPosition")
            ax_size = self._get_attribute(ax_ref, "AXSize")
            
            if ax_position and ax_size:
                # Convert from CGPoint to tuple and convert coordinates
                macos_x = ax_position.x
                macos_y = ax_position.y
                position = self._convert_coords_to_screen(macos_x, macos_y)
                size = (int(ax_size.width), int(ax_size.height))
            
            # Get state
            enabled = self._get_attribute(ax_ref, "AXEnabled")
            if enabled is None:
                enabled = True
            
            focused = self._get_attribute(ax_ref, "AXFocused")
            if focused is None:
                focused = False
            
            # Get available actions
            actions = []
            error, action_names = AXUIElementCopyActionNames(ax_ref, None)
            if error == kAXErrorSuccess and action_names:
                actions = list(action_names)
            
            # Create element
            element = AXElement(
                ax_ref=ax_ref,
                role=role,
                title=title,
                value=value,
                description=description,
                position=position,
                size=size,
                enabled=enabled,
                focused=focused,
                actions=actions,
                children=[]
            )
            
            # Recursively get children if requested
            if include_children and current_depth < max_depth:
                children_refs = self._get_attribute(ax_ref, "AXChildren")
                if children_refs:
                    for child_ref in children_refs[:100]:  # Limit to prevent explosion
                        child = self._element_to_axelement(child_ref, include_children=True, max_depth=max_depth, current_depth=current_depth+1)
                        if child:
                            element.children.append(child)
            
            return element
            
        except Exception as e:
            logger.debug(f"Error converting element: {e}")
            return None
    
    def get_frontmost_app_element(self) -> Optional[AXElement]:
        """Get the AXUIElement for the frontmost application."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            frontmost_app = workspace.frontmostApplication()
            
            if not frontmost_app:
                return None
            
            pid = frontmost_app.processIdentifier()
            ax_app = AXUIElementCreateApplication(pid)
            
            return self._element_to_axelement(ax_app, include_children=False)
            
        except Exception as e:
            logger.error(f"Failed to get frontmost app: {e}")
            return None
    
    def get_ui_tree(self, max_depth: int = 5, use_cache: bool = True) -> Optional[AXElement]:
        """
        Get the full UI element tree for the frontmost application.
        
        Args:
            max_depth: Maximum depth to traverse
            use_cache: Whether to use cached tree
            
        Returns:
            Root AXElement with children populated
        """
        # Check cache
        current_time = time.time()
        if use_cache and (current_time - self._cache_timestamp) < self._cache_ttl:
            cached = self._element_cache.get('ui_tree')
            if cached:
                logger.debug("Using cached UI tree")
                return cached
        
        try:
            workspace = NSWorkspace.sharedWorkspace()
            frontmost_app = workspace.frontmostApplication()
            
            if not frontmost_app:
                return None
            
            pid = frontmost_app.processIdentifier()
            ax_app = AXUIElementCreateApplication(pid)
            
            # Get the tree with children
            tree = self._element_to_axelement(ax_app, include_children=True, max_depth=max_depth)
            
            # Cache it
            self._element_cache['ui_tree'] = tree
            self._cache_timestamp = current_time
            
            return tree
            
        except Exception as e:
            logger.error(f"Failed to get UI tree: {e}")
            return None
    
    def _traverse_elements(self, element: AXElement, results: List[AXElement], role_filter: Optional[str] = None, text_filter: Optional[str] = None):
        """Recursively traverse element tree and collect matching elements."""
        # Check filters
        matches = True
        if role_filter and element.role != role_filter:
            matches = False
        if text_filter:
            text_lower = text_filter.lower()
            title = (element.title or "").lower()
            value = (element.value or "").lower()
            desc = (element.description or "").lower()
            if text_lower not in title and text_lower not in value and text_lower not in desc:
                matches = False
        
        if matches:
            results.append(element)
        
        # Traverse children
        for child in element.children:
            self._traverse_elements(child, results, role_filter, text_filter)
    
    def find_elements_by_role(self, role: str, use_cache: bool = True) -> List[AXElement]:
        """Find all elements with a specific role (e.g., 'AXButton', 'AXTextField')."""
        tree = self.get_ui_tree(use_cache=use_cache)
        if not tree:
            return []
        
        results = []
        self._traverse_elements(tree, results, role_filter=role)
        return results
    
    def find_elements_by_text(self, text: str, use_cache: bool = True) -> List[AXElement]:
        """Find elements containing specific text in title, value, or description."""
        tree = self.get_ui_tree(use_cache=use_cache)
        if not tree:
            return []
        
        results = []
        self._traverse_elements(tree, results, text_filter=text)
        return results
    
    def find_element_by_text(self, text: str, use_cache: bool = True) -> Optional[AXElement]:
        """Find first element containing specific text."""
        elements = self.find_elements_by_text(text, use_cache)
        return elements[0] if elements else None
    
    def perform_action(self, element: AXElement, action: str = "AXPress") -> bool:
        """
        Perform an accessibility action on an element.
        
        Common actions:
        - AXPress: Click/activate
        - AXShowMenu: Show context menu
        - AXDecrement/AXIncrement: For steppers
        - AXRaise: Bring window to front
        
        Returns:
            True if action succeeded
        """
        try:
            if action not in element.actions:
                logger.warning(f"Action '{action}' not available on {element}. Available: {element.actions}")
                return False
            
            error = AXUIElementPerformAction(element.ax_ref, action)
            
            if error == kAXErrorSuccess:
                logger.info(f"Successfully performed {action} on {element}")
                return True
            else:
                logger.warning(f"Failed to perform {action}: error code {error}")
                return False
                
        except Exception as e:
            logger.error(f"Exception performing action: {e}")
            return False
    
    def set_value(self, element: AXElement, value: str) -> bool:
        """
        Set the value of an element (e.g., text field).
        
        Returns:
            True if value was set successfully
        """
        try:
            from ApplicationServices import AXUIElementSetAttributeValue
            
            error = AXUIElementSetAttributeValue(element.ax_ref, "AXValue", value)
            
            if error == kAXErrorSuccess:
                logger.info(f"Set value of {element} to '{value}'")
                return True
            else:
                logger.warning(f"Failed to set value: error code {error}")
                return False
                
        except Exception as e:
            logger.error(f"Exception setting value: {e}")
            return False
    
    def get_element_at_position(self, x: int, y: int) -> Optional[AXElement]:
        """
        Get the UI element at specific screen coordinates.
        
        Args:
            x, y: Screen coordinates (top-left origin)
            
        Returns:
            AXElement at that position or None
        """
        try:
            # Convert to macOS coordinates
            macos_y = self._screen_height - y
            
            system_wide = AXUIElementCreateSystemWide()
            error, element_ref = AXUIElementCopyElementAtPosition(system_wide, x, macos_y, None)
            
            if error == kAXErrorSuccess and element_ref:
                return self._element_to_axelement(element_ref)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get element at position: {e}")
            return None
    
    def invalidate_cache(self):
        """Clear the element cache (call when UI changes)."""
        self._element_cache.clear()
        self._cache_timestamp = 0
        logger.debug("Accessibility cache invalidated")
    
    def get_frontmost_app_info(self) -> Dict[str, str]:
        """Get information about the frontmost app."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            frontmost_app = workspace.frontmostApplication()
            
            if not frontmost_app:
                return {"app": "Unknown", "window": ""}
            
            app_name = frontmost_app.localizedName()
            
            # Try to get window title
            pid = frontmost_app.processIdentifier()
            ax_app = AXUIElementCreateApplication(pid)
            
            window_title = ""
            focused_window = self._get_attribute(ax_app, "AXFocusedWindow")
            if focused_window:
                window_title = self._get_attribute(focused_window, "AXTitle") or ""
            
            return {
                "app": app_name or "Unknown",
                "window": window_title
            }
            
        except Exception as e:
            logger.error(f"Failed to get app info: {e}")
            return {"app": "Unknown", "window": ""}


# Convenience functions for backward compatibility
def get_ui_tree() -> Optional[AXElement]:
    """Get UI tree for frontmost app."""
    api = AccessibilityAPI()
    return api.get_ui_tree()


def find_element_by_text(text: str) -> Optional[AXElement]:
    """Find element by text content."""
    api = AccessibilityAPI()
    return api.find_element_by_text(text)


def perform_element_action(element: AXElement, action: str = "AXPress") -> bool:
    """Perform action on element."""
    api = AccessibilityAPI()
    return api.perform_action(element, action)
