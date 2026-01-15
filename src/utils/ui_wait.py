"""
Event-Driven UI Wait System for macOS

Replaces fixed time.sleep() calls with intelligent waiting based on:
1. UI Tree Stability - Wait until accessibility tree stops changing
2. Element Appearance - Wait for specific elements to appear
3. Element Disappearance - Wait for loading indicators to vanish
4. Window Ready - Wait for window to be fully interactive

Uses macOS Accessibility Tree (AXUIElement) for event-driven observation.
"""

import time
import hashlib
from typing import Optional, List, Dict, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from ..utils.logging import logger

try:
    from .accessibility_api import AccessibilityAPI, AXElement, PYOBJC_AVAILABLE
except ImportError:
    PYOBJC_AVAILABLE = False
    logger.warning("Accessibility API not available for event-driven waiting")


class WaitCondition(str, Enum):
    """Types of wait conditions."""
    UI_STABLE = "ui_stable"           # Wait for UI tree to stop changing
    ELEMENT_PRESENT = "element_present"  # Wait for element to appear
    ELEMENT_ABSENT = "element_absent"    # Wait for element to disappear
    ELEMENT_ENABLED = "element_enabled"  # Wait for element to become enabled
    ELEMENT_FOCUSED = "element_focused"  # Wait for element to get focus
    WINDOW_READY = "window_ready"        # Wait for window to be interactive
    APP_FRONTMOST = "app_frontmost"      # Wait for app to be frontmost


@dataclass
class WaitResult:
    """Result of a wait operation."""
    success: bool
    condition: WaitCondition
    waited_ms: float
    element: Optional[AXElement] = None
    reason: str = ""


@dataclass
class UISnapshot:
    """Snapshot of UI state for comparison."""
    tree_hash: str
    element_count: int
    focused_element: Optional[str] = None
    window_title: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    
    def matches(self, other: 'UISnapshot', tolerance: int = 2) -> bool:
        """
        Check if two snapshots match (UI is stable).
        
        Args:
            other: Another snapshot to compare
            tolerance: Max element count difference allowed
        """
        if self.tree_hash == other.tree_hash:
            return True
        # Allow minor changes (e.g., cursor blink)
        return abs(self.element_count - other.element_count) <= tolerance


