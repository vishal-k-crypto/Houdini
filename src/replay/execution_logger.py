"""
Execution Logger - Records every event during task execution for replay.

This logger captures:
- Cursor positions (x, y, timestamp)
- Thinking window content (component, message, level)
- Action executions (action, success, duration)
- Screenshots at checkpoints
- Supervisor interventions
- State transitions

All events are timestamped in milliseconds for precise replay.
"""

import json
import time
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from pathlib import Path
from enum import Enum
import threading

# pyautogui is optional - only needed for cursor tracking during live execution
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


class EventType(str, Enum):
    """Types of events that can be logged."""
    # Cursor events
    CURSOR_MOVE = "cursor_move"
    CURSOR_CLICK = "cursor_click"
    CURSOR_DRAG = "cursor_drag"
    
    # Thinking events (from thinking window)
    THINKING_PLANNER = "thinking_planner"
    THINKING_EXECUTOR = "thinking_executor"
    THINKING_SUPERVISOR = "thinking_supervisor"
    THINKING_SYSTEM = "thinking_system"
    
    # Action events
    ACTION_START = "action_start"
    ACTION_COMPLETE = "action_complete"
    ACTION_FAILED = "action_failed"
    
    # Batch events
    BATCH_START = "batch_start"
    BATCH_COMPLETE = "batch_complete"
    
    # State events
    PHASE_CHANGE = "phase_change"
    STATUS_CHANGE = "status_change"
    
    # Supervisor events
    SUPERVISOR_INTERVENTION = "supervisor_intervention"
    SUPERVISOR_VALIDATION = "supervisor_validation"
    
    # Screenshot checkpoints
    SCREENSHOT = "screenshot"
    
    # Task events
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    
    # Keyboard events
    KEY_PRESS = "key_press"
    KEY_HOTKEY = "key_hotkey"
    TEXT_TYPE = "text_type"


@dataclass
class ExecutionEvent:
    """A single event in the execution timeline."""
    event_type: EventType
    timestamp_ms: int  # Milliseconds since epoch
    relative_ms: int   # Milliseconds since task start
    data: Dict[str, Any]
    
    # Optional cursor position at time of event
    cursor_x: Optional[int] = None
    cursor_y: Optional[int] = None
    
    # Optional screenshot reference
    screenshot_path: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d['event_type'] = self.event_type.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ExecutionEvent':
        """Create from dictionary."""
        data = data.copy()
        data['event_type'] = EventType(data['event_type'])
        return cls(**data)


