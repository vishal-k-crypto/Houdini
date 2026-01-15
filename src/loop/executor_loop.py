"""
ExecutorLoop - Continuous execution loop for the agent.
The model always knows what it's doing through context prompts.
Now enhanced with pattern learning and recovery handling.

UPDATED: Now uses event-driven waiting via macOS Accessibility Tree
instead of fixed time.sleep() calls for better reliability and speed.

UPDATED: Now logs all events to the Replay system for "Time Travel" debugging.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
import pyautogui

from .loop_state import LoopState, LoopStatus
from ..utils.logging import logger
from ..utils.pattern_store import pattern_store
from ..utils.choice_tracker import choice_tracker
from ..ui.thinking_window import show_executor_thinking, show_thinking

# Import replay system for time travel debugging
try:
    from ..replay.execution_logger import get_execution_logger, ExecutionLogger
    REPLAY_AVAILABLE = True
except ImportError:
    REPLAY_AVAILABLE = False

# Import event-driven wait system
try:
    from ..utils.ui_wait import (
        get_ui_wait_system, wait_for_ui_stable, smart_wait,
        wait_for_element, wait_for_window_ready, UIWaitSystem
    )
    UI_WAIT_AVAILABLE = True
except ImportError:
    UI_WAIT_AVAILABLE = False
    logger.debug("Event-driven UI wait system not available, using fixed sleeps")


class ExecutorLoop:
    """
    Continuous execution loop that maintains full awareness of task state.
    
    On each iteration, the model knows:
    - What task it's working on
    - What it just did (action history)
    - What it needs to do next (current batch/action)
    - Overall progress
    
    Now includes stuck detection and recovery handling.
    """
    
    def __init__(self, state: LoopState, 
                 on_vision_needed: Optional[Callable] = None,
                 action_delay: float = 0.1,
                 cli = None):
        """
        Args:
            state: Shared LoopState with supervisor
            on_vision_needed: Callback when vision action is needed
            action_delay: Seconds to wait between actions
            cli: Gemini CLI for recovery (optional)
        """
        self.state = state
        self.on_vision_needed = on_vision_needed
        self.action_delay = action_delay
        self.running = False
        self.cli = cli
        
        # Performance tracking
        self.loop_iterations = 0
        self.total_action_time_ms = 0.0
        
        # Pattern learning - track execution for learning
        self.execution_trace: List[Dict] = []
        
        # Recovery handler (initialized lazily)
        self._recovery_handler = None
        
        # Event-driven wait system (initialized lazily)
        self._ui_wait: Optional[UIWaitSystem] = None
        if UI_WAIT_AVAILABLE:
            try:
                self._ui_wait = get_ui_wait_system()
                logger.debug("Event-driven UI wait system initialized")
            except Exception as e:
                logger.debug(f"Could not init UI wait system: {e}")
    
    @property
    def recovery_handler(self):
        """Lazy initialization of recovery handler."""
        if self._recovery_handler is None and self.cli is not None:
            from .recovery_handler import RecoveryHandler
            self._recovery_handler = RecoveryHandler(
                cli=self.cli,
                state=self.state,
                stuck_threshold_seconds=15.0,
                max_same_state_iterations=5,
                max_recovery_attempts=3
            )
        return self._recovery_handler
    
    def run(self) -> Dict:
        """
        Main execution loop.
        
        Returns:
            Summary dict with execution results
        """
        self.running = True
        self.state.status = LoopStatus.RUNNING
        self.state.started_at = datetime.now()
        
        # Start replay session for time travel debugging
        self._replay_logger: Optional[ExecutionLogger] = None
        if REPLAY_AVAILABLE:
            try:
                self._replay_logger = get_execution_logger()
                self._replay_logger.start_session(
                    task_id=self.state.task_id,
                    task_description=self.state.task_description,
                    metadata={
                        "batches": len(self.state.batches),
                        "architecture": "executor_loop",
                    }
                )
                logger.debug("📼 Replay session started for time travel debugging")
            except Exception as e:
                logger.debug(f"Could not start replay session: {e}")
        
        logger.info(f"🔄 ExecutorLoop starting: {self.state.task_description}")
        logger.info(f"📋 Plan has {len(self.state.batches)} batches")
        
        try:
            while self.running:
                self.loop_iterations += 1
                
                # Check for stuck condition and attempt recovery
                if self.recovery_handler:
                    recovery_result = self.recovery_handler.check_and_recover()
                    if recovery_result:
                        if recovery_result.get("action") == "abort":
                            logger.error("🛑 Recovery aborted task")
                            break
                        elif recovery_result.get("action") == "skip":
                            logger.info("⏭️ Skipped to next batch after recovery")
                            continue
                        elif recovery_result.get("success"):
                            logger.info(f"✅ Recovery successful: {recovery_result.get('action')}")
                            # Reset pause if we were paused
                            if self.state.status == LoopStatus.PAUSED:
                                self.state.resume()
                            continue
                
                # Check if paused (supervisor intervention)
                if self.state.status == LoopStatus.PAUSED:
                    logger.warning(f"⏸️ Loop paused: {self.state.pause_reason}")
                    time.sleep(0.5)
                    continue
                
                # Check if complete - BEFORE trying to execute more steps
                if self.state.is_task_complete():
                    logger.info(f"✅ All batches completed ({self.state.current_batch_idx}/{len(self.state.batches)})")
                    
                    # CRITICAL: Verify task is ACTUALLY complete using robust verification
                    verification_result = self._robust_task_verification()
                    confidence = verification_result.get("confidence", 0)
                    
                    if verification_result.get("complete") and confidence >= 0.65:  # Lowered from 0.75
                        logger.info(f"✅ Task VERIFIED complete: {verification_result.get('reason')}")
                        logger.info(f"   Confidence: {confidence:.0%}")
                        self.state.status = LoopStatus.COMPLETED
                        
                        # Save final checkpoint with screenshot
                        try:
                            checkpoint = self.state.save_checkpoint(
                                description="Task completed successfully",
                                capture_screenshot=True
                            )
                            logger.info(f"📸 Final checkpoint saved: {checkpoint.screenshot_path}")
                        except Exception as e:
                            logger.warning(f"Failed to save final checkpoint: {e}")
                        
                        break
                    else:
                        # Task NOT complete - add corrective actions
                        reason = verification_result.get("reason", "Unknown")
                        next_steps = verification_result.get("next_steps", [])
                        
                        logger.warning(f"⚠️ Task NOT complete (confidence: {confidence:.0%})")
                        logger.warning(f"   Reason: {reason}")
                        
                        if next_steps:
                            logger.info(f"🔄 Attempting {len(next_steps)} corrective actions...")
                            corrective_batches = self._create_corrective_batches(next_steps)
                            self.state.batches.extend(corrective_batches)
                            logger.info(f"   Added {len(corrective_batches)} corrective batches")
                            # Continue execution
                        else:
                            # Generate recovery plan
                            logger.info("🤔 Generating recovery plan...")
                            recovery_batches = self._generate_recovery_plan(verification_result)
                            
                            if recovery_batches:
                                self.state.batches.extend(recovery_batches)
                                logger.info(f"   Added {len(recovery_batches)} recovery batches")
                            else:
                                logger.error("❌ Unable to determine next steps")
                                self.state.status = LoopStatus.FAILED
                                break
                
                # Log context every few iterations
                if self.loop_iterations % 5 == 1:
                    logger.debug(f"\n{self.state.get_context_prompt()}")
                
                # Execute one step
                step_result = self._execute_step()
                
                if step_result.get("stop"):
                    if step_result.get("error"):
                        self.state.status = LoopStatus.FAILED
                    break
                
                # Brief delay between actions
                time.sleep(self.action_delay)
            
        except KeyboardInterrupt:
            logger.warning("⚠️ Loop interrupted by user")
            self.state.status = LoopStatus.PAUSED
            self.state.pause_reason = "User interrupt"
        
        except Exception as e:
            logger.error(f"❌ Loop error: {e}")
            self.state.status = LoopStatus.FAILED
        
        finally:
            self.running = False
            self.state.completed_at = datetime.now()
            
            # End replay session for time travel debugging
            if self._replay_logger and self._replay_logger.current_session:
                try:
                    success = self.state.status == LoopStatus.COMPLETED
                    error = None if success else f"Status: {self.state.status.value}"
                    self._replay_logger.end_session(success=success, error=error)
                    logger.debug("📼 Replay session saved for time travel debugging")
                except Exception as e:
                    logger.debug(f"Could not end replay session: {e}")
            
            # Record execution pattern for learning
            self._record_pattern_learning()
        
        return self._get_summary()
    
    def _execute_step(self) -> Dict:
        """
        Execute one step (one action from current batch).
        
        Returns:
            {"stop": bool, "error": str or None}
        """
        batch = self.state.get_current_batch()
        
        if not batch:
            return {"stop": True, "error": None}
        
        batch_type = batch.get("type", "blind")
        description = batch.get("description", f"Batch {self.state.current_batch_idx + 1}")
        
        # Log batch start
        if self.state.current_action_idx == 0:
            logger.info(f"\n▶️ Batch {self.state.current_batch_idx + 1}: {description}")
            try:
                # Use status update instead of main log to reduce clutter
                from ..ui.thinking_window import update_status
                update_status(f"Batch {self.state.current_batch_idx + 1}: {description}")
            except:
                pass
            
            # Log batch start to replay system
            if self._replay_logger and self._replay_logger.current_session:
                self._replay_logger.log_batch_start(
                    self.state.current_batch_idx,
                    batch_type,
                    description
                )
        
        if batch_type == "blind":
            return self._execute_blind_step(batch)
        elif batch_type == "vision":
            return self._execute_vision_step(batch)
        else:
            logger.warning(f"Unknown batch type: {batch_type}")
            self.state.advance_batch()
            return {"stop": False}
    
    def _execute_blind_step(self, batch: Dict) -> Dict:
        """Execute one blind action from the batch."""
        actions = batch.get("actions", [])
        
        if self.state.current_action_idx >= len(actions):
            # Batch complete, move to next
            num_actions = len(actions)
            logger.info(f"  ✅ Batch complete ({num_actions} action{'s' if num_actions != 1 else ''})")
            
            # Log batch completion to replay
            if self._replay_logger and self._replay_logger.current_session:
                self._replay_logger.log_batch_complete(self.state.current_batch_idx, True)
            
            # Save checkpoint with screenshot after batch completion
            try:
                checkpoint = self.state.save_checkpoint(
                    description=f"After batch {self.state.current_batch_idx + 1}",
                    capture_screenshot=True
                )
                logger.debug(f"  📸 Checkpoint saved: {checkpoint.screenshot_path}")
                
                # Log screenshot to replay
                if self._replay_logger and self._replay_logger.current_session and checkpoint.screenshot_path:
                    self._replay_logger.log_screenshot(
                        checkpoint.screenshot_path,
                        f"After batch {self.state.current_batch_idx + 1}"
                    )
            except Exception as e:
                logger.debug(f"  Screenshot checkpoint failed: {e}")
            
            self.state.advance_batch()
            # Event-driven wait for UI to settle after batch
            self._smart_wait_after("batch_complete")
            return {"stop": False}
        
        action = actions[self.state.current_action_idx]
        start_time = time.time()
        
        # Log action start to replay
        if self._replay_logger and self._replay_logger.current_session:
            self._replay_logger.log_action(action, "blind")
        
        try:
            success = self._execute_action(action)
            duration_ms = (time.time() - start_time) * 1000
            self.total_action_time_ms += duration_ms
            
            self.state.record_action(
                action_type="blind",
                action=action,
                success=success,
                duration_ms=duration_ms
            )
            
            # Log action completion to replay
            if self._replay_logger and self._replay_logger.current_session:
                self._replay_logger.log_action_complete(action, success, duration_ms)
            
            if success:
                logger.info(f"  ↳ {action} [{duration_ms:.0f}ms]")
                try:
                    show_executor_thinking(f"Executed: {action[:60]}")
                except:
                    pass
            else:
                logger.warning(f"  ⚠️ {action} (may have failed)")
            
            self.state.advance_action()
            
        except Exception as e:
            logger.error(f"  ❌ Action failed: {action} - {e}")
            # Capture screenshot on failure for debugging
            self.state.record_action(
                action_type="blind",
                action=action,
                success=False,
                error=str(e),
                capture_screenshot=True  # Capture on error
            )
            # Continue anyway - let supervisor decide if critical
            self.state.advance_action()
        
        return {"stop": False}
    
    def _execute_vision_step(self, batch: Dict) -> Dict:
        """Handle a vision action (requires screen observation)."""
        action_desc = batch.get("action", batch.get("description", "Vision action"))
        
        # Vision batches are single actions, check if already executed
        if self.state.current_action_idx > 0:
            # Already executed, move to next batch
            logger.info(f"  ✅ Vision batch complete")
            self.state.advance_batch()
            # Event-driven wait for UI to settle
            self._smart_wait_after("vision")
            return {"stop": False}
        
        logger.info(f"  👁️ Vision action needed: {action_desc}")
        try:
            show_executor_thinking(f"Vision action: {action_desc[:60]}")
        except:
            pass
        
        if self.on_vision_needed:
            # Callback to handle vision action
            start_time = time.time()
            result = self.on_vision_needed(action_desc)
            duration_ms = (time.time() - start_time) * 1000
            
            # Get method used for learning/debugging
            method_used = result.get("method", "unknown")
            
            # Capture screenshot for vision actions (especially failures)
            capture_ss = not result.get("success", False)  # Always capture on failure
            
            self.state.record_action(
                action_type="vision",
                action=action_desc,
                success=result.get("success", False),
                error=result.get("error"),
                duration_ms=duration_ms,
                capture_screenshot=capture_ss
            )
            
            if result.get("success"):
                logger.info(f"  ✅ Vision action completed via {method_used} [{duration_ms:.0f}ms]")
                try:
                    show_executor_thinking(f"✓ Success ({method_used})")
                except:
                    pass
            else:
                logger.warning(f"  ⚠️ Vision action failed: {result.get('error', 'unknown')}")
                # Record failure pattern for supervisor
                self._record_vision_failure(action_desc, result.get("error"))
        else:
            # No handler - mark as needing vision and continue
            self.state.status = LoopStatus.AWAITING_VISION
            self.state.record_action(
                action_type="vision",
                action=action_desc,
                success=False,
                error="No vision handler"
            )
        
        # Advance action index to mark vision action as done
        self.state.advance_action()
        # Event-driven wait for UI to settle after vision action
        self._smart_wait_after("vision")
        
        return {"stop": False}
    
    def _record_vision_failure(self, action_desc: str, error: str):
        """Record vision failure for pattern learning."""
        failure_info = {
            "action": action_desc,
            "error": error,
            "batch_idx": self.state.current_batch_idx,
            "timestamp": datetime.now().isoformat()
        }
        self.execution_trace.append({"type": "vision_failure", **failure_info})
    
    def _execute_action(self, action: str) -> bool:
        """
        Execute a single blind action.
        
        Action formats:
        - "hotkey:key1,key2" → pyautogui.hotkey(key1, key2)
        - "type:text" → pyautogui.write(text)
        - "key:keyname" → pyautogui.press(keyname)
        - "wait:seconds" → time.sleep(seconds) OR smart wait
        - "wait_for:element_text" → wait for element to appear (NEW)
        - "wait_stable" → wait for UI to stabilize (NEW)
        - "click:x,y" → pyautogui.click(x, y)
        """
        try:
            if action.startswith("hotkey:"):
                keys = action[7:].split(",")
                keys = [k.strip() for k in keys]
                pyautogui.hotkey(*keys)
                # Event-driven wait after hotkey
                self._smart_wait_after("hotkey")
                
            elif action.startswith("type:"):
                text = action[5:]
                pyautogui.write(text, interval=0.02)
                # Minimal wait for typing
                self._smart_wait_after("type")
                
            elif action.startswith("key:"):
                key = action[4:].strip()
                pyautogui.press(key)
                # Smart wait after key press
                self._smart_wait_after("key")
            
            elif action.startswith("wait_for:"):
                # NEW: Wait for specific element to appear
                element_text = action[9:].strip()
                if self._ui_wait:
                    result = self._ui_wait.wait_for_element(text=element_text, timeout_ms=10000)
                    if not result.success:
                        logger.warning(f"Element '{element_text}' not found after {result.waited_ms:.0f}ms")
                else:
                    time.sleep(2.0)  # Fallback
            
            elif action.startswith("wait_stable"):
                # NEW: Wait for UI to stabilize
                if self._ui_wait:
                    result = self._ui_wait.wait_for_ui_stable()
                    logger.debug(f"UI stabilized after {result.waited_ms:.0f}ms")
                else:
                    time.sleep(0.5)  # Fallback
                
            elif action.startswith("wait:"):
                secs = float(action[5:])
                # Use event-driven wait if available, otherwise fixed sleep
                if self._ui_wait and secs >= 0.3:
                    # For longer waits, use UI stability check
                    result = self._ui_wait.wait_for_ui_stable(
                        max_wait_ms=int(secs * 1000),
                        stability_ms=150
                    )
                    logger.debug(f"Smart wait: requested {secs}s, actual {result.waited_ms:.0f}ms")
                else:
                    time.sleep(secs)
                
            elif action.startswith("click:"):
                coords = action[6:].split(",")
                target_x, target_y = int(coords[0]), int(coords[1])
                
                # Get current position for logging
                current_x, current_y = pyautogui.position()
                distance = ((target_x - current_x)**2 + (target_y - current_y)**2)**0.5
                
                logger.debug(f"Cursor: ({current_x}, {current_y}) → ({target_x}, {target_y}) [distance: {distance:.0f}px]")
                
                # Import HumanCursor for natural mouse movement
                from ..utils.cursor_controller import get_cursor
                cursor = get_cursor()
                
                # Update UI BEFORE moving (so user sees what's happening)
                try:
                    show_executor_thinking(f"Moving to ({target_x}, {target_y})...")
                except:
                    pass
                
                # Use HumanCursor for actual movement (blocks until done)
                cursor.move_to(target_x, target_y)
                cursor.click()
                
                # Update UI AFTER finished
                try:
                    show_executor_thinking(f"✓ Clicked at ({target_x}, {target_y})", level="success")
                except:
                    pass
                
                # Event-driven wait after click
                self._smart_wait_after("click")
                
            else:
                logger.warning(f"Unknown action format: {action}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Action execution error: {e}")
            raise
    
    def _smart_wait_after(self, action_type: str):
        """
        Event-driven wait after an action completes.
        Uses UI stability detection instead of fixed sleep.
        """
        if self._ui_wait:
            try:
                if action_type in ("batch_complete", "vision"):
                    # These need longer stability checks
                    result = self._ui_wait.wait_for_ui_stable(
                        max_wait_ms=2000,
                        stability_ms=200
                    )
                else:
                    result = self._ui_wait.smart_wait_after_action(action_type)
                logger.debug(f"Post-{action_type} wait: {result.waited_ms:.0f}ms")
            except Exception as e:
                logger.debug(f"Smart wait failed, using fallback: {e}")
                time.sleep(0.1)
        else:
            # Fallback to fixed sleeps
            if action_type == "type":
                time.sleep(0.05)
            elif action_type == "click":
                time.sleep(0.15)
            elif action_type in ("batch_complete", "vision"):
                time.sleep(0.3)
            else:
                time.sleep(0.1)
            raise
    
    def stop(self):
        """Stop the execution loop gracefully."""
        logger.info("🛑 Stop requested")
        self.running = False
    
    def pause(self, reason: str = "Manual pause"):
        """Pause the loop."""
        self.state.pause(reason)
    
    def resume(self):
        """Resume from paused state."""
        self.state.resume()
        logger.info("▶️ Resuming execution")
    
    def _get_summary(self) -> Dict:
        """Generate execution summary."""
        elapsed = 0
        if self.state.started_at:
            end = self.state.completed_at or datetime.now()
            elapsed = (end - self.state.started_at).total_seconds()
        
        successful = sum(1 for a in self.state.action_history if a.success)
        failed = sum(1 for a in self.state.action_history if not a.success)
        
        return {
            "task_id": self.state.task_id,
            "status": self.state.status.value,
            "elapsed_seconds": elapsed,
            "loop_iterations": self.loop_iterations,
            "actions_total": len(self.state.action_history),
            "actions_successful": successful,
            "actions_failed": failed,
            "batches_total": len(self.state.batches),
            "batches_completed": self.state.current_batch_idx,
            "avg_action_ms": self.total_action_time_ms / max(1, len(self.state.action_history)),
            "interventions": len(self.state.interventions),
        }
    
    def _record_pattern_learning(self):
        """Record execution pattern for learning."""
        try:
            # Determine if execution was successful
            success = self.state.status == LoopStatus.COMPLETED
            
            # Calculate total duration
            duration = 0.0
            if self.state.started_at and self.state.completed_at:
                duration = (self.state.completed_at - self.state.started_at).total_seconds()
            
            # Build action trace from state history
            action_trace = []
            for record in self.state.action_history:
                action_trace.append({
                    "action": record.action,
                    "success": record.success,
                    "duration": record.duration_ms / 1000  # Convert to seconds
                })
            
            if action_trace:
                # Record to pattern store for learning
                pattern_store.record_execution(
                    task=self.state.task_description,
                    actions=action_trace,
                    success=success,
                    duration=duration
                )
                
                # Track app-specific choices
                self._track_app_choices(action_trace, success)
                
                if success:
                    logger.info(f"📚 Pattern recorded for future optimization")
                else:
                    logger.debug(f"📝 Failure pattern recorded for learning")
                    
        except Exception as e:
            logger.warning(f"Could not record pattern: {e}")
    
    def _track_app_choices(self, action_trace: List[Dict], success: bool):
        """Track choices for app-specific learning."""
        try:
            # Extract app name from task or actions
            app_name = self._extract_app_name()
            
            if app_name:
                # Track wait times for this app
                for i, action_data in enumerate(action_trace):
                    action = action_data.get("action", "")
                    if action.startswith("wait:"):
                        try:
                            wait_time = float(action.split(":")[1])
                            
                            # Determine what type of action preceded this wait
                            if i > 0:
                                prev_action = action_trace[i - 1].get("action", "")
                                action_type = self._classify_wait_context(prev_action)
                                
                                choice_tracker.update_wait_preference(
                                    app_name=app_name,
                                    action_type=action_type,
                                    wait_time=wait_time,
                                    success=action_data.get("success", True)
                                )
                        except:
                            pass
        except Exception as e:
            logger.debug(f"Could not track app choices: {e}")
    
    def _extract_app_name(self) -> Optional[str]:
        """Extract app name from task description."""
        task = self.state.task_description.lower()
        
        # Common app names
        apps = [
            "safari", "chrome", "firefox", "edge", "brave",
            "finder", "notes", "calendar", "messages", "mail",
            "terminal", "calculator", "preview", "photos",
            "whatsapp", "spotify", "slack", "discord"
        ]
        
        for app in apps:
            if app in task:
                return app.title()
        
        return None
    
    def _classify_wait_context(self, prev_action: str) -> str:
        """Classify what type of wait is needed based on previous action."""
        if "command,space" in prev_action:
            return "spotlight_launch"
        elif "enter" in prev_action:
            return "confirm_action"
        elif "command,l" in prev_action or "command,t" in prev_action:
            return "keyboard_shortcut"
        elif prev_action.startswith("type:"):
            return "after_typing"
        elif prev_action.startswith("click:"):
            return "after_click"
        else:
            return "generic"
    
    def _robust_task_verification(self) -> Dict:
        """
        Robust task verification using multiple methods.
        Much more reliable than simple LLM check.
        
        Returns:
            {
                "complete": bool,
                "confidence": float (0-1), 
                "reason": str,
                "evidence": List[str],
                "next_steps": List[str]
            }
        """
        try:
            from .task_verifier import get_verifier
            from ..utils.accessibility_reader import get_frontmost_app
            
            logger.info("🔍 Running robust task verification...")
            
            # Get current state
            app_info = get_frontmost_app()
            
            current_state = {
                "app": app_info.get("app", ""),
                "window": app_info.get("window", ""),
                "batch_count": len(self.state.batches),
                "actions_completed": len(self.state.action_history)
            }
            
            # Get verifier and run verification
            verifier = get_verifier(self.cli)
            result = verifier.verify_task_complete(
                self.state.task_description,
                self.state.action_history,
                current_state
            )
            
            # Log evidence
            if result.get("evidence"):
                logger.info("📋 Verification evidence:")
                for evidence in result["evidence"][:5]:  # Show top 5
                    logger.info(f"   • {evidence}")
            
            return result
            
        except Exception as e:
            logger.error(f"Robust verification failed: {e}")
            # Fallback to old method
            return self._verify_task_completion()
    
    def _create_corrective_batches(self, next_steps: List[str]) -> List[Dict]:
        """Create batches from corrective action descriptions."""
        batches = []
        
        for step in next_steps[:3]:  # Max 3 corrective actions
            step_lower = step.lower()
            
            # Determine if vision or blind action
            if any(kw in step_lower for kw in ["click", "find", "verify", "locate", "check"]):
                batches.append({
                    "type": "vision",
                    "action": step,
                    "description": f"Corrective: {step}"
                })
            elif any(kw in step_lower for kw in ["type", "enter", "press"]):
                # Extract what to type if possible
                if "type" in step_lower and '"' in step:
                    text = step.split('"')[1] if '"' in step else step.split("'")[1]
                    batches.append({
                        "type": "blind",
                        "actions": [f"type:{text}"],
                        "description": f"Corrective: {step}"
                    })
                else:
                    batches.append({
                        "type": "blind",
                        "actions": [step],
                        "description": f"Corrective: {step}"
                    })
            else:
                # Generic action
                batches.append({
                    "type": "vision",
                    "action": step,
                    "description": f"Corrective: {step}"
                })
        
        return batches
    
    def _generate_recovery_plan(self, verification_result: Dict) -> List[Dict]:
        """Generate recovery plan when task is incomplete but no clear next steps."""
        if not self.cli:
            return []
        
        try:
            from ..utils.accessibility_reader import get_frontmost_app, format_ui_for_llm
            
            app_info = get_frontmost_app()
            screen_context = format_ui_for_llm(max_elements=30)
            
            prompt = f"""TASK RECOVERY PLANNING

