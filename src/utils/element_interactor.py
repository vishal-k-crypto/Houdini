"""
Element-Based Interaction System
Interact with UI elements by properties rather than coordinates.

Hierarchy of interaction methods:
1. Native accessibility actions (AXPress, AXValue) - Fastest, most reliable
2. Human-like cursor control - For elements without native actions
3. Fallback to simple pyautogui - Last resort

This makes the automation more robust against UI changes.
"""

from typing import Optional
from ..utils.logging import logger

try:
    from .accessibility_api import AccessibilityAPI, AXElement
    from .cursor_controller import HumanCursor
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    logger.error("Required modules (accessibility_api, cursor_controller) not available")

import pyautogui
import time


class ElementInteractor:
    """
    High-level interface for interacting with UI elements.
    Automatically chooses the best interaction method.
    """
    
    def __init__(self, prefer_accessibility: bool = True, use_human_cursor: bool = True):
        """
        Initialize element interactor.
        
        Args:
            prefer_accessibility: Try native accessibility actions first
            use_human_cursor: Use human-like cursor movement vs simple pyautogui
        """
        self.prefer_accessibility = prefer_accessibility
        self.use_human_cursor = use_human_cursor
        
        if MODULES_AVAILABLE:
            self.accessibility_api = AccessibilityAPI()
            self.human_cursor = HumanCursor() if use_human_cursor else None
        else:
            self.accessibility_api = None
            self.human_cursor = None
    
    def click_element(self, element, action: str = "AXPress") -> bool:
        """
        Click an element using the best available method.
        
        Args:
            element: AXElement or UIElement
            action: Accessibility action to try (default: AXPress for click)
            
        Returns:
            True if clicked successfully
        """
        # Method 1: Try native accessibility action
        if self.prefer_accessibility and isinstance(element, AXElement):
            if action in element.actions:
                logger.info(f"Using native accessibility action: {action}")
                success = self.accessibility_api.perform_action(element, action)
                if success:
                    return True
                logger.warning(f"Native action failed, falling back to cursor")
        
        # Method 2: Human-like cursor control
        if element.center:
            x, y = element.center
            
            if self.human_cursor:
                logger.info(f"Using human-like cursor to click {element}")
                target_size = element.size if hasattr(element, 'size') and element.size else (10, 10)
                self.human_cursor.move_to(x, y, target_size=target_size)
                self.human_cursor.click()
                return True
            else:
                # Method 3: Simple pyautogui fallback
                logger.info(f"Using simple click on {element}")
                pyautogui.click(x, y)
                return True
        
        logger.error(f"Could not click element: {element}")
        return False
    
    def type_text(self, element, text: str, use_native: bool = True) -> bool:
        """
        Type text into an element (text field, search box, etc.).
        
        Args:
            element: Target element
            text: Text to type
            use_native: Try setting AXValue directly (faster)
            
        Returns:
            True if successful
        """
        # Method 1: Native AXValue (instant, no typing animation)
        if use_native and isinstance(element, AXElement):
            logger.info(f"Setting text via AXValue: '{text}'")
            success = self.accessibility_api.set_value(element, text)
            if success:
                return True
            logger.warning("AXValue failed, falling back to typing")
        
        # Method 2: Focus element then type
        # First click to focus
        self.click_element(element)
        time.sleep(0.1)
        
        # Type with human-like timing
        logger.info(f"Typing text (human-like): '{text}'")
        for char in text:
            pyautogui.write(char, interval=0.05)  # Human-like typing speed
            # Add occasional variation
            if len(text) > 10 and char == ' ':
                time.sleep(0.1)  # Slightly longer pauses at spaces
        
        return True
    
    def select_menu_item(self, menu_path: list) -> bool:
        """
        Select a menu item by navigating the hierarchy.
        
        Args:
            menu_path: List of menu names, e.g., ["File", "Open", "Recent"]
            
        Returns:
            True if successful
        """
        if not self.accessibility_api:
            logger.error("Accessibility API not available for menu navigation")
            return False
        
        try:
            # Get menu bar
            tree = self.accessibility_api.get_ui_tree(max_depth=3)
            if not tree:
                return False
            
            # Navigate menu hierarchy
            current_elements = [tree]
            
            for menu_name in menu_path:
                found = False
                for element in current_elements:
                    # Search in children
                    for child in element.children:
                        if menu_name.lower() in (child.title or "").lower():
                            # Found it, perform action
                            if "AXPress" in child.actions:
                                self.accessibility_api.perform_action(child, "AXPress")
                                time.sleep(0.2)  # Wait for menu to open
                                
                                # Get updated tree for next level
                                tree = self.accessibility_api.get_ui_tree(max_depth=3, use_cache=False)
                                current_elements = tree.children if tree else []
                                found = True
                                break
                    if found:
                        break
                
                if not found:
                    logger.error(f"Menu item '{menu_name}' not found")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Menu selection failed: {e}")
            return False
    
    def checkbox_set_state(self, element, checked: bool) -> bool:
        """
        Set checkbox state.
        
        Args:
            element: Checkbox element
            checked: True to check, False to uncheck
            
        Returns:
            True if successful
        """
        if isinstance(element, AXElement):
            current_value = element.value
            
            # Convert to boolean
            is_checked = current_value == 1 or current_value == "1" or current_value is True
            
            if is_checked == checked:
                logger.info(f"Checkbox already in desired state: {checked}")
                return True
            
            # Toggle by clicking
            return self.click_element(element)
        
        # Fallback: just click it
        return self.click_element(element)
    
    def scroll(self, direction: str = "down", amount: int = 3):
        """
        Scroll the screen or focused element.
        
        Args:
            direction: "up", "down", "left", "right"
            amount: Number of scroll increments
        """
        if direction == "down":
            pyautogui.scroll(-amount)
        elif direction == "up":
            pyautogui.scroll(amount)
        elif direction == "left":
            pyautogui.hscroll(-amount)
        elif direction == "right":
            pyautogui.hscroll(amount)
        
        logger.info(f"Scrolled {direction} by {amount}")
    
    def drag_element(self, element, target_x: int, target_y: int) -> bool:
        """
        Drag an element to a target position.
        
        Args:
            element: Element to drag
            target_x, target_y: Target coordinates
            
        Returns:
            True if successful
        """
        if not element.center:
            logger.error("Element has no position information")
            return False
        
        start_x, start_y = element.center
        
        if self.human_cursor:
            self.human_cursor.drag(start_x, start_y, target_x, target_y)
        else:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(target_x - start_x, target_y - start_y, duration=0.5)
        
        return True


# Convenience functions
_global_interactor = None

def get_interactor() -> ElementInteractor:
    """Get global element interactor instance."""
    global _global_interactor
    if _global_interactor is None:
        _global_interactor = ElementInteractor()
    return _global_interactor


def click(element) -> bool:
    """Quick function to click an element."""
    return get_interactor().click_element(element)


def type_text(element, text: str) -> bool:
    """Quick function to type text."""
    return get_interactor().type_text(element, text)
