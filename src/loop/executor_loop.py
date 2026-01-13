"""
ExecutorLoop - Continuous execution loop for the agent.
The model always knows what it's doing through context prompts.
"""

import time
from datetime import datetime
from typing import Dict, Optional, Callable
import pyautogui

from .loop_state import LoopState, LoopStatus
from ..utils.logging import logger


class ExecutorLoop:
    """
    Continuous execution loop that maintains full awareness of task state.
    
    On each iteration, the model knows:
    - What task it's working on
    - What it just did (action history)
    - What it needs to do next (current batch/action)
    - Overall progress
    
    This enables fast decision-making because context is always available.
    """
    
    def __init__(self, state: LoopState, 
                 on_vision_needed: Optional[Callable] = None,
                 action_delay: float = 0.1):
        """
        Args:
            state: Shared LoopState with supervisor
            on_vision_needed: Callback when vision action is needed
            action_delay: Seconds to wait between actions
        """
        self.state = state
        self.on_vision_needed = on_vision_needed
        self.action_delay = action_delay
        self.running = False
        
        # Performance tracking
        self.loop_iterations = 0
        self.total_action_time_ms = 0.0
    
    def run(self) -> Dict:
        """
        Main execution loop.
        
        Returns:
            Summary dict with execution results
        """
        self.running = True
        self.state.status = LoopStatus.RUNNING
        self.state.started_at = datetime.now()
        
        logger.info(f"🔄 ExecutorLoop starting: {self.state.task_description}")
        logger.info(f"📋 Plan has {len(self.state.batches)} batches")
        
        try:
            while self.running:
                self.loop_iterations += 1
                
                # Check if paused (supervisor intervention)
                if self.state.status == LoopStatus.PAUSED:
                    logger.warning(f"⏸️ Loop paused: {self.state.pause_reason}")
                    time.sleep(0.5)
                    continue
                
                # Check if complete
                if self.state.is_task_complete():
                    self.state.status = LoopStatus.COMPLETED
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
            logger.info(f"  ✅ Batch complete ({len(actions)} actions)")
            self.state.advance_batch()
            time.sleep(0.3)  # UI settle time
            return {"stop": False}
        
        action = actions[self.state.current_action_idx]
        start_time = time.time()
        
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
            
            if success:
                logger.info(f"  ↳ {action} [{duration_ms:.0f}ms]")
            else:
                logger.warning(f"  ⚠️ {action} (may have failed)")
            
            self.state.advance_action()
            
        except Exception as e:
            logger.error(f"  ❌ Action failed: {action} - {e}")
            self.state.record_action(
                action_type="blind",
                action=action,
                success=False,
                error=str(e)
            )
            # Continue anyway - let supervisor decide if critical
            self.state.advance_action()
        
        return {"stop": False}
    
    def _execute_vision_step(self, batch: Dict) -> Dict:
        """Handle a vision action (requires screen observation)."""
        action_desc = batch.get("action", batch.get("description", "Vision action"))
        
        logger.info(f"  👁️ Vision action needed: {action_desc}")
        
        if self.on_vision_needed:
            # Callback to handle vision action
            start_time = time.time()
            result = self.on_vision_needed(action_desc)
            duration_ms = (time.time() - start_time) * 1000
            
            self.state.record_action(
                action_type="vision",
                action=action_desc,
                success=result.get("success", False),
                error=result.get("error"),
                duration_ms=duration_ms
            )
            
            if result.get("success"):
                logger.info(f"  ✅ Vision action completed [{duration_ms:.0f}ms]")
            else:
                logger.warning(f"  ⚠️ Vision action failed: {result.get('error', 'unknown')}")
        else:
            # No handler - mark as needing vision and continue
            self.state.status = LoopStatus.AWAITING_VISION
            self.state.record_action(
                action_type="vision",
                action=action_desc,
                success=False,
                error="No vision handler"
            )
        
        self.state.advance_action()
        self.state.advance_batch()
        time.sleep(0.5)  # Extra time after vision actions
        
        return {"stop": False}
    
    def _execute_action(self, action: str) -> bool:
        """
        Execute a single blind action.
        
        Action formats:
        - "hotkey:key1,key2" → pyautogui.hotkey(key1, key2)
        - "type:text" → pyautogui.write(text)
        - "key:keyname" → pyautogui.press(keyname)
        - "wait:seconds" → time.sleep(seconds)
        - "click:x,y" → pyautogui.click(x, y)
        """
        try:
            if action.startswith("hotkey:"):
                keys = action[7:].split(",")
                keys = [k.strip() for k in keys]
                pyautogui.hotkey(*keys)
                
            elif action.startswith("type:"):
                text = action[5:]
                pyautogui.write(text, interval=0.02)
                
            elif action.startswith("key:"):
                key = action[4:].strip()
                pyautogui.press(key)
                
            elif action.startswith("wait:"):
                secs = float(action[5:])
                time.sleep(secs)
                
            elif action.startswith("click:"):
                coords = action[6:].split(",")
                x, y = int(coords[0]), int(coords[1])
                pyautogui.click(x, y)
                
            else:
                logger.warning(f"Unknown action format: {action}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Action execution error: {e}")
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