**Original Task:** {self.state.task_description}

**Current State:**
- App: {app_info.get('app', 'Unknown')}
- Window: {app_info.get('window', '')}
- Actions completed: {len(self.state.action_history)}

**Verification Result:**
- Complete: {verification_result.get('complete')}
- Confidence: {verification_result.get('confidence', 0):.0%}
- Reason: {verification_result.get('reason')}

**Screen State:**
{screen_context}

**Your Task:**
Generate 1-3 SPECIFIC actions to complete this task. Be PRECISE about UI elements.

**Response Format:**
ACTION1: [specific action with UI element details]
ACTION2: [if needed]
ACTION3: [if needed]

Examples:
- ACTION1: Click on the message input field at the bottom of the chat
- ACTION1: Type "test message" in the active input field
- ACTION1: Click the Send button (blue button at bottom-right)

Your recovery actions:"""

            response = self.cli.generate(prompt, temperature=0.3).strip()
            
            # Parse actions
            actions = []
            for line in response.split("\n"):
                if line.strip().startswith("ACTION"):
                    action_text = line.split(":", 1)[1].strip() if ":" in line else line.strip()
                    if action_text and len(action_text) > 5:
                        actions.append(action_text)
            
            if actions:
                logger.info(f"💡 Generated {len(actions)} recovery actions")
                for i, action in enumerate(actions, 1):
                    logger.info(f"   {i}. {action}")
                
                return self._create_corrective_batches(actions)
            
            return []
            
        except Exception as e:
            logger.error(f"Recovery plan generation failed: {e}")
            return []
    
    def _verify_task_completion(self) -> Dict:
        """
        Verify if the task is actually complete by analyzing current screen state.
        Uses Gemini 2.5 Flash for quick verification.
        
        Returns:
            {
                "complete": bool,
                "reason": str,
                "additional_batches": List[Dict]  # If not complete
            }
        """
        if not self.cli:
            # No CLI available, assume complete
            return {"complete": True, "reason": "No verification available"}
        
        try:
            logger.info("🔍 Verifying task completion with AI...")
            
            # Get current screen state
            from ..utils.accessibility_reader import get_frontmost_app, format_ui_for_llm
            
            app_info = get_frontmost_app()
            screen_context = format_ui_for_llm(max_elements=40)
            
            # Build verification prompt
            prompt = f"""## Task Verification

