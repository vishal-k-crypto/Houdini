"""
SupervisorLoop - Monitors execution and validates actions.
Runs in parallel with ExecutorLoop (or checkpoint-based).
"""

import time
import threading
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field

from .loop_state import LoopState, LoopStatus, ActionRecord
from ..utils.logging import logger


@dataclass
class ValidationResult:
    """Result of validating an action."""
    approved: bool
    confidence: float = 1.0
    reason: str = ""
    correction: Optional[str] = None


@dataclass
class Intervention:
    """Record of a supervisor intervention."""
    timestamp: datetime
    action_idx: int
    batch_idx: int
    reason: str
    correction: Optional[str]
    resolved: bool = False


class SupervisorLoop:
    """
    Lightweight monitoring loop that validates executor actions.
    
    Design principles:
    - Minimal latency impact on executor
    - Only intervenes when necessary
    - Tracks patterns in errors
    
    The supervisor always knows:
    - Expected vs actual state
    - Error patterns from history
    - When to pause/intervene
    """
    
    def __init__(self, state: LoopState, 
                 validator_model=None,
                 check_interval: float = 0.5,
                 confidence_threshold: float = 0.7):
        """
        Args:
            state: Shared LoopState with executor
            validator_model: Optional LLM for validation (Qwen etc)
            check_interval: Seconds between validation checks
            confidence_threshold: Below this, intervene
        """
        self.state = state
        self.validator = validator_model
        self.check_interval = check_interval
        self.confidence_threshold = confidence_threshold
        
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Tracking
        self.last_checked_action_count = 0
        self.interventions: List[Intervention] = []
        self.error_patterns: Dict[str, int] = {}
    
    def start_background(self):
        """Start supervisor in background thread."""
        if self.thread and self.thread.is_alive():
            logger.warning("SupervisorLoop already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("🔍 SupervisorLoop started in background")
    
    def stop(self):
        """Stop the supervisor loop."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("🔍 SupervisorLoop stopped")
    
    def _run_loop(self):
        """Main monitoring loop - runs at lower frequency than executor."""
        while self.running:
            try:
                # Check if executor is active
                if self.state.status not in [LoopStatus.RUNNING, LoopStatus.AWAITING_VISION]:
                    time.sleep(self.check_interval)
                    continue
                
                # Check for new actions
                current_action_count = len(self.state.action_history)
                
                if current_action_count > self.last_checked_action_count:
                    # New actions to validate
                    new_actions = self.state.action_history[self.last_checked_action_count:]
                    
                    for action in new_actions:
                        validation = self._validate_action(action)
                        
                        if not validation.approved:
                            self._intervene(action, validation)
                    
                    self.last_checked_action_count = current_action_count
                
                # Check for error patterns
                self._check_error_patterns()
                
            except Exception as e:
                logger.error(f"Supervisor error: {e}")
            
            time.sleep(self.check_interval)
    
    def _validate_action(self, action: ActionRecord) -> ValidationResult:
        """
        Validate a single action.
        
        Validation strategies:
        1. Check if action succeeded
        2. Check if action makes sense for task
        3. Use LLM validator if available
        """
        # Quick check: did the action fail?
        if not action.success:
            return ValidationResult(
                approved=False,
                confidence=1.0,
                reason=f"Action failed: {action.error}",
                correction="Retry or skip"
            )
        
        # Pattern check: repeated failures on similar actions?
        action_key = action.action.split(":")[0] if ":" in action.action else action.action[:20]
        if self.error_patterns.get(action_key, 0) >= 3:
            return ValidationResult(
                approved=False,
                confidence=0.8,
                reason=f"Pattern detected: {action_key} has failed {self.error_patterns[action_key]} times",
                correction="Try alternative approach"
            )
        
        # If validator model available, use it
        if self.validator:
            return self._validate_with_model(action)
        
        # Default: approve
        return ValidationResult(approved=True, confidence=0.9)
    
    def _validate_with_model(self, action: ActionRecord) -> ValidationResult:
        """Use LLM to validate action logic."""
        try:
            context = self._build_validation_context(action)
            
            prompt = f"""You are a Supervisor validating task execution.

{context}

Question: Was this action appropriate for accomplishing the task?
Answer with:
- APPROVED: if the action makes sense
- REJECTED: if the action is wrong or unnecessary
- Followed by a brief reason.

Example responses:
"APPROVED - Opening Safari is the correct first step"
"REJECTED - Wrong application, should open Chrome instead"

Your response:"""
            
            # Call validator model
            if hasattr(self.validator, 'validate_step'):
                result = self.validator.validate_step(
                    task=self.state.task_description,
                    last_action=action.action
                )
                return ValidationResult(
                    approved=result.get("approved", True),
                    confidence=0.8,
                    reason=result.get("reason", "")
                )
            
            return ValidationResult(approved=True)
            
        except Exception as e:
            logger.warning(f"Validator error: {e}")
            return ValidationResult(approved=True, reason="Validator unavailable")
    
    def _build_validation_context(self, action: ActionRecord) -> str:
        """Build context for validation prompt."""
        recent = self.state.action_history[-5:-1] if len(self.state.action_history) > 1 else []
        recent_text = "\n".join(f"  - {a.action}" for a in recent) if recent else "(first action)"
        
        return f"""## Task
{self.state.task_description}

## Progress
Batch {action.batch_idx + 1}/{len(self.state.batches)}
Actions completed: {len(self.state.action_history)}

## Recent Actions:
{recent_text}

## Action to Validate:
{action.action}
Result: {"Success" if action.success else f"Failed - {action.error}"}"""
    
    def _intervene(self, action: ActionRecord, validation: ValidationResult):
        """Pause executor and log intervention."""
        logger.warning(f"🚨 Supervisor intervention: {validation.reason}")
        
        intervention = Intervention(
            timestamp=datetime.now(),
            action_idx=action.action_idx,
            batch_idx=action.batch_idx,
            reason=validation.reason,
            correction=validation.correction
        )
        self.interventions.append(intervention)
        self.state.interventions.append({
            "timestamp": intervention.timestamp.isoformat(),
            "reason": intervention.reason,
            "correction": intervention.correction
        })
        
        # Pause the executor
        self.state.pause(validation.reason)
        
        # Track error pattern
        action_key = action.action.split(":")[0] if ":" in action.action else action.action[:20]
        self.error_patterns[action_key] = self.error_patterns.get(action_key, 0) + 1
    
    def _check_error_patterns(self):
        """Check for concerning patterns that might indicate stuck states."""
        # Check for many consecutive failures
        recent = self.state.action_history[-5:] if len(self.state.action_history) >= 5 else []
        failed_count = sum(1 for a in recent if not a.success)
        
        if failed_count >= 4:
            logger.warning("🚨 Pattern detected: 4+ recent failures")
            if self.state.status == LoopStatus.RUNNING:
                self.state.pause("Too many consecutive failures")
    
    def validate_checkpoint(self) -> ValidationResult:
        """
        Checkpoint-based validation (alternative to real-time).
        Called explicitly after each batch or at defined checkpoints.
        """
        if not self.state.action_history:
            return ValidationResult(approved=True)
        
        # Validate overall progress
        failed = sum(1 for a in self.state.action_history if not a.success)
        total = len(self.state.action_history)
        
        success_rate = (total - failed) / total if total > 0 else 1.0
        
        if success_rate < 0.5:
            return ValidationResult(
                approved=False,
                confidence=0.9,
                reason=f"Low success rate: {success_rate:.0%} ({failed}/{total} failed)",
                correction="Consider rolling back to last checkpoint"
            )
        
        return ValidationResult(
            approved=True,
            confidence=success_rate,
            reason=f"Success rate: {success_rate:.0%}"
        )
    
    def get_context_prompt(self) -> str:
        """Generate context prompt for supervisor's awareness."""
        recent = self.state.action_history[-10:] if self.state.action_history else []
        errors = [a for a in recent if not a.success]
        
        return f"""## Supervisor Context [Task: {self.state.task_id}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Task:** {self.state.task_description}
**Executor Status:** {self.state.status.value}
**Actions Monitored:** {len(self.state.action_history)}
**Recent Errors:** {len(errors)}
**Interventions Made:** {len(self.interventions)}

### Error Patterns:
{self._format_error_patterns()}

### Last Intervention:
{self._format_last_intervention()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    
    def _format_error_patterns(self) -> str:
        if not self.error_patterns:
            return "  (none detected)"
        lines = [f"  - {k}: {v} occurrences" for k, v in self.error_patterns.items()]
        return "\n".join(lines)
    
    def _format_last_intervention(self) -> str:
        if not self.interventions:
            return "  (none)"
        last = self.interventions[-1]
        return f"  Reason: {last.reason}\n  Correction: {last.correction or 'N/A'}"
