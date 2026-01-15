"""
Enhanced Executor - Uses native accessibility API and human-like cursor control.
This is 10-100x faster than the old blind executor for UI interactions.
"""

import time
from typing import List, Dict, Optional
from ..utils.logging import logger

try:
    from ..utils.accessibility_api import AccessibilityAPI
    from ..utils.cursor_controller import HumanCursor
    from ..utils.element_interactor import ElementInteractor
    from ..utils.screen_understanding_coordinator import ScreenUnderstandingCoordinator
    ENHANCED_AVAILABLE = True
except ImportError as e:
    ENHANCED_AVAILABLE = False
    logger.warning(f"Enhanced features not available: {e}")

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class EnhancedExecutor:
    """
    Enhanced executor using native accessibility API and human-like cursor.
    
    Features:
    - Native element finding (0.002s vs 2-3s for OCR)
    - Human-like cursor movement (undetectable)
    - Instant text entry via AXValue
    - Smart fallbacks when native methods fail
    """
    
    def __init__(self, use_human_cursor: bool = True):
        """
        Initialize enhanced executor.
        
        Args:
            use_human_cursor: Use human-like cursor movement vs simple pyautogui
        """
        if not ENHANCED_AVAILABLE:
            raise RuntimeError("Enhanced features not available. Install dependencies.")
        
        self.accessibility_api = AccessibilityAPI()
        self.cursor = HumanCursor() if use_human_cursor else None
        self.interactor = ElementInteractor(
            prefer_accessibility=True,
            use_human_cursor=use_human_cursor
        )
        self.coordinator = ScreenUnderstandingCoordinator(
            use_accessibility=True,
            use_vlm=False,  # Skip VLM for speed, use only if needed
            use_ocr=True
        )
        
        self.stats = {
            "native_actions": 0,
            "cursor_actions": 0,
            "fallback_actions": 0,
            "total_time": 0.0
        }
    
    def execute_action(self, action: str, task: str = None) -> Dict:
        """
        Execute a single action using enhanced methods.
        
        Supported action formats:
        - "click:element_name" → Find and click element by text
        - "type:field_name:text" → Find field and type text
        - "hotkey:key1,key2" → Press keyboard shortcut
        - "key:keyname" → Press single key
        - "wait:seconds" → Wait
        - "click:x,y" → Click at coordinates (fallback)
        
        Returns:
            {"success": bool, "method": str, "time": float, "error": str}
        """
        start_time = time.time()
        
        try:
            # Parse action
            if action.startswith("click:"):
                target = action[6:].strip()
                
                # Check if it's coordinates (x,y) or element name
                if "," in target and all(p.strip().isdigit() for p in target.split(",")):
                    # Coordinate-based click (fallback)
                    coords = target.split(",")
                    x, y = int(coords[0]), int(coords[1])
                    
                    if self.cursor:
                        self.cursor.move_to(x, y)
                        self.cursor.click()
                        method = "cursor_coordinate"
                    else:
                        pyautogui.click(x, y)
                        method = "pyautogui_coordinate"
                    
                    self.stats["cursor_actions"] += 1
                    logger.info(f"  ↳ click({x}, {y}) via {method}")
                    
                else:
                    # Element-based click (preferred)
                    # First try frontmost app for speed
                    element = self.accessibility_api.find_element_by_text(target)
                    
                    # If not found in frontmost, search ALL apps
                    if not element:
                        logger.debug(f"'{target}' not in frontmost app, searching all apps...")
                        element = self.accessibility_api.find_element_anywhere(target)
                    
                    if element:
                        # Try native action first
                        if "AXPress" in element.actions:
                            success = self.accessibility_api.perform_action(element, "AXPress")
                            if success:
                                method = "native_ax_press"
                                self.stats["native_actions"] += 1
                                logger.info(f"  ↳ native click on '{target}'")
                                return {
                                    "success": True,
                                    "method": method,
                                    "time": time.time() - start_time,
                                    "error": None
                                }
                        
                        # Fallback to cursor
                        self.interactor.click_element(element)
                        method = "cursor_element"
                        self.stats["cursor_actions"] += 1
                        logger.info(f"  ↳ cursor click on '{target}'")
                    else:
                        return {
                            "success": False,
                            "method": "element_not_found",
                            "time": time.time() - start_time,
                            "error": f"Element '{target}' not found"
                        }
            
            elif action.startswith("type:"):
                # Format: "type:field_name:text" or "type:text"
                parts = action[5:].split(":", 1)
                
                if len(parts) == 2:
                    # "type:field_name:text"
                    field_name, text = parts
                    # First try frontmost app
                    element = self.accessibility_api.find_element_by_text(field_name)
                    
                    # If not found, search all apps
                    if not element:
                        logger.debug(f"Field '{field_name}' not in frontmost app, searching all...")
                        element = self.accessibility_api.find_element_anywhere(field_name)
                    
                    if element:
                        # Try native AXValue (instant!)
                        success = self.accessibility_api.set_value(element, text)
                        if success:
                            method = "native_ax_value"
                            self.stats["native_actions"] += 1
                            logger.info(f"  ↳ instant type '{text}' into '{field_name}'")
                        else:
                            # Fallback to typing
                            self.interactor.type_text(element, text)
                            method = "cursor_type"
                            self.stats["cursor_actions"] += 1
                            logger.info(f"  ↳ typed '{text}' into '{field_name}'")
                    else:
                        return {
                            "success": False,
                            "method": "field_not_found",
                            "time": time.time() - start_time,
                            "error": f"Field '{field_name}' not found"
                        }
                else:
                    # "type:text" - type at current position
                    text = parts[0]
                    pyautogui.write(text, interval=0.02)
                    method = "pyautogui_type"
                    self.stats["fallback_actions"] += 1
                    logger.info(f"  ↳ type '{text}'")
            
            elif action.startswith("hotkey:"):
                # Keyboard shortcut
                keys = action[7:].split(",")
                keys = [k.strip() for k in keys]
                
                # macOS key mapping
                key_mapping = {
                    'cmd': 'command', 'opt': 'option', 'alt': 'option',
                    'ctrl': 'control', 'del': 'delete', 'ret': 'return',
                    'esc': 'escape', 'grave': '`'
                }
                keys = [key_mapping.get(k.lower(), k) for k in keys]
                
                pyautogui.hotkey(*keys)
                method = "hotkey"
                self.stats["fallback_actions"] += 1
                logger.info(f"  ↳ hotkey({', '.join(keys)})")
            
            elif action.startswith("key:"):
                # Single key press
                key = action[4:].strip()
                pyautogui.press(key)
                method = "keypress"
                self.stats["fallback_actions"] += 1
                logger.info(f"  ↳ press({key})")
            
            elif action.startswith("wait:"):
                # Wait
                secs = float(action[5:])
                time.sleep(secs)
                method = "wait"
                logger.debug(f"  ↳ wait({secs}s)")
            
            else:
                return {
                    "success": False,
                    "method": "unknown_action",
                    "time": time.time() - start_time,
                    "error": f"Unknown action format: {action}"
                }
            
            # Success
            exec_time = time.time() - start_time
            self.stats["total_time"] += exec_time
            
            return {
                "success": True,
                "method": method,
                "time": exec_time,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"  ✗ Enhanced action failed: {action} - {e}")
            return {
                "success": False,
                "method": "exception",
                "time": time.time() - start_time,
                "error": str(e)
            }
    
    def execute_batch(self, actions: List[str], task: str = None) -> Dict:
        """
        Execute a batch of actions.
        
        Args:
            actions: List of action strings
            task: Optional task description for logging
            
        Returns:
            {"success": bool, "executed": int, "stats": dict, "error": str}
        """
        results = []
        
        for i, action in enumerate(actions):
            result = self.execute_action(action, task)
            results.append(result)
            
            if not result["success"]:
                logger.error(f"  Action {i+1}/{len(actions)} failed: {result['error']}")
                return {
                    "success": False,
                    "executed": i,
                    "results": results,
                    "stats": self.stats,
                    "error": result["error"]
                }
            
            # Small delay between actions
            time.sleep(0.1)
        
        return {
            "success": True,
            "executed": len(actions),
            "results": results,
            "stats": self.stats.copy(),
            "error": None
        }
    
    def get_statistics(self) -> Dict:
        """Get execution statistics."""
        total_actions = sum([
            self.stats["native_actions"],
            self.stats["cursor_actions"],
            self.stats["fallback_actions"]
        ])
        
        return {
            **self.stats,
            "total_actions": total_actions,
            "avg_time_per_action": self.stats["total_time"] / total_actions if total_actions > 0 else 0,
            "native_percentage": 100 * self.stats["native_actions"] / total_actions if total_actions > 0 else 0
        }


# Convenience function for backward compatibility
def execute_enhanced_batch(actions: List[str], task: str = None, use_human_cursor: bool = True) -> Dict:
    """
    Execute actions using enhanced executor.
    
    Args:
        actions: List of action strings
        task: Optional task description
        use_human_cursor: Use human-like cursor movement
        
    Returns:
        Execution result dict
    """
    if not ENHANCED_AVAILABLE:
        logger.warning("Enhanced executor not available, falling back to basic executor")
        from .blind_executor import execute_blind_batch
        return execute_blind_batch(actions, task)
    
    executor = EnhancedExecutor(use_human_cursor=use_human_cursor)
    result = executor.execute_batch(actions, task)
    
    # Log statistics
    if result["success"]:
        stats = executor.get_statistics()
        logger.info(f"  📊 Stats: {stats['native_actions']} native, {stats['cursor_actions']} cursor, {stats['fallback_actions']} fallback")
        logger.info(f"  ⚡ Speed: {stats['avg_time_per_action']:.3f}s per action, {stats['native_percentage']:.0f}% native")
    
    return result
