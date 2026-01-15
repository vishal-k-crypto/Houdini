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
        """
        Get main display height for coordinate conversion.
        
        Uses NSScreen for logical resolution (matches PyAutoGUI).
        Falls back to CGDisplayBounds if needed.
        """
        try:
            # Use NSScreen for logical resolution (matches PyAutoGUI)
            screen = AppKit.NSScreen.mainScreen()
            if screen:
                frame = screen.frame()
                height = int(frame.size.height)
                logger.debug(f"AccessibilityAPI screen height: {height} (from NSScreen)")
                return height
        except Exception as e:
            logger.debug(f"NSScreen failed: {e}")
        
        try:
            display_bounds = CGDisplayBounds(CGMainDisplayID())
            return int(display_bounds.size.height)
        except:
            return 1080  # Fallback
    
    def _convert_coords_to_screen(self, macos_x: float, macos_y: float) -> Tuple[int, int]:
        """
        Convert macOS AXPosition coordinates to screen coordinates.
        
        IMPORTANT: AXPosition values from Accessibility API are already in
        screen coordinates with (0,0) at TOP-LEFT corner. No conversion needed.
        
        The common misconception is that macOS uses bottom-left origin, but
        that's only for Quartz/Core Graphics drawing, NOT for Accessibility API.
        """
        # AXPosition is already in screen coords (top-left origin)
        return (int(macos_x), int(macos_y))
    
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
            
            # Get position and size (with robust error handling)
            position = None
            size = None
            try:
                ax_position = self._get_attribute(ax_ref, "AXPosition")
                ax_size = self._get_attribute(ax_ref, "AXSize")
                
                if ax_position and ax_size:
                    # Handle different position representations
                    if hasattr(ax_position, 'x'):
                        macos_x = ax_position.x
                        macos_y = ax_position.y
                    elif isinstance(ax_position, (tuple, list)) and len(ax_position) >= 2:
                        macos_x, macos_y = ax_position[0], ax_position[1]
                    else:
                        # Skip position if format is unknown
                        macos_x, macos_y = None, None
                    
                    if macos_x is not None and macos_y is not None:
                        position = self._convert_coords_to_screen(macos_x, macos_y)
                    
                    # Handle different size representations
                    if hasattr(ax_size, 'width'):
                        size = (int(ax_size.width), int(ax_size.height))
                    elif isinstance(ax_size, (tuple, list)) and len(ax_size) >= 2:
                        size = (int(ax_size[0]), int(ax_size[1]))
            except Exception as e:
                # Position/size extraction failed, but element can still be useful
                logger.debug(f"Position/size extraction failed: {e}")
            
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
                
                # For AXApplication, also get menu bar and windows (not in AXChildren)
                if role == "AXApplication":
                    # Get menu bar (main menu bar, skip extras menu bar)
                    menubar_ref = self._get_attribute(ax_ref, "AXMenuBar")
                    if menubar_ref:
                        menubar = self._element_to_axelement(menubar_ref, include_children=True, max_depth=max_depth, current_depth=current_depth+1)
                        if menubar:
                            element.children.append(menubar)
                    
                    # Get windows
                    windows_refs = self._get_attribute(ax_ref, "AXWindows")
                    if windows_refs:
                        for win_ref in windows_refs[:20]:
                            win = self._element_to_axelement(win_ref, include_children=True, max_depth=max_depth, current_depth=current_depth+1)
                            if win:
                                element.children.append(win)
            
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
    
    def get_ui_tree(self, max_depth: int = 8, use_cache: bool = True) -> Optional[AXElement]:
        """
        Get the full UI element tree for the frontmost application.
        
        Args:
            max_depth: Maximum depth to traverse (8 for complex apps like Chrome)
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
    
    def get_running_apps(self) -> List[Dict]:
        """
        Get list of all running applications with their PIDs.
        
        Returns:
            List of dicts with 'name', 'bundle_id', 'pid', 'is_active'
        """
        try:
            workspace = NSWorkspace.sharedWorkspace()
            frontmost = workspace.frontmostApplication()
            frontmost_pid = frontmost.processIdentifier() if frontmost else -1
            
            apps = []
            for app in workspace.runningApplications():
                # Skip background-only apps
                if app.activationPolicy() != 0:  # NSApplicationActivationPolicyRegular = 0
                    continue
                    
                apps.append({
                    "name": app.localizedName() or "Unknown",
                    "bundle_id": app.bundleIdentifier() or "",
                    "pid": app.processIdentifier(),
                    "is_active": app.processIdentifier() == frontmost_pid
                })
            
            return apps
            
        except Exception as e:
            logger.error(f"Failed to get running apps: {e}")
            return []
    
    def get_app_by_name(self, app_name: str) -> Optional[Dict]:
        """
        Find a running app by name (case-insensitive partial match).
        
        Returns:
            Dict with app info or None if not found
        """
        apps = self.get_running_apps()
        app_name_lower = app_name.lower()
        
        # First try exact match
        for app in apps:
            if app["name"].lower() == app_name_lower:
                return app
        
        # Then try partial match
        for app in apps:
            if app_name_lower in app["name"].lower():
                return app
        
        return None
    
    def get_ui_tree_for_app(self, app_name: str, max_depth: int = 8) -> Optional[AXElement]:
        """
        Get UI element tree for a SPECIFIC application by name.
        
        This is the KEY method for fixing the "terminal only" issue.
        Instead of getting elements from frontmost app, this gets
        elements from any running app.
        
        Args:
            app_name: Name of the app (e.g., "Safari", "Chrome")
            max_depth: Maximum depth to traverse
            
        Returns:
            Root AXElement with children populated, or None if app not found
        """
        app_info = self.get_app_by_name(app_name)
        if not app_info:
            logger.warning(f"App '{app_name}' not found in running applications")
            return None
        
        try:
            ax_app = AXUIElementCreateApplication(app_info["pid"])
            tree = self._element_to_axelement(ax_app, include_children=True, max_depth=max_depth)
            logger.debug(f"Got UI tree for {app_info['name']} (PID {app_info['pid']})")
            return tree
            
        except Exception as e:
            logger.error(f"Failed to get UI tree for {app_name}: {e}")
            return None
    
    def find_element_in_app(self, app_name: str, text: str) -> Optional[AXElement]:
        """
        Find element by text in a SPECIFIC application (not just frontmost).
        
        Args:
            app_name: Name of the app to search in
            text: Text to search for
            
        Returns:
            First matching AXElement or None
        """
        tree = self.get_ui_tree_for_app(app_name)
        if not tree:
            return None
        
        results = []
        self._traverse_elements(tree, results, text_filter=text)
        return results[0] if results else None
    
    def get_all_visible_elements(self, max_apps: int = 10) -> List[AXElement]:
        """
        Get UI elements from ALL visible applications.
        
        This provides a complete picture of the screen, not just
        the frontmost app. Useful for finding elements to click
        anywhere on the desktop.
        
        Args:
            max_apps: Maximum number of apps to query (to prevent slowness)
            
        Returns:
            List of all elements across all visible apps
        """
        all_elements = []
        apps = self.get_running_apps()[:max_apps]
        
        for app_info in apps:
            try:
                ax_app = AXUIElementCreateApplication(app_info["pid"])
                tree = self._element_to_axelement(ax_app, include_children=True, max_depth=5)
                if tree:
                    # Collect all elements from this app's tree
                    results = []
                    self._traverse_elements(tree, results)
                    all_elements.extend(results)
            except Exception as e:
                logger.debug(f"Skipping {app_info['name']}: {e}")
        
        logger.debug(f"Found {len(all_elements)} elements across {len(apps)} apps")
        return all_elements
    
    def find_element_anywhere(self, text: str) -> Optional[AXElement]:
        """
        Find element by text across ALL running applications.
        
        This searches the entire desktop, not just the frontmost app.
        Use this when you need to click something that might not be
        in the current app.
        
        Args:
            text: Text to search for
            
        Returns:
            First matching AXElement or None
        """
        apps = self.get_running_apps()
        text_lower = text.lower()
        
        for app_info in apps:
            try:
                ax_app = AXUIElementCreateApplication(app_info["pid"])
                tree = self._element_to_axelement(ax_app, include_children=True, max_depth=6)
                if tree:
                    results = []
                    self._traverse_elements(tree, results, text_filter=text)
                    if results:
                        logger.info(f"Found '{text}' in {app_info['name']}")
                        return results[0]
            except Exception as e:
                logger.debug(f"Skipping {app_info['name']}: {e}")
        
        return None


# Convenience functions for backward compatibility
def get_ui_tree() -> Optional[AXElement]:
    """Get UI tree for frontmost app."""
    api = AccessibilityAPI()
    return api.get_ui_tree()


def find_element_by_text(text: str) -> Optional[AXElement]:
    """Find element by text content."""
    api = AccessibilityAPI()
    return api.find_element_by_text(text)


def find_element_anywhere(text: str) -> Optional[AXElement]:
    """Find element by text across ALL running applications."""
    api = AccessibilityAPI()
    return api.find_element_anywhere(text)


def find_element_in_app(app_name: str, text: str) -> Optional[AXElement]:
    """Find element by text in a specific application."""
    api = AccessibilityAPI()
    return api.find_element_in_app(app_name, text)


def get_ui_tree_for_app(app_name: str) -> Optional[AXElement]:
    """Get UI tree for a specific application by name."""
    api = AccessibilityAPI()
    return api.get_ui_tree_for_app(app_name)


def perform_element_action(element: AXElement, action: str = "AXPress") -> bool:
    """Perform action on element."""
    api = AccessibilityAPI()
    return api.perform_action(element, action)
