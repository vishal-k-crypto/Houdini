#!/usr/bin/env python3
"""
Test script for the Time Travel Debugging (Replay) feature.
Verifies that the execution logger and replay engine work correctly.
"""

import sys
import time
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.replay.execution_logger import (
    ExecutionLogger, ExecutionEvent, EventType,
    get_execution_logger
)
from src.replay.replay_engine import ReplayEngine, ReplaySession, list_available_task_ids


def test_execution_logger():
    """Test the execution logger."""
    print("🧪 Testing ExecutionLogger...")
    
    # Create a logger with temp directory
    logger = ExecutionLogger()
    original_dir = logger.sessions_dir
    logger.sessions_dir = Path(tempfile.mkdtemp()) / "test_sessions"
    logger.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Start a session
        session = logger.start_session(
            task_id="test123",
            task_description="Test task for replay",
            metadata={"test": True}
        )
        
        assert session is not None
        assert session.task_id == "test123"
        print("  ✓ Session started")
        
        # Log some events
        logger.log_thinking("planner", "Analyzing task...", "info")
        time.sleep(0.05)
        logger.log_action("hotkey:command,space", "blind")
        time.sleep(0.05)
        logger.log_action_complete("hotkey:command,space", True, 50.0)
        time.sleep(0.05)
        logger.log_cursor_click(500, 300)
        logger.log_batch_start(0, "blind", "Open application")
        logger.log_batch_complete(0, True)
        logger.log_phase_change("planning", "executing")
        print("  ✓ Events logged")
        
        # End session
        logger.end_session(success=True)
        print("  ✓ Session ended")
        
        # Check saved file
        session_files = list(logger.sessions_dir.glob("*.json"))
        assert len(session_files) == 1
        print(f"  ✓ Session saved to: {session_files[0].name}")
        
        # Load and verify
        loaded = logger.load_session(session_files[0])
        assert loaded.task_id == "test123"
        assert len(loaded.events) >= 7  # At least 7 events logged
        assert loaded.success == True
        print(f"  ✓ Session loaded with {len(loaded.events)} events")
        
        # Check event types
        event_types = {e.event_type for e in loaded.events}
        assert EventType.TASK_START in event_types
        assert EventType.THINKING_PLANNER in event_types
        assert EventType.ACTION_START in event_types
        assert EventType.ACTION_COMPLETE in event_types
        assert EventType.CURSOR_CLICK in event_types
        print("  ✓ All expected event types present")
        
        print("✅ ExecutionLogger tests passed!\n")
        
    finally:
        # Cleanup
        import shutil
        if logger.sessions_dir.exists():
            shutil.rmtree(logger.sessions_dir.parent)
        logger.sessions_dir = original_dir


