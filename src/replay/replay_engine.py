"""
Replay Engine - Loads and plays back execution sessions.

The replay engine provides:
- Session loading and parsing
- Timeline navigation (play, pause, seek)
- Speed control (0.5x, 1x, 2x, etc.)
- Event filtering by type
- Cursor trajectory rendering
"""

import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Set
from pathlib import Path
from enum import Enum
import threading

from .execution_logger import (
    ExecutionLogger, ExecutionSession, ExecutionEvent, EventType,
    get_execution_logger
)


class ReplayState(str, Enum):
    """Current state of replay."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass 
class TimelineMarker:
    """A marker on the timeline (e.g., batch start, error, checkpoint)."""
    position_ms: int
    label: str
    marker_type: str  # "batch", "error", "checkpoint", "supervisor"
    event_index: int
    color: str = "#00ff88"


@dataclass
class ReplaySession:
    """
    An active replay session with navigation controls.
    """
    session: ExecutionSession
    state: ReplayState = ReplayState.STOPPED
    
    # Playback position (milliseconds from start)
    position_ms: int = 0
    
    # Playback speed (1.0 = realtime, 2.0 = 2x speed)
    speed: float = 1.0
    
    # Current event index
    current_event_idx: int = 0
    
    # Filtered event types (None = show all)
    event_filter: Optional[Set[EventType]] = None
    
    # Timeline markers for quick navigation
    markers: List[TimelineMarker] = field(default_factory=list)
    
    # Callbacks
    on_event: Optional[Callable[[ExecutionEvent], None]] = None
    on_position_change: Optional[Callable[[int], None]] = None
    on_state_change: Optional[Callable[[ReplayState], None]] = None
    
    def __post_init__(self):
        """Generate timeline markers from events."""
        self.markers = self._generate_markers()
    
    def _generate_markers(self) -> List[TimelineMarker]:
        """Generate markers for important events."""
        markers = []
        
        for i, event in enumerate(self.session.events):
            marker = None
            
            if event.event_type == EventType.BATCH_START:
                batch_idx = event.data.get("batch_idx", 0)
                desc = event.data.get("description", "")[:30]
                marker = TimelineMarker(
                    position_ms=event.relative_ms,
                    label=f"Batch {batch_idx + 1}: {desc}",
                    marker_type="batch",
                    event_index=i,
                    color="#00d4ff"
                )
            elif event.event_type == EventType.ACTION_FAILED:
                action = event.data.get("action", "")[:30]
                marker = TimelineMarker(
                    position_ms=event.relative_ms,
                    label=f"❌ Failed: {action}",
                    marker_type="error",
                    event_index=i,
                    color="#ff3b30"
                )
            elif event.event_type == EventType.SCREENSHOT:
                marker = TimelineMarker(
                    position_ms=event.relative_ms,
                    label=f"📸 {event.data.get('description', 'Screenshot')}",
                    marker_type="checkpoint",
                    event_index=i,
                    color="#ffd60a"
                )
            elif event.event_type == EventType.SUPERVISOR_INTERVENTION:
                reason = event.data.get("reason", "")[:30]
                marker = TimelineMarker(
                    position_ms=event.relative_ms,
                    label=f"👁️ {reason}",
                    marker_type="supervisor",
                    event_index=i,
                    color="#bf5af2"
                )
            elif event.event_type == EventType.PHASE_CHANGE:
                new_phase = event.data.get("new_phase", "")
                marker = TimelineMarker(
                    position_ms=event.relative_ms,
                    label=f"Phase: {new_phase}",
                    marker_type="phase",
                    event_index=i,
                    color="#00ff88"
                )
            
            if marker:
                markers.append(marker)
        
        return markers
    
    @property
    def duration_ms(self) -> int:
        """Total duration of the session."""
        return self.session.duration_ms()
    
    @property
    def progress(self) -> float:
        """Current progress as a percentage (0-100)."""
        if self.duration_ms == 0:
            return 0
        return (self.position_ms / self.duration_ms) * 100
    
    def get_events_in_range(self, start_ms: int, end_ms: int) -> List[ExecutionEvent]:
        """Get all events in a time range."""
        events = []
        for event in self.session.events:
            if start_ms <= event.relative_ms <= end_ms:
                if self.event_filter is None or event.event_type in self.event_filter:
                    events.append(event)
        return events
    
    def get_current_event(self) -> Optional[ExecutionEvent]:
        """Get the current event based on position."""
        if not self.session.events:
            return None
        
        # Find the event at or just before current position
        for i, event in enumerate(self.session.events):
            if event.relative_ms > self.position_ms:
                return self.session.events[max(0, i - 1)]
        
        return self.session.events[-1]
    
    def get_cursor_at_position(self) -> tuple[Optional[int], Optional[int]]:
        """Get cursor position at current playback position."""
        event = self.get_current_event()
        if event:
            return event.cursor_x, event.cursor_y
        return None, None
    
    def get_thinking_history(self, max_items: int = 10) -> List[Dict]:
        """Get thinking messages up to current position."""
        thinking_types = {
            EventType.THINKING_PLANNER,
            EventType.THINKING_EXECUTOR,
            EventType.THINKING_SUPERVISOR,
            EventType.THINKING_SYSTEM,
        }
        
        messages = []
        for event in self.session.events:
            if event.relative_ms > self.position_ms:
                break
            if event.event_type in thinking_types:
                messages.append({
                    "component": event.data.get("component", "system"),
                    "message": event.data.get("message", ""),
                    "level": event.data.get("level", "info"),
                    "time_ms": event.relative_ms,
                })
        
        return messages[-max_items:]
    
    def seek_to_marker(self, marker_idx: int):
        """Seek to a specific marker."""
        if 0 <= marker_idx < len(self.markers):
            marker = self.markers[marker_idx]
            self.seek_to(marker.position_ms)
            self.current_event_idx = marker.event_index
    
    def seek_to(self, position_ms: int):
        """Seek to a specific position."""
        self.position_ms = max(0, min(position_ms, self.duration_ms))
        
        # Update current event index
        for i, event in enumerate(self.session.events):
            if event.relative_ms >= self.position_ms:
                self.current_event_idx = i
                break
        else:
            self.current_event_idx = len(self.session.events) - 1
        
        if self.on_position_change:
            self.on_position_change(self.position_ms)
    
    def seek_relative(self, delta_ms: int):
        """Seek relative to current position."""
        self.seek_to(self.position_ms + delta_ms)
    
    def next_marker(self):
        """Jump to next marker."""
        for marker in self.markers:
            if marker.position_ms > self.position_ms:
                self.seek_to(marker.position_ms)
                return
    
    def prev_marker(self):
        """Jump to previous marker."""
        for marker in reversed(self.markers):
            if marker.position_ms < self.position_ms - 100:  # 100ms buffer
                self.seek_to(marker.position_ms)
                return


class ReplayEngine:
    """
    Engine for loading and managing replay sessions.
    
    Features:
    - List available sessions
    - Load sessions from disk
    - Import from existing execution history
    - Play/pause/seek controls
    """
    
    def __init__(self):
        self.logger = get_execution_logger()
        self.active_session: Optional[ReplaySession] = None
        self._playback_thread: Optional[threading.Thread] = None
        self._playback_stop = threading.Event()
    
    def list_sessions(self) -> List[Dict]:
        """List all available replay sessions."""
        sessions = []
        
        for filepath in self.logger.get_session_files():
            try:
                with open(filepath, 'r') as f:
                    import json
                    data = json.load(f)
                    sessions.append({
                        "filepath": str(filepath),
                        "task_id": data.get("task_id", "unknown"),
                        "task_description": data.get("task_description", ""),
                        "started_at": data.get("started_at", ""),
                        "success": data.get("success", False),
                        "event_count": len(data.get("events", [])),
                    })
            except Exception as e:
                continue
        
        return sessions
    
    def load_session(self, filepath_or_task_id: str) -> Optional[ReplaySession]:
        """Load a session by filepath or task ID."""
        filepath = Path(filepath_or_task_id)
        
        # If not a direct path, try to find by task ID
        if not filepath.exists():
            session = self.logger.load_session_by_task_id(filepath_or_task_id)
            if session:
                self.active_session = ReplaySession(session=session)
                return self.active_session
            return None
        
        session = self.logger.load_session(filepath)
        self.active_session = ReplaySession(session=session)
        return self.active_session
    
    def import_from_screenshots(self, task_id: str) -> Optional[ReplaySession]:
        """
        Create a replay session from existing screenshot checkpoints.
        
        This allows replaying older executions that were recorded
        before the full logging was implemented.
        """
        screenshots_dir = Path(__file__).parent.parent.parent / "data" / "screenshots" / task_id
        
        if not screenshots_dir.exists():
            return None
        
        # Find all screenshots
        screenshots = sorted(screenshots_dir.glob("*.png"))
        
        if not screenshots:
            return None
        
        # Create a synthetic session from screenshots
        events = []
        for i, ss_path in enumerate(screenshots):
            # Parse timestamp from filename (format: YYYYMMDD_HHMMSS_description.png)
            parts = ss_path.stem.split("_")
            if len(parts) >= 2:
                try:
                    date_str = parts[0]
                    time_str = parts[1]
                    timestamp = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                    timestamp_ms = int(timestamp.timestamp() * 1000)
                except:
                    timestamp_ms = i * 1000  # Fallback to 1 second intervals
            else:
                timestamp_ms = i * 1000
            
            description = "_".join(parts[2:]) if len(parts) > 2 else f"Screenshot {i+1}"
            
            events.append(ExecutionEvent(
                event_type=EventType.SCREENSHOT,
                timestamp_ms=timestamp_ms,
                relative_ms=i * 2000,  # 2 second intervals for display
                data={"description": description},
                screenshot_path=str(ss_path),
            ))
        
        # Determine start time from first screenshot
        first_timestamp = screenshots[0].stem.split("_")[:2]
        try:
            started_at = datetime.strptime(f"{first_timestamp[0]}_{first_timestamp[1]}", "%Y%m%d_%H%M%S")
        except:
            started_at = datetime.now()
        
        session = ExecutionSession(
            task_id=task_id,
            task_description=f"Imported from screenshots ({len(screenshots)} checkpoints)",
            started_at=started_at.isoformat(),
            completed_at=datetime.now().isoformat(),
            success=True,
            events=events,
            metadata={"source": "screenshots_import"},
        )
        
        self.active_session = ReplaySession(session=session)
        return self.active_session
    
    def play(self, on_event: Optional[Callable[[ExecutionEvent], None]] = None):
        """Start playback of the active session."""
        if not self.active_session:
            return
        
        self.active_session.state = ReplayState.PLAYING
        self.active_session.on_event = on_event
        
        # Stop any existing playback
        self._playback_stop.set()
        if self._playback_thread:
            self._playback_thread.join(timeout=1.0)
        
        # Start new playback
        self._playback_stop.clear()
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()
    
    def pause(self):
        """Pause playback."""
        if self.active_session:
            self.active_session.state = ReplayState.PAUSED
    
    def stop(self):
        """Stop playback and reset position."""
        self._playback_stop.set()
        if self._playback_thread:
            self._playback_thread.join(timeout=1.0)
            self._playback_thread = None
        
        if self.active_session:
            self.active_session.state = ReplayState.STOPPED
            self.active_session.position_ms = 0
            self.active_session.current_event_idx = 0
    
    def set_speed(self, speed: float):
        """Set playback speed."""
        if self.active_session:
            self.active_session.speed = max(0.1, min(10.0, speed))
    
    def _playback_loop(self):
        """Main playback loop."""
        if not self.active_session:
            return
        
        session = self.active_session
        last_time = time.time()
        
        while not self._playback_stop.is_set():
            if session.state != ReplayState.PLAYING:
                time.sleep(0.05)
                continue
            
            # Calculate elapsed time
            now = time.time()
            elapsed_real_ms = (now - last_time) * 1000
            elapsed_playback_ms = elapsed_real_ms * session.speed
            last_time = now
            
            # Update position
            new_position = session.position_ms + int(elapsed_playback_ms)
            session.seek_to(new_position)
            
            # Emit events that occurred in this interval
            if session.on_event:
                events = session.get_events_in_range(
                    session.position_ms - int(elapsed_playback_ms),
                    session.position_ms
                )
                for event in events:
                    session.on_event(event)
            
            # Check if we've reached the end
            if session.position_ms >= session.duration_ms:
                session.state = ReplayState.STOPPED
                break
            
            time.sleep(0.016)  # ~60fps update rate


def list_available_task_ids() -> List[str]:
    """List task IDs that have screenshot data available for replay."""
    screenshots_dir = Path(__file__).parent.parent.parent / "data" / "screenshots"
    
    if not screenshots_dir.exists():
        return []
    
    # Get all task ID folders
    task_ids = []
    for item in screenshots_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Check if folder has screenshots
            screenshots = list(item.glob("*.png"))
            if screenshots:
                task_ids.append(item.name)
    
    return sorted(task_ids)
