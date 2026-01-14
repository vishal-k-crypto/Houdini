"""
RecoveryHandler - Handles stuck situations and unexpected UI elements.
When the agent gets stuck, this module:
1. Detects the stuck condition
2. Analyzes the current screen
3. Determines appropriate recovery action
4. Executes recovery with full context awareness
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from .loop_state import LoopState, LoopStatus
from ..utils.logging import logger
from ..utils.gemini_client import GeminiCLI
from ..utils.accessibility_reader import (
    get_frontmost_app,
    get_ui_elements_applescript,
    format_ui_for_llm
)


@dataclass
class StuckCondition:
    """Represents a detected stuck condition."""
    detected_at: datetime
    reason: str
    screen_context: str
    loop_count: int
    last_actions: List[str]
    recovery_attempted: int = 0


@dataclass
class RecoveryAction:
    """A recovery action to take."""
    action_type: str  # "click", "key", "hotkey", "escape", "skip"
    action_value: str
    reason: str
    confidence: float


class RecoveryHandler:
    """
    Handles recovery when the agent gets stuck.
    
    Detection strategies:
    1. Same batch/action for too long
    2. Repeated failures on same action
    3. No progress for N iterations
    4. Unexpected modal/dialog detected
    
    Recovery strategies:
    1. Dismiss dialogs (Escape, click Cancel/OK)
    2. Retry with different approach
    3. Skip problematic step
    4. Request LLM guidance with full context
    """
    
    def __init__(self, 
                 cli: GeminiCLI,
                 state: LoopState,
                 stuck_threshold_seconds: float = 10.0,
                 max_same_state_iterations: int = 5,
                 max_recovery_attempts: int = 3):
        """
        Args:
            cli: Gemini client for LLM guidance
            state: Shared loop state
            stuck_threshold_seconds: Time before considering stuck
            max_same_state_iterations: Iterations on same state before stuck
            max_recovery_attempts: Max recovery attempts before giving up
        """
        self.cli = cli
        self.state = state
        self.stuck_threshold = stuck_threshold_seconds
        self.max_same_state_iterations = max_same_state_iterations
        self.max_recovery_attempts = max_recovery_attempts
        
        # Tracking
        self.last_batch_idx = -1
        self.last_action_idx = -1
        self.same_state_count = 0
        self.last_progress_time = datetime.now()
        self.recovery_history: List[Dict] = []
        self.current_stuck: Optional[StuckCondition] = None
        
        # Context history for LLM
        self.context_history: List[str] = []
        self.max_context_history = 10
    
    def check_and_recover(self) -> Optional[Dict]:
        """
        Check if stuck and attempt recovery if needed.
        
        Returns:
            Recovery result dict or None if not stuck
        """
        # Check for stuck condition
        stuck = self._detect_stuck()
        
        if not stuck:
            return None
        
        logger.warning(f"🔄 Stuck detected: {stuck.reason}")
        self.current_stuck = stuck
        
        # Attempt recovery
        return self._attempt_recovery(stuck)
    
    def _detect_stuck(self) -> Optional[StuckCondition]:
        """Detect if the agent is stuck."""
        current_batch = self.state.current_batch_idx
        current_action = self.state.current_action_idx
        
        # Check 1: Same state for too many iterations
        if current_batch == self.last_batch_idx and current_action == self.last_action_idx:
            self.same_state_count += 1
            
            if self.same_state_count >= self.max_same_state_iterations:
                return self._create_stuck_condition("No progress for multiple iterations")
        else:
            # Progress made
            self.same_state_count = 0
            self.last_progress_time = datetime.now()
        
        self.last_batch_idx = current_batch
        self.last_action_idx = current_action
        
        # Check 2: Time-based stuck detection
        time_stuck = (datetime.now() - self.last_progress_time).total_seconds()
        if time_stuck > self.stuck_threshold:
            return self._create_stuck_condition(f"No progress for {time_stuck:.1f}s")
        
        # Check 3: Paused status with repeated interventions
        if self.state.status == LoopStatus.PAUSED:
            recent_interventions = [
                i for i in self.state.interventions 
                if datetime.fromisoformat(i['timestamp']) > datetime.now() - timedelta(seconds=30)
            ]
            if len(recent_interventions) >= 3:
                return self._create_stuck_condition("Multiple supervisor interventions")
        
        # Check 4: Detect unexpected modal/dialog
        modal = self._detect_modal_dialog()
        if modal:
            return self._create_stuck_condition(f"Unexpected dialog: {modal}")
        
        return None
    
    def _detect_modal_dialog(self) -> Optional[str]:
        """Detect if there's an unexpected modal/dialog on screen."""
        try:
            app_info = get_frontmost_app()
            window_title = (app_info.get("window", "") or "").lower()
            
            # Common dialog patterns
            dialog_keywords = [
                "do you want to", "are you sure", "confirm", "warning",
                "error", "alert", "terminate", "quit", "save changes",
                "permission", "allow", "deny", "cancel", "ok"
            ]
            
            for keyword in dialog_keywords:
                if keyword in window_title:
                    return window_title
            
            # Check for small windows (likely modals)
            elements = get_ui_elements_applescript(max_elements=20)
            
            # Look for common button patterns in dialogs
            button_texts = set()
            for elem in elements:
                if elem.role == "button":
                    text = (elem.title or "").lower()
                    button_texts.add(text)
            
            # Common dialog button combinations
            if {"ok", "cancel"} <= button_texts or {"yes", "no"} <= button_texts:
                return f"Dialog with buttons: {', '.join(button_texts)}"
            if "terminate" in button_texts or "quit" in button_texts:
                return f"Termination dialog: {', '.join(button_texts)}"
                
        except Exception as e:
            logger.debug(f"Modal detection error: {e}")
        
        return None
    
    def _create_stuck_condition(self, reason: str) -> StuckCondition:
        """Create a stuck condition with current context."""
        # Get current screen context
        try:
            screen_context = format_ui_for_llm(max_elements=30)
        except:
            screen_context = "(Could not capture screen)"
        
        # Get recent actions
        recent = self.state.action_history[-5:]
        last_actions = [f"{a.action} ({'✓' if a.success else '✗'})" for a in recent]
        
        # Capture screenshot for stuck condition
        try:
            screenshot_path = self.state._capture_screenshot("stuck_condition")
            logger.info(f"  📸 Stuck screenshot: {screenshot_path}")
        except Exception as e:
            logger.debug(f"Failed to capture stuck screenshot: {e}")
            screenshot_path = None
        
        return StuckCondition(
            detected_at=datetime.now(),
            reason=reason,
            screen_context=screen_context,
            loop_count=self.same_state_count,
            last_actions=last_actions
        )
    
    def _attempt_recovery(self, stuck: StuckCondition) -> Dict:
        """Attempt to recover from stuck condition."""
        stuck.recovery_attempted += 1
        
        if stuck.recovery_attempted > self.max_recovery_attempts:
            logger.error("❌ Max recovery attempts reached, giving up")
            return {"success": False, "action": "give_up", "reason": "Max attempts exceeded"}
        
        logger.info(f"🔧 Recovery attempt {stuck.recovery_attempted}/{self.max_recovery_attempts}")
        
        # Strategy 1: Try quick fixes first (no LLM needed)
        quick_fix = self._try_quick_fix(stuck)
        if quick_fix:
            return quick_fix
        
        # Strategy 2: Get LLM guidance with full context
        return self._get_llm_recovery(stuck)
    
    def _try_quick_fix(self, stuck: StuckCondition) -> Optional[Dict]:
        """Try quick fixes without LLM call."""
        import pyautogui
        
        # Quick fix 1: Dismiss dialogs with Escape
        if "dialog" in stuck.reason.lower() or "terminate" in stuck.reason.lower():
            logger.info("  Trying Escape to dismiss dialog...")
            pyautogui.press("escape")
            time.sleep(0.3)
            
            # Check if dialog is gone
            if not self._detect_modal_dialog():
                self._record_recovery("escape", "Dismissed dialog with Escape", True)
                return {"success": True, "action": "escape", "reason": "Dialog dismissed"}
        
        # Quick fix 2: Click Cancel button if visible
        if "cancel" in stuck.screen_context.lower():
            try:
                elements = get_ui_elements_applescript(max_elements=30)
                for elem in elements:
                    if elem.role == "button" and "cancel" in (elem.title or "").lower():
                        logger.info(f"  Clicking Cancel button at {elem.center}")
                        pyautogui.click(elem.center[0], elem.center[1])
                        time.sleep(0.3)
                        self._record_recovery("click_cancel", "Clicked Cancel button", True)
                        return {"success": True, "action": "click_cancel", "reason": "Clicked Cancel"}
            except:
                pass
        
        # Quick fix 3: Click through common dialog buttons
        dialog_buttons = ["ok", "done", "close", "continue", "skip"]
        try:
            elements = get_ui_elements_applescript(max_elements=30)
            for button_text in dialog_buttons:
                for elem in elements:
                    if elem.role == "button" and button_text in (elem.title or "").lower():
                        logger.info(f"  Clicking {button_text} button")
                        pyautogui.click(elem.center[0], elem.center[1])
                        time.sleep(0.3)
                        self._record_recovery(f"click_{button_text}", f"Clicked {button_text}", True)
                        return {"success": True, "action": f"click_{button_text}"}
        except:
            pass
        
        return None
    
    def _get_llm_recovery(self, stuck: StuckCondition) -> Dict:
        """Get LLM guidance for recovery with full context."""
        import pyautogui
        
        # Build comprehensive context
        context = self._build_recovery_context(stuck)
        
        # Add to context history
        self._add_to_context_history(f"STUCK: {stuck.reason}")
        
        prompt = f"""{context}

## Recovery Request
The agent is stuck and needs your help to continue.

Based on the screen state and task context, what should the agent do?

RESPOND WITH ONE OF:
1. click:<element_text> - Click on a specific UI element
2. key:<keyname> - Press a key (escape, enter, tab, etc.)
3. hotkey:<key1,key2> - Press a keyboard shortcut
4. type:<text> - Type some text
5. skip - Skip the current action and continue with the next batch
6. retry - Retry the current action
7. abort - Stop execution (only if task is impossible)

IMPORTANT:
- If there's a dialog, dismiss it appropriately
- For "terminate" dialogs, usually click "Cancel" to keep the process running
- For permission dialogs, click "Allow" or "OK"
- Think about what the user would do manually

Your response (one line only):"""

        try:
            response = self.cli.generate(prompt).strip()
            logger.info(f"  LLM recovery suggestion: {response}")
            
            # Parse and execute recovery action
            return self._execute_recovery_action(response, stuck)
            
        except Exception as e:
            logger.error(f"LLM recovery failed: {e}")
            return {"success": False, "action": "llm_error", "reason": str(e)}
    
    def _build_recovery_context(self, stuck: StuckCondition) -> str:
        """Build comprehensive context for LLM recovery."""
        # Get current app info
        try:
            app_info = get_frontmost_app()
            app_context = f"Current App: {app_info.get('app', 'Unknown')} - {app_info.get('window', '')}"
        except:
            app_context = "Current App: Unknown"
        
        # Format action history
        action_history = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(stuck.last_actions))
        
        # Format recovery history if any
        recovery_attempts = ""
        if self.recovery_history:
            recent_recoveries = self.recovery_history[-3:]
            recovery_attempts = "\n## Previous Recovery Attempts:\n" + "\n".join(
                f"  - {r['action']}: {r['result']}" for r in recent_recoveries
            )
        
        # Format context history
        context_log = ""
        if self.context_history:
            context_log = "\n## Context History:\n" + "\n".join(
                f"  {i+1}. {c}" for i, c in enumerate(self.context_history[-5:])
            )
        
        return f"""## Task Context
Task: {self.state.task_description}
Status: {self.state.status.value}
Progress: Batch {self.state.current_batch_idx + 1}/{len(self.state.batches)}, Action {self.state.current_action_idx}

## Why Stuck
Reason: {stuck.reason}
Time stuck: {(datetime.now() - stuck.detected_at).total_seconds():.1f}s
Loop iterations on same state: {stuck.loop_count}

## {app_context}

## Recent Actions:
{action_history}

## Current Screen Elements:
{stuck.screen_context[:2000]}
{recovery_attempts}
{context_log}"""
    
    def _execute_recovery_action(self, response: str, stuck: StuckCondition) -> Dict:
        """Execute the LLM-suggested recovery action."""
        import pyautogui
        
        response = response.strip().lower()
        
        try:
            if response.startswith("click:"):
                element_text = response[6:].strip()
                return self._recovery_click(element_text)
                
            elif response.startswith("key:"):
                key = response[4:].strip()
                pyautogui.press(key)
                time.sleep(0.2)
                self._record_recovery(f"key:{key}", "Pressed key", True)
                return {"success": True, "action": f"key:{key}"}
                
            elif response.startswith("hotkey:"):
                keys = [k.strip() for k in response[7:].split(",")]
                pyautogui.hotkey(*keys)
                time.sleep(0.2)
                self._record_recovery(f"hotkey:{','.join(keys)}", "Pressed hotkey", True)
                return {"success": True, "action": f"hotkey:{','.join(keys)}"}
                
            elif response.startswith("type:"):
                text = response[5:].strip()
                pyautogui.write(text, interval=0.02)
                time.sleep(0.2)
                self._record_recovery(f"type:{text[:20]}", "Typed text", True)
                return {"success": True, "action": f"type:{text[:20]}"}
                
            elif response == "skip":
                self.state.advance_batch()
                self._record_recovery("skip", "Skipped to next batch", True)
                self._add_to_context_history("Skipped problematic batch")
                return {"success": True, "action": "skip", "reason": "Skipped current batch"}
                
            elif response == "retry":
                self.same_state_count = 0
                self.last_progress_time = datetime.now()
                self._record_recovery("retry", "Reset for retry", True)
                return {"success": True, "action": "retry", "reason": "Retrying current action"}
                
            elif response == "abort":
                self.state.status = LoopStatus.FAILED
                self._record_recovery("abort", "Task aborted", False)
                return {"success": False, "action": "abort", "reason": "Task deemed impossible"}
                
            else:
                logger.warning(f"Unknown recovery response: {response}")
                # Default: try Escape
                pyautogui.press("escape")
                return {"success": True, "action": "escape_fallback"}
                
        except Exception as e:
            logger.error(f"Recovery action failed: {e}")
            self._record_recovery(response, f"Failed: {e}", False)
            return {"success": False, "action": response, "reason": str(e)}
    
    def _recovery_click(self, element_text: str) -> Dict:
        """Click on an element by text."""
        import pyautogui
        
        try:
            elements = get_ui_elements_applescript(max_elements=50)
            
            # Find matching element
            for elem in elements:
                elem_title = (elem.title or "").lower()
                elem_value = (elem.value or "").lower()
                
                if element_text.lower() in elem_title or element_text.lower() in elem_value:
                    logger.info(f"  Found element: {elem.role} '{elem.title}' at {elem.center}")
                    pyautogui.click(elem.center[0], elem.center[1])
                    time.sleep(0.3)
                    self._record_recovery(f"click:{element_text}", f"Clicked {elem.role}", True)
                    return {"success": True, "action": f"click:{element_text}"}
            
            logger.warning(f"Element not found: {element_text}")
            self._record_recovery(f"click:{element_text}", "Element not found", False)
            return {"success": False, "action": f"click:{element_text}", "reason": "Element not found"}
            
        except Exception as e:
            return {"success": False, "action": f"click:{element_text}", "reason": str(e)}
    
    def _record_recovery(self, action: str, result: str, success: bool):
        """Record a recovery attempt."""
        self.recovery_history.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "result": result,
            "success": success
        })
    
    def _add_to_context_history(self, context: str):
        """Add to context history for LLM."""
        self.context_history.append(f"[{datetime.now().strftime('%H:%M:%S')}] {context}")
        if len(self.context_history) > self.max_context_history:
            self.context_history = self.context_history[-self.max_context_history:]
    
    def record_action(self, action: str, success: bool):
        """Record an action for context tracking."""
        status = "✓" if success else "✗"
        self._add_to_context_history(f"Action: {action[:50]} [{status}]")
    
    def reset(self):
        """Reset stuck detection state."""
        self.same_state_count = 0
        self.last_progress_time = datetime.now()
        self.current_stuck = None