class UIWaitSystem:
    """
    Event-driven waiting system using macOS Accessibility Tree.
    
    Instead of fixed sleeps, this monitors the UI and proceeds when:
    - The UI tree stabilizes (stops changing)
    - A specific element appears/disappears
    - Window becomes interactive
    
    This makes the agent faster (no over-sleeping) and more reliable
    (no under-sleeping when UI is slow).
    """
    
    def __init__(self, 
                 poll_interval_ms: int = 50,
                 stability_threshold_ms: int = 150,
                 max_wait_ms: int = 10000):
        """
        Args:
            poll_interval_ms: How often to check UI state
            stability_threshold_ms: How long UI must be stable
            max_wait_ms: Maximum wait time before giving up
        """
        self.poll_interval_ms = poll_interval_ms
        self.stability_threshold_ms = stability_threshold_ms
        self.max_wait_ms = max_wait_ms
        
        # Initialize accessibility API
        self._api: Optional[AccessibilityAPI] = None
        self._init_api()
        
        # Statistics
        self.total_waits = 0
        self.total_saved_ms = 0
        self.wait_history: List[WaitResult] = []
    
    def _init_api(self):
        """Initialize accessibility API if available."""
        if PYOBJC_AVAILABLE:
            try:
                self._api = AccessibilityAPI()
                logger.debug("UIWaitSystem: Accessibility API initialized")
            except Exception as e:
                logger.warning(f"UIWaitSystem: Failed to init Accessibility API: {e}")
                self._api = None
        else:
            logger.warning("UIWaitSystem: PyObjC not available, using fallback timing")
    
    def _get_ui_snapshot(self) -> Optional[UISnapshot]:
        """Get current UI state snapshot for comparison."""
        if not self._api:
            return None
        
        try:
            # Invalidate cache to get fresh tree
            self._api.invalidate_cache()
            
            # Get UI tree
            tree = self._api.get_ui_tree(max_depth=4, use_cache=False)
            if not tree:
                return None
            
            # Count elements and create hash
            element_count = self._count_elements(tree)
            tree_str = self._serialize_tree(tree)
            tree_hash = hashlib.md5(tree_str.encode()).hexdigest()
            
            # Get focused element
            focused = self._find_focused_element(tree)
            focused_str = str(focused) if focused else None
            
            # Get window title
            window_title = None
            for child in tree.children:
                if child.role == "AXWindow":
                    window_title = child.title
                    break
            
            return UISnapshot(
                tree_hash=tree_hash,
                element_count=element_count,
                focused_element=focused_str,
                window_title=window_title
            )
            
        except Exception as e:
            logger.debug(f"Failed to get UI snapshot: {e}")
            return None
    
    def _count_elements(self, element: AXElement) -> int:
        """Count total elements in tree."""
        count = 1
        for child in element.children:
            count += self._count_elements(child)
        return count
    
    def _serialize_tree(self, element: AXElement, depth: int = 0) -> str:
        """Serialize tree to string for hashing."""
        parts = [f"{element.role}:{element.title}:{element.value}"]
        for child in element.children[:20]:  # Limit to prevent huge strings
            parts.append(self._serialize_tree(child, depth + 1))
        return "|".join(parts)
    
    def _find_focused_element(self, element: AXElement) -> Optional[AXElement]:
        """Find the currently focused element in tree."""
        if element.focused:
            return element
        for child in element.children:
            focused = self._find_focused_element(child)
            if focused:
                return focused
        return None
    
    def _find_element_in_tree(self, tree: AXElement, text: Optional[str] = None, 
                               role: Optional[str] = None) -> Optional[AXElement]:
        """Find element matching criteria in tree."""
        # Check current element
        if role and tree.role != role:
            pass  # Role doesn't match
        elif text:
            text_lower = text.lower()
            title = (tree.title or "").lower()
            value = (tree.value or "").lower()
            desc = (tree.description or "").lower()
            if text_lower in title or text_lower in value or text_lower in desc:
                if not role or tree.role == role:
                    return tree
        elif role and tree.role == role:
            return tree
        
        # Check children
        for child in tree.children:
            found = self._find_element_in_tree(child, text, role)
            if found:
                return found
        
        return None
    
    def wait_for_ui_stable(self, 
                           max_wait_ms: Optional[int] = None,
                           stability_ms: Optional[int] = None) -> WaitResult:
        """
        Wait for UI to stabilize (stop changing).
        
        This is the primary replacement for time.sleep() - it waits
        until the accessibility tree stops changing, then returns.
        
        Args:
            max_wait_ms: Maximum time to wait (default: self.max_wait_ms)
            stability_ms: How long UI must be stable (default: self.stability_threshold_ms)
            
        Returns:
            WaitResult with success status and timing info
        """
        max_wait = max_wait_ms or self.max_wait_ms
        stability_threshold = stability_ms or self.stability_threshold_ms
        
        start_time = time.time()
        self.total_waits += 1
        
        # Fallback if no accessibility API
        if not self._api:
            fallback_ms = min(300, max_wait)
            time.sleep(fallback_ms / 1000)
            return WaitResult(
                success=True,
                condition=WaitCondition.UI_STABLE,
                waited_ms=fallback_ms,
                reason="Fallback timing (no accessibility API)"
            )
        
        # Get initial snapshot
        prev_snapshot = self._get_ui_snapshot()
        stable_since: Optional[float] = None
        
        poll_interval_sec = self.poll_interval_ms / 1000
        stability_threshold_sec = stability_threshold / 1000
        max_wait_sec = max_wait / 1000
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed >= max_wait_sec:
                waited_ms = elapsed * 1000
                result = WaitResult(
                    success=False,
                    condition=WaitCondition.UI_STABLE,
                    waited_ms=waited_ms,
                    reason="Timeout waiting for UI stability"
                )
                self.wait_history.append(result)
                return result
            
            # Get current snapshot
            current_snapshot = self._get_ui_snapshot()
            
            if current_snapshot and prev_snapshot:
                if current_snapshot.matches(prev_snapshot):
                    # UI is stable
                    if stable_since is None:
                        stable_since = time.time()
                    elif (time.time() - stable_since) >= stability_threshold_sec:
                        # Stable for long enough!
                        waited_ms = elapsed * 1000
                        
                        # Calculate time saved vs fixed sleep
                        typical_sleep = 500  # What we might have slept
                        saved = max(0, typical_sleep - waited_ms)
                        self.total_saved_ms += saved
                        
                        result = WaitResult(
                            success=True,
                            condition=WaitCondition.UI_STABLE,
                            waited_ms=waited_ms,
                            reason=f"UI stable after {waited_ms:.0f}ms"
                        )
                        self.wait_history.append(result)
                        logger.debug(f"UI stable after {waited_ms:.0f}ms (saved ~{saved:.0f}ms)")
                        return result
                else:
                    # UI changed, reset stability counter
                    stable_since = None
            
            prev_snapshot = current_snapshot
            time.sleep(poll_interval_sec)
    
    def wait_for_element(self,
                         text: Optional[str] = None,
                         role: Optional[str] = None,
                         timeout_ms: Optional[int] = None) -> WaitResult:
        """
        Wait for a specific element to appear in the UI.
        
        Args:
            text: Text to search for in element title/value/description
            role: AX role to match (e.g., "AXButton", "AXTextField")
            timeout_ms: Maximum time to wait
            
        Returns:
            WaitResult with found element if successful
        """
        if not text and not role:
            return WaitResult(
                success=False,
                condition=WaitCondition.ELEMENT_PRESENT,
                waited_ms=0,
                reason="Must specify text or role to wait for"
            )
        
        max_wait = timeout_ms or self.max_wait_ms
        start_time = time.time()
        self.total_waits += 1
        
        # Fallback if no accessibility API
        if not self._api:
            time.sleep(min(500, max_wait) / 1000)
            return WaitResult(
                success=True,  # Assume success
                condition=WaitCondition.ELEMENT_PRESENT,
                waited_ms=min(500, max_wait),
                reason="Fallback timing (no accessibility API)"
            )
        
        poll_interval_sec = self.poll_interval_ms / 1000
        max_wait_sec = max_wait / 1000
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed >= max_wait_sec:
                waited_ms = elapsed * 1000
                result = WaitResult(
                    success=False,
                    condition=WaitCondition.ELEMENT_PRESENT,
                    waited_ms=waited_ms,
                    reason=f"Timeout waiting for element: text='{text}', role='{role}'"
                )
                self.wait_history.append(result)
                return result
            
            # Search for element
            self._api.invalidate_cache()
            
            if text:
                element = self._api.find_element_by_text(text, use_cache=False)
            else:
                elements = self._api.find_elements_by_role(role, use_cache=False)
                element = elements[0] if elements else None
            
            if element:
                waited_ms = elapsed * 1000
                result = WaitResult(
                    success=True,
                    condition=WaitCondition.ELEMENT_PRESENT,
                    waited_ms=waited_ms,
                    element=element,
                    reason=f"Found element after {waited_ms:.0f}ms"
                )
                self.wait_history.append(result)
                logger.debug(f"Element found after {waited_ms:.0f}ms: {element}")
                return result
            
            time.sleep(poll_interval_sec)
    
    def wait_for_element_gone(self,
                               text: Optional[str] = None,
                               role: Optional[str] = None,
                               timeout_ms: Optional[int] = None) -> WaitResult:
        """
        Wait for a specific element to disappear (e.g., loading spinner).
        
        Args:
            text: Text to search for
            role: AX role to match
            timeout_ms: Maximum time to wait
            
        Returns:
            WaitResult indicating if element disappeared
        """
        max_wait = timeout_ms or self.max_wait_ms
        start_time = time.time()
        self.total_waits += 1
        
        if not self._api:
            time.sleep(min(300, max_wait) / 1000)
            return WaitResult(
                success=True,
                condition=WaitCondition.ELEMENT_ABSENT,
                waited_ms=min(300, max_wait),
                reason="Fallback timing"
            )
        
        poll_interval_sec = self.poll_interval_ms / 1000
        max_wait_sec = max_wait / 1000
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed >= max_wait_sec:
                return WaitResult(
                    success=False,
                    condition=WaitCondition.ELEMENT_ABSENT,
                    waited_ms=elapsed * 1000,
                    reason="Timeout - element still present"
                )
            
            self._api.invalidate_cache()
            
            if text:
                element = self._api.find_element_by_text(text, use_cache=False)
            else:
                elements = self._api.find_elements_by_role(role, use_cache=False)
                element = elements[0] if elements else None
            
            if not element:
                waited_ms = elapsed * 1000
                result = WaitResult(
                    success=True,
                    condition=WaitCondition.ELEMENT_ABSENT,
                    waited_ms=waited_ms,
                    reason=f"Element gone after {waited_ms:.0f}ms"
                )
                self.wait_history.append(result)
                return result
            
            time.sleep(poll_interval_sec)
    
    def wait_for_window_ready(self, 
                               app_name: Optional[str] = None,
                               timeout_ms: Optional[int] = None) -> WaitResult:
        """
        Wait for window to be fully interactive.
        
        Checks that:
        - Window has a title
        - Window contains interactive elements
        - UI is stable
        
        Args:
            app_name: Optional app name to wait for
            timeout_ms: Maximum time to wait
        """
        max_wait = timeout_ms or self.max_wait_ms
        start_time = time.time()
        self.total_waits += 1
        
        if not self._api:
            time.sleep(min(500, max_wait) / 1000)
            return WaitResult(
                success=True,
                condition=WaitCondition.WINDOW_READY,
                waited_ms=min(500, max_wait),
                reason="Fallback timing"
            )
        
        poll_interval_sec = self.poll_interval_ms / 1000
        max_wait_sec = max_wait / 1000
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed >= max_wait_sec:
                return WaitResult(
                    success=False,
                    condition=WaitCondition.WINDOW_READY,
                    waited_ms=elapsed * 1000,
                    reason="Timeout waiting for window"
                )
            
            try:
                self._api.invalidate_cache()
                app_info = self._api.get_frontmost_app_info()
                
                # Check app name if specified
                if app_name and app_name.lower() not in app_info.get("app", "").lower():
                    time.sleep(poll_interval_sec)
                    continue
                
                # Check window has title
                if not app_info.get("window"):
                    time.sleep(poll_interval_sec)
                    continue
                
                # Get tree and check for interactive elements
                tree = self._api.get_ui_tree(max_depth=3, use_cache=False)
                if not tree:
                    time.sleep(poll_interval_sec)
                    continue
                
                # Check for common interactive elements
                interactive_roles = ["AXButton", "AXTextField", "AXLink", "AXMenuItem"]
                has_interactive = False
                for role in interactive_roles:
                    elements = self._api.find_elements_by_role(role, use_cache=False)
                    if elements:
                        has_interactive = True
                        break
                
                if has_interactive:
                    # Now wait for stability
                    stability_result = self.wait_for_ui_stable(
                        max_wait_ms=min(1000, max_wait - int(elapsed * 1000))
                    )
                    
                    waited_ms = (time.time() - start_time) * 1000
                    result = WaitResult(
                        success=True,
                        condition=WaitCondition.WINDOW_READY,
                        waited_ms=waited_ms,
                        reason=f"Window ready after {waited_ms:.0f}ms"
                    )
                    self.wait_history.append(result)
                    return result
                
            except Exception as e:
                logger.debug(f"Error checking window: {e}")
            
            time.sleep(poll_interval_sec)
    
    def smart_wait_after_action(self, action_type: str) -> WaitResult:
        """
        Smart wait that adapts based on action type.
        
        Different actions need different wait strategies:
        - Click: Wait for UI to stabilize (something should change)
        - Type: Minimal wait (text input is usually immediate)
        - Hotkey: Wait for potential window/menu changes
        - Navigation: Wait for new content to load
        
        Args:
            action_type: Type of action just performed
            
        Returns:
            WaitResult with timing info
        """
        action_lower = action_type.lower()
        
        if "type" in action_lower or "write" in action_lower:
            # Typing is usually instant, minimal wait
            return self.wait_for_ui_stable(max_wait_ms=200, stability_ms=50)
        
        elif "click" in action_lower:
            # Click should trigger UI change
            return self.wait_for_ui_stable(max_wait_ms=2000, stability_ms=150)
        
        elif "hotkey" in action_lower or "key" in action_lower:
            # Hotkeys might open menus/windows
            return self.wait_for_ui_stable(max_wait_ms=1500, stability_ms=200)
        
        elif any(x in action_lower for x in ["navigate", "go to", "open"]):
            # Navigation needs more time
            return self.wait_for_ui_stable(max_wait_ms=5000, stability_ms=300)
        
        else:
            # Default: wait for stability
            return self.wait_for_ui_stable()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get wait statistics."""
        if not self.wait_history:
            return {
                "total_waits": 0,
                "avg_wait_ms": 0,
                "total_saved_ms": 0,
                "success_rate": 0
            }
        
        total_wait_time = sum(w.waited_ms for w in self.wait_history)
        successes = sum(1 for w in self.wait_history if w.success)
        
        return {
            "total_waits": self.total_waits,
            "avg_wait_ms": total_wait_time / len(self.wait_history),
            "total_saved_ms": self.total_saved_ms,
            "success_rate": successes / len(self.wait_history),
            "by_condition": self._stats_by_condition()
        }
    
    def _stats_by_condition(self) -> Dict[str, Dict]:
        """Get stats grouped by condition type."""
        by_condition = {}
        for result in self.wait_history:
            cond = result.condition.value
            if cond not in by_condition:
                by_condition[cond] = {"count": 0, "total_ms": 0, "successes": 0}
            by_condition[cond]["count"] += 1
            by_condition[cond]["total_ms"] += result.waited_ms
            if result.success:
                by_condition[cond]["successes"] += 1
        
        return by_condition


# Global instance for convenience
_ui_wait_system: Optional[UIWaitSystem] = None


def get_ui_wait_system() -> UIWaitSystem:
    """Get or create global UI wait system instance."""
    global _ui_wait_system
    if _ui_wait_system is None:
        _ui_wait_system = UIWaitSystem()
    return _ui_wait_system


# Convenience functions
def wait_for_ui_stable(max_wait_ms: int = 5000, stability_ms: int = 150) -> WaitResult:
    """Wait for UI to stabilize. Replacement for time.sleep()."""
    return get_ui_wait_system().wait_for_ui_stable(max_wait_ms, stability_ms)


def wait_for_element(text: Optional[str] = None, role: Optional[str] = None, 
                     timeout_ms: int = 10000) -> WaitResult:
    """Wait for specific element to appear."""
    return get_ui_wait_system().wait_for_element(text, role, timeout_ms)


def wait_for_element_gone(text: Optional[str] = None, role: Optional[str] = None,
                          timeout_ms: int = 10000) -> WaitResult:
    """Wait for element to disappear (e.g., loading spinner)."""
    return get_ui_wait_system().wait_for_element_gone(text, role, timeout_ms)


def wait_for_window_ready(app_name: Optional[str] = None, 
                          timeout_ms: int = 10000) -> WaitResult:
    """Wait for window to be fully interactive."""
    return get_ui_wait_system().wait_for_window_ready(app_name, timeout_ms)


def smart_wait(action_type: str) -> WaitResult:
    """Smart wait based on action type just performed."""
    return get_ui_wait_system().smart_wait_after_action(action_type)