def test_replay_session():
    """Test replay session navigation."""
    print("🧪 Testing ReplaySession...")
    
    from src.replay.execution_logger import ExecutionSession
    
    # Create a mock session with events
    events = [
        ExecutionEvent(
            event_type=EventType.TASK_START,
            timestamp_ms=1000,
            relative_ms=0,
            data={"task": "test"},
            cursor_x=100, cursor_y=100
        ),
        ExecutionEvent(
            event_type=EventType.THINKING_PLANNER,
            timestamp_ms=1500,
            relative_ms=500,
            data={"message": "Planning..."},
            cursor_x=150, cursor_y=150
        ),
        ExecutionEvent(
            event_type=EventType.BATCH_START,
            timestamp_ms=2000,
            relative_ms=1000,
            data={"batch_idx": 0, "description": "Batch 1"},
            cursor_x=200, cursor_y=200
        ),
        ExecutionEvent(
            event_type=EventType.ACTION_COMPLETE,
            timestamp_ms=3000,
            relative_ms=2000,
            data={"action": "click", "success": True},
            cursor_x=300, cursor_y=300
        ),
        ExecutionEvent(
            event_type=EventType.TASK_COMPLETE,
            timestamp_ms=4000,
            relative_ms=3000,
            data={"success": True},
            cursor_x=400, cursor_y=400
        ),
    ]
    
    session = ExecutionSession(
        task_id="replay_test",
        task_description="Test replay session",
        started_at="2026-01-15T10:00:00",
        completed_at="2026-01-15T10:00:03",
        success=True,
        events=events
    )
    
    replay = ReplaySession(session=session)
    
    # Test duration
    assert replay.duration_ms == 3000
    print("  ✓ Duration calculation correct")
    
    # Test markers generation
    assert len(replay.markers) >= 1  # At least batch start marker
    print(f"  ✓ Generated {len(replay.markers)} timeline markers")
    
    # Test seeking
    replay.seek_to(1500)
    assert replay.position_ms == 1500
    print("  ✓ Seek to position works")
    
    # Test cursor position at current position
    x, y = replay.get_cursor_at_position()
    assert x is not None and y is not None
    print(f"  ✓ Cursor position at 1500ms: ({x}, {y})")
    
    # Test thinking history
    thinking = replay.get_thinking_history(10)
    assert len(thinking) >= 1
    print(f"  ✓ Thinking history: {len(thinking)} messages")
    
    # Test progress
    replay.seek_to(1500)
    assert 40 < replay.progress < 60  # Should be around 50%
    print(f"  ✓ Progress at 1500ms: {replay.progress:.1f}%")
    
    print("✅ ReplaySession tests passed!\n")


def test_replay_engine():
    """Test replay engine session management."""
    print("🧪 Testing ReplayEngine...")
    
    engine = ReplayEngine()
    
    # Test list sessions (should work even if empty)
    sessions = engine.list_sessions()
    print(f"  ✓ Listed {len(sessions)} sessions")
    
    # Test list available task IDs
    task_ids = list_available_task_ids()
    print(f"  ✓ Found {len(task_ids)} task IDs with screenshots")
    
    print("✅ ReplayEngine tests passed!\n")


def test_serialization():
    """Test event and session serialization."""
    print("🧪 Testing Serialization...")
    
    from src.replay.execution_logger import ExecutionSession
    
    event = ExecutionEvent(
        event_type=EventType.ACTION_START,
        timestamp_ms=1000,
        relative_ms=500,
        data={"action": "click:button"},
        cursor_x=200,
        cursor_y=300,
        screenshot_path="/path/to/screenshot.png"
    )
    
    # Serialize to dict
    event_dict = event.to_dict()
    assert event_dict["event_type"] == "action_start"
    assert event_dict["cursor_x"] == 200
    print("  ✓ Event to dict works")
    
    # Deserialize from dict
    event2 = ExecutionEvent.from_dict(event_dict)
    assert event2.event_type == EventType.ACTION_START
    assert event2.cursor_x == 200
    print("  ✓ Event from dict works")
    
    # Test session serialization
    session = ExecutionSession(
        task_id="ser_test",
        task_description="Serialization test",
        started_at="2026-01-15T10:00:00",
        events=[event]
    )
    
    session_dict = session.to_dict()
    assert session_dict["task_id"] == "ser_test"
    assert len(session_dict["events"]) == 1
    print("  ✓ Session to dict works")
    
    session2 = ExecutionSession.from_dict(session_dict)
    assert session2.task_id == "ser_test"
    assert len(session2.events) == 1
    assert session2.events[0].event_type == EventType.ACTION_START
    print("  ✓ Session from dict works")
    
    print("✅ Serialization tests passed!\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("🕐 TIME TRAVEL DEBUGGING - TEST SUITE")
    print("=" * 60)
    print()
    
    try:
        test_execution_logger()
        test_replay_session()
        test_replay_engine()
        test_serialization()
        
        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print()
        print("The Time Travel Debugging feature is ready to use:")
        print("  python -m src.main --replay")
        print()
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