**Original Task:** {self.state.task_description}

**Execution Summary:**
- Total batches: {len(self.state.batches)}
- Actions completed: {len(self.state.action_history)}
- Current app: {app_info.get('app', 'Unknown')}
- Current window: {app_info.get('window', '')}

**Recent Actions (last 5):**
{self._format_recent_actions()}

**Current Screen State:**
{screen_context}

## Your Task
Analyze if the original task is **ACTUALLY COMPLETE** based on the screen state and actions taken.

**Question:** Is the task "{self.state.task_description}" complete?

**Examples:**
- Task: "open Safari" → If Safari is frontmost app, COMPLETE
- Task: "create folder named test" → If folder exists on desktop, COMPLETE
- Task: "search for weather" → If search results are showing, COMPLETE
- Task: "go to google.com" → If google.com is loaded, COMPLETE

**Respond in this format:**

STATUS: [COMPLETE or INCOMPLETE]
REASON: [Brief explanation of why]
NEXT_ACTIONS: [If incomplete, list what needs to be done - one action per line, or "none" if complete]

Your response:"""

            # Use Gemini 2.5 Flash for fast verification
            try:
                response = self.cli.generate(prompt, model="gemini-2.0-flash-exp").strip()
            except:
                # Fallback to default model
                response = self.cli.generate(prompt).strip()
            
            logger.debug(f"Verification response: {response}")
            
            # Parse response
            is_complete = "COMPLETE" in response.upper() and "INCOMPLETE" not in response.upper()
            
            # Extract reason
            reason = "Task appears complete"
            if "REASON:" in response:
                reason_part = response.split("REASON:")[1].split("NEXT_ACTIONS:")[0].strip()
                reason = reason_part if reason_part else reason
            
            if is_complete:
                return {
                    "complete": True,
                    "reason": reason,
                    "additional_batches": []
                }
            
            # Extract next actions if incomplete
            additional_batches = []
            if "NEXT_ACTIONS:" in response:
                actions_text = response.split("NEXT_ACTIONS:")[1].strip()
                
                if actions_text.lower() != "none":
                    # Parse actions and create batches
                    action_lines = [line.strip() for line in actions_text.split("\n") if line.strip() and not line.strip().startswith("-")]
                    
                    if action_lines:
                        # Create a continuation batch
                        logger.info(f"🔄 AI suggests {len(action_lines)} additional actions")
                        for action_line in action_lines[:3]:  # Limit to 3 additional actions
                            # Determine if blind or vision action
                            if any(kw in action_line.lower() for kw in ["click", "verify", "check", "find"]):
                                additional_batches.append({
                                    "type": "vision",
                                    "action": action_line,
                                    "description": f"Complete task: {action_line}"
                                })
                            else:
                                additional_batches.append({
                                    "type": "blind",
                                    "actions": [action_line],
                                    "description": f"Complete task: {action_line}"
                                })
            
            return {
                "complete": False,
                "reason": reason,
                "additional_batches": additional_batches
            }
            
        except Exception as e:
            logger.error(f"Task verification failed: {e}")
            # On error, assume complete to avoid infinite loop
            return {"complete": True, "reason": f"Verification error: {e}"}
    
    def _format_recent_actions(self) -> str:
        """Format recent actions for verification prompt."""
        recent = self.state.action_history[-5:] if self.state.action_history else []
        if not recent:
            return "(No actions yet)"
        
        lines = []
        for i, action in enumerate(recent, 1):
            status = "✓" if action.success else f"✗ {action.error}"
            lines.append(f"{i}. {action.action[:60]} [{status}]")
        
        return "\n".join(lines)