@dataclass
class ExecutionSession:
    """A complete execution session."""
    task_id: str
    task_description: str
    started_at: str
    completed_at: Optional[str] = None
    success: bool = False
    events: List[ExecutionEvent] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "task_description": self.task_description,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
            "events": [e.to_dict() for e in self.events],
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ExecutionSession':
        """Create from dictionary."""
        events = [ExecutionEvent.from_dict(e) for e in data.get("events", [])]
        return cls(
            task_id=data["task_id"],
            task_description=data["task_description"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            success=data.get("success", False),
            events=events,
            metadata=data.get("metadata", {}),
        )
    
    def duration_ms(self) -> int:
        """Total duration in milliseconds."""
        if not self.events:
            return 0
        return self.events[-1].relative_ms
    
    def event_count_by_type(self) -> Dict[str, int]:
        """Count events by type."""
        counts = {}
        for event in self.events:
            key = event.event_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts


class ExecutionLogger:
    """
    Logs all events during task execution for later replay.
    
    This is a singleton that captures events in real-time
    and saves them to disk for later replay.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.sessions_dir = Path(__file__).parent.parent.parent / "data" / "replay_sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_session: Optional[ExecutionSession] = None
        self.session_start_time_ms: int = 0
        self.cursor_tracking = False
        self.cursor_thread: Optional[threading.Thread] = None
        self._cursor_tracking_stop = threading.Event()
        
        # Cursor sampling settings
        self.cursor_sample_rate_ms = 50  # Sample every 50ms
        self.last_cursor_pos = (0, 0)
        
        self._initialized = True
    
    def start_session(self, task_id: str, task_description: str, 
                      metadata: Optional[Dict] = None) -> ExecutionSession:
        """Start a new execution session."""
        self.session_start_time_ms = int(time.time() * 1000)
        
        self.current_session = ExecutionSession(
            task_id=task_id,
            task_description=task_description,
            started_at=datetime.now().isoformat(),
            metadata=metadata or {}
        )
        
        # Log task start event
        self.log_event(EventType.TASK_START, {
            "task_id": task_id,
            "task_description": task_description,
        })
        
        # Start cursor tracking
        self._start_cursor_tracking()
        
        return self.current_session
    
    def end_session(self, success: bool = True, error: Optional[str] = None):
        """End the current execution session and save to disk."""
        if not self.current_session:
            return
        
        # Stop cursor tracking
        self._stop_cursor_tracking()
        
        # Log task completion
        event_type = EventType.TASK_COMPLETE if success else EventType.TASK_FAILED
        self.log_event(event_type, {
            "success": success,
            "error": error,
            "duration_ms": self.current_session.duration_ms(),
            "event_count": len(self.current_session.events),
        })
        
        self.current_session.completed_at = datetime.now().isoformat()
        self.current_session.success = success
        
        # Save to disk
        self._save_session()
        
        # Clear current session
        self.current_session = None
    
    def log_event(self, event_type: EventType, data: Dict[str, Any],
                  screenshot_path: Optional[str] = None):
        """Log an event with current cursor position."""
        if not self.current_session:
            return
        
        now_ms = int(time.time() * 1000)
        relative_ms = now_ms - self.session_start_time_ms
        
        # Get current cursor position
        cursor_x, cursor_y = None, None
        if PYAUTOGUI_AVAILABLE:
            try:
                cursor_x, cursor_y = pyautogui.position()
            except:
                pass
        
        event = ExecutionEvent(
            event_type=event_type,
            timestamp_ms=now_ms,
            relative_ms=relative_ms,
            data=data,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            screenshot_path=screenshot_path,
        )
        
        self.current_session.events.append(event)
    
    def log_cursor_move(self, x: int, y: int):
        """Log a cursor movement (sampled)."""
        self.log_event(EventType.CURSOR_MOVE, {"x": x, "y": y})
    
    def log_cursor_click(self, x: int, y: int, button: str = "left"):
        """Log a cursor click."""
        self.log_event(EventType.CURSOR_CLICK, {
            "x": x, "y": y, "button": button
        })
    
    def log_thinking(self, component: str, message: str, level: str = "info"):
        """Log a thinking window message."""
        event_type = {
            "planner": EventType.THINKING_PLANNER,
            "executor": EventType.THINKING_EXECUTOR,
            "supervisor": EventType.THINKING_SUPERVISOR,
        }.get(component.lower(), EventType.THINKING_SYSTEM)
        
        self.log_event(event_type, {
            "component": component,
            "message": message,
            "level": level,
        })
    
    def log_action(self, action: str, action_type: str = "blind"):
        """Log action start."""
        self.log_event(EventType.ACTION_START, {
            "action": action,
            "action_type": action_type,
        })
    
    def log_action_complete(self, action: str, success: bool, 
                           duration_ms: float, error: Optional[str] = None):
        """Log action completion."""
        event_type = EventType.ACTION_COMPLETE if success else EventType.ACTION_FAILED
        self.log_event(event_type, {
            "action": action,
            "success": success,
            "duration_ms": duration_ms,
            "error": error,
        })
    
    def log_batch_start(self, batch_idx: int, batch_type: str, description: str):
        """Log batch execution start."""
        self.log_event(EventType.BATCH_START, {
            "batch_idx": batch_idx,
            "batch_type": batch_type,
            "description": description,
        })
    
    def log_batch_complete(self, batch_idx: int, success: bool):
        """Log batch completion."""
        self.log_event(EventType.BATCH_COMPLETE, {
            "batch_idx": batch_idx,
            "success": success,
        })
    
    def log_phase_change(self, old_phase: str, new_phase: str):
        """Log a phase change."""
        self.log_event(EventType.PHASE_CHANGE, {
            "old_phase": old_phase,
            "new_phase": new_phase,
        })
    
    def log_supervisor_intervention(self, reason: str, decision: str,
                                    correction: Optional[str] = None):
        """Log a supervisor intervention."""
        self.log_event(EventType.SUPERVISOR_INTERVENTION, {
            "reason": reason,
            "decision": decision,
            "correction": correction,
        })
    
    def log_screenshot(self, screenshot_path: str, description: str = ""):
        """Log a screenshot checkpoint."""
        self.log_event(EventType.SCREENSHOT, {
            "description": description,
        }, screenshot_path=screenshot_path)
    
    def log_key_press(self, key: str):
        """Log a key press."""
        self.log_event(EventType.KEY_PRESS, {"key": key})
    
    def log_hotkey(self, keys: List[str]):
        """Log a hotkey combination."""
        self.log_event(EventType.KEY_HOTKEY, {"keys": keys})
    
    def log_text_type(self, text: str):
        """Log text typing."""
        self.log_event(EventType.TEXT_TYPE, {"text": text})
    
    def log_screenshot_auto(self, trigger: str = "checkpoint", description: str = "") -> Optional[str]:
        """
        Automatically capture and log a screenshot.
        
        Args:
            trigger: What triggered this screenshot (e.g., 'batch_start', 'error', 'intervention')
            description: Human-readable description
            
        Returns:
            Path to saved screenshot, or None if capture failed
        """
        if not PYAUTOGUI_AVAILABLE:
            return None
        
        if not self.current_session:
            return None
        
        try:
            import subprocess
            import tempfile
            
            # Create screenshots directory
            screenshots_dir = self.sessions_dir.parent / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename with timestamp and trigger
            timestamp = int(time.time() * 1000)
            safe_trigger = "".join(c if c.isalnum() else "_" for c in trigger[:20])
            filename = f"{self.current_session.task_id}_{timestamp}_{safe_trigger}.png"
            filepath = screenshots_dir / filename
            
            # Capture screen using macOS screencapture (fast and reliable)
            result = subprocess.run(
                ["screencapture", "-x", "-C", str(filepath)],
                capture_output=True, timeout=5
            )
            
            if result.returncode == 0 and filepath.exists():
                # Log the screenshot event
                self.log_event(EventType.SCREENSHOT, {
                    "trigger": trigger,
                    "description": description or f"Auto-captured on {trigger}",
                }, screenshot_path=str(filepath))
                
                return str(filepath)
        except Exception:
            pass
        
        return None
    
    def _start_cursor_tracking(self):
        """Start background cursor position tracking."""
        if not PYAUTOGUI_AVAILABLE:
            return  # Can't track cursor without pyautogui
        
        if self.cursor_tracking:
            return
        
        self.cursor_tracking = True
        self._cursor_tracking_stop.clear()
        
        def track_cursor():
            while not self._cursor_tracking_stop.is_set():
                try:
                    x, y = pyautogui.position()
                    # Only log if position changed significantly
                    if abs(x - self.last_cursor_pos[0]) > 5 or abs(y - self.last_cursor_pos[1]) > 5:
                        self.log_cursor_move(x, y)
                        self.last_cursor_pos = (x, y)
                except:
                    pass
                time.sleep(self.cursor_sample_rate_ms / 1000)
        
        self.cursor_thread = threading.Thread(target=track_cursor, daemon=True)
        self.cursor_thread.start()
    
    def _stop_cursor_tracking(self):
        """Stop cursor position tracking."""
        self.cursor_tracking = False
        self._cursor_tracking_stop.set()
        if self.cursor_thread:
            self.cursor_thread.join(timeout=1.0)
            self.cursor_thread = None
    
    def _save_session(self):
        """Save current session to disk."""
        if not self.current_session:
            return
        
        filename = f"{self.current_session.task_id}_{self.current_session.started_at.replace(':', '-').replace('.', '-')}.json"
        filepath = self.sessions_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(self.current_session.to_dict(), f, indent=2)
    
    def get_session_files(self) -> List[Path]:
        """Get all saved session files."""
        return sorted(self.sessions_dir.glob("*.json"), reverse=True)
    
    def load_session(self, filepath: Path) -> ExecutionSession:
        """Load a session from disk."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return ExecutionSession.from_dict(data)
    
    def load_session_by_task_id(self, task_id: str) -> Optional[ExecutionSession]:
        """Load the most recent session for a task ID."""
        for filepath in self.get_session_files():
            if filepath.name.startswith(task_id):
                return self.load_session(filepath)
        return None


# Global logger instance
_execution_logger: Optional[ExecutionLogger] = None


def get_execution_logger() -> ExecutionLogger:
    """Get the global execution logger instance."""
    global _execution_logger
    if _execution_logger is None:
        _execution_logger = ExecutionLogger()
    return _execution_logger


# Convenience functions for logging from anywhere
def log_thinking(component: str, message: str, level: str = "info"):
    """Log a thinking event."""
    logger = get_execution_logger()
    logger.log_thinking(component, message, level)


def log_action(action: str, action_type: str = "blind"):
    """Log an action start."""
    logger = get_execution_logger()
    logger.log_action(action, action_type)


def log_action_complete(action: str, success: bool, duration_ms: float, error: Optional[str] = None):
    """Log action completion."""
    logger = get_execution_logger()
    logger.log_action_complete(action, success, duration_ms, error)
