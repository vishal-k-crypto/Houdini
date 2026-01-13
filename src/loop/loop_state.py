"""
LoopState - Shared state for execution loops.
Both ExecutorLoop and SupervisorLoop read/write this state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
import json
import uuid


class LoopStatus(str, Enum):
    """Status of the execution loop."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_VISION = "awaiting_vision"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ActionRecord:
    """Record of a single action taken."""
    action_type: str  # "blind" or "vision"
    action: str  # The action string or description
    batch_idx: int
    action_idx: int
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class Checkpoint:
    """A saved state for rollback."""
    checkpoint_id: str
    batch_idx: int
    action_idx: int
    timestamp: datetime
    description: str


@dataclass
class LoopState:
    """
    Shared state between ExecutorLoop and SupervisorLoop.
    
    The model always knows:
    - task_id: Unique identifier for this execution
    - task_description: What we're trying to accomplish
    - batches: The full execution plan
    - current_batch_idx: Which batch we're on
    - current_action_idx: Which action within the batch
    - status: Current loop status
    - action_history: All actions taken so far
    - checkpoints: Saved states for recovery
    """
    
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_description: str = ""
    batches: List[Dict] = field(default_factory=list)
    
    current_batch_idx: int = 0
    current_action_idx: int = 0
    status: LoopStatus = LoopStatus.PENDING
    
    action_history: List[ActionRecord] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Supervisor intervention tracking
    interventions: List[Dict] = field(default_factory=list)
    pause_reason: Optional[str] = None
    
    def get_current_batch(self) -> Optional[Dict]:
        """Get the current batch being executed."""
        if 0 <= self.current_batch_idx < len(self.batches):
            return self.batches[self.current_batch_idx]
        return None
    
    def get_total_actions_in_batch(self) -> int:
        """Get number of actions in current batch."""
        batch = self.get_current_batch()
        if batch and batch.get("type") == "blind":
            return len(batch.get("actions", []))
        return 1  # Vision batches are single actions
    
    def get_progress_string(self) -> str:
        """Human-readable progress string."""
        total_batches = len(self.batches)
        if total_batches == 0:
            return "No batches"
        
        batch_progress = f"Batch {self.current_batch_idx + 1}/{total_batches}"
        batch = self.get_current_batch()
        
        if batch and batch.get("type") == "blind":
            actions = batch.get("actions", [])
            action_progress = f"Action {self.current_action_idx + 1}/{len(actions)}"
            return f"{batch_progress}, {action_progress}"
        
        return batch_progress
    
    def get_context_prompt(self, max_history: int = 5) -> str:
        """
        Generate a compact context prompt for the model.
        This is the key to keeping the model aware of its state.
        """
        # Recent history
        recent_actions = self.action_history[-max_history:] if self.action_history else []
        history_lines = []
        for rec in recent_actions:
            status = "✓" if rec.success else f"✗ {rec.error}"
            history_lines.append(f"  - {rec.action[:60]}... [{status}]")
        history_text = "\n".join(history_lines) if history_lines else "  (none yet)"
        
        # Current batch info
        batch = self.get_current_batch()
        batch_info = json.dumps(batch, indent=2) if batch else "None"
        
        # Remaining work
        remaining_batches = self.batches[self.current_batch_idx:]
        remaining_summary = []
        for i, b in enumerate(remaining_batches[:3]):  # Show next 3 batches
            prefix = "→" if i == 0 else " "
            remaining_summary.append(f"  {prefix} [{b.get('type', '?').upper()}] {b.get('description', '...')[:40]}")
        if len(remaining_batches) > 3:
            remaining_summary.append(f"  ... and {len(remaining_batches) - 3} more batches")
        remaining_text = "\n".join(remaining_summary) if remaining_summary else "  (all done)"
        
        return f"""## Execution Context [Task: {self.task_id}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Task:** {self.task_description}
**Status:** {self.status.value}
**Progress:** {self.get_progress_string()}
**Actions Completed:** {len(self.action_history)}

### Recent History:
{history_text}

### Current Batch:
{batch_info}

### Remaining Work:
{remaining_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    
    def record_action(self, action_type: str, action: str, success: bool = True, 
                      error: Optional[str] = None, duration_ms: float = 0.0):
        """Record an action that was taken."""
        record = ActionRecord(
            action_type=action_type,
            action=action,
            batch_idx=self.current_batch_idx,
            action_idx=self.current_action_idx,
            success=success,
            error=error,
            duration_ms=duration_ms
        )
        self.action_history.append(record)
    
    def advance_action(self):
        """Move to the next action within current batch."""
        self.current_action_idx += 1
    
    def advance_batch(self):
        """Move to the next batch, reset action index."""
        self.current_batch_idx += 1
        self.current_action_idx = 0
    
    def is_batch_complete(self) -> bool:
        """Check if current batch is fully executed."""
        batch = self.get_current_batch()
        if not batch:
            return True
        
        if batch.get("type") == "blind":
            actions = batch.get("actions", [])
            return self.current_action_idx >= len(actions)
        else:
            # Vision batches are single-shot
            return self.current_action_idx > 0
    
    def is_task_complete(self) -> bool:
        """Check if all batches are done."""
        return self.current_batch_idx >= len(self.batches)
    
    def save_checkpoint(self, description: str = "") -> Checkpoint:
        """Save current state as a checkpoint for potential rollback."""
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4())[:8],
            batch_idx=self.current_batch_idx,
            action_idx=self.current_action_idx,
            timestamp=datetime.now(),
            description=description or f"Checkpoint at batch {self.current_batch_idx}"
        )
        self.checkpoints.append(checkpoint)
        return checkpoint
    
    def rollback_to(self, checkpoint_id: str) -> bool:
        """Restore state to a previous checkpoint."""
        for cp in self.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                self.current_batch_idx = cp.batch_idx
                self.current_action_idx = cp.action_idx
                # Remove actions after this point
                self.action_history = [
                    a for a in self.action_history 
                    if a.batch_idx < cp.batch_idx or 
                       (a.batch_idx == cp.batch_idx and a.action_idx < cp.action_idx)
                ]
                return True
        return False
    
    def pause(self, reason: str):
        """Pause execution with a reason."""
        self.status = LoopStatus.PAUSED
        self.pause_reason = reason
    
    def resume(self):
        """Resume from paused state."""
        if self.status == LoopStatus.PAUSED:
            self.status = LoopStatus.RUNNING
            self.pause_reason = None
    
    def to_dict(self) -> Dict:
        """Serialize state for logging/persistence."""
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "status": self.status.value,
            "current_batch_idx": self.current_batch_idx,
            "current_action_idx": self.current_action_idx,
            "actions_completed": len(self.action_history),
            "checkpoints": len(self.checkpoints),
            "interventions": len(self.interventions),
        }
