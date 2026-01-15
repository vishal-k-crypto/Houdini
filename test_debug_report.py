#!/usr/bin/env python3
"""
Test script for the Debug Report Generator feature.
Verifies that debug reports are generated correctly from execution sessions.
"""

import sys
import time
import tempfile
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.replay.execution_logger import (
    ExecutionLogger, ExecutionEvent, EventType, ExecutionSession,
    get_execution_logger
)
from src.utils.debug_report_generator import (
    DebugReportGenerator, get_debug_report_generator,
    generate_debug_report, export_debug_report
)


def test_debug_report_generator_init():
    """Test that the generator initializes correctly."""
    print("🧪 Testing DebugReportGenerator initialization...")
    
    generator = DebugReportGenerator()
    assert generator.reports_dir.exists()
    print(f"  ✓ Reports directory created: {generator.reports_dir}")
    
    print("✅ Initialization tests passed!\n")


def test_generate_report_from_session():
    """Test generating a debug report from a mock session."""
    print("🧪 Testing report generation from session...")
    
    # Create a mock session with various events
    events = [
        ExecutionEvent(
            event_type=EventType.TASK_START,
            timestamp_ms=1000,
            relative_ms=0,
            data={"task_id": "test_task", "task_description": "Open Safari and search"},
            cursor_x=100, cursor_y=100
        ),
        ExecutionEvent(
            event_type=EventType.THINKING_PLANNER,
            timestamp_ms=1500,
            relative_ms=500,
            data={"component": "planner", "message": "Analyzing task structure...", "level": "info"},
            cursor_x=100, cursor_y=100
        ),
        ExecutionEvent(
            event_type=EventType.BATCH_START,
            timestamp_ms=2000,
            relative_ms=1000,
            data={"batch_idx": 0, "batch_type": "blind", "description": "Open Safari"},
            cursor_x=100, cursor_y=100
        ),
        ExecutionEvent(
            event_type=EventType.ACTION_START,
            timestamp_ms=2100,
            relative_ms=1100,
            data={"action": "hotkey:command,space", "action_type": "blind"},
            cursor_x=150, cursor_y=150
        ),
        ExecutionEvent(
            event_type=EventType.ACTION_COMPLETE,
            timestamp_ms=2300,
            relative_ms=1300,
            data={"action": "hotkey:command,space", "success": True, "duration_ms": 200},
            cursor_x=150, cursor_y=150
        ),
        ExecutionEvent(
            event_type=EventType.ACTION_FAILED,
            timestamp_ms=3000,
            relative_ms=2000,
            data={"action": "click:button", "success": False, "error": "Element not found"},
            cursor_x=300, cursor_y=300
        ),
        ExecutionEvent(
            event_type=EventType.THINKING_SUPERVISOR,
            timestamp_ms=3500,
            relative_ms=2500,
            data={"component": "supervisor", "message": "Detected failure, initiating recovery", "level": "warning"},
            cursor_x=300, cursor_y=300
        ),
        ExecutionEvent(
            event_type=EventType.TASK_FAILED,
            timestamp_ms=4000,
            relative_ms=3000,
            data={"success": False, "error": "Task failed due to element not found"},
            cursor_x=400, cursor_y=400
        ),
    ]
    
    session = ExecutionSession(
        task_id="test_debug_report",
        task_description="Test task for debug report generation",
        started_at="2026-01-16T01:00:00",
        completed_at="2026-01-16T01:00:03",
        success=False,
        events=events,
        metadata={"test": True, "architecture": "test"}
    )
    
    # Generate report
    generator = DebugReportGenerator()
    report = generator.generate_report(session, include_screenshots=False)
    
    assert "# 🔍 Automation Debug Report" in report
    print("  ✓ Report header present")
    
    assert "Executive Summary" in report
    print("  ✓ Executive Summary section present")
    
    assert "test_debug_report" in report
    print("  ✓ Task ID in report")
    
    assert "Failed" in report or "❌" in report
    print("  ✓ Failed status indicated")
    
    assert "Error Analysis" in report
    print("  ✓ Error Analysis section present")
    
    assert "Element not found" in report
    print("  ✓ Error message captured")
    
    assert "AI Thinking Log" in report
    print("  ✓ Thinking Log section present")
    
    assert "Analyzing task structure" in report
    print("  ✓ Planner thinking captured")
    
    assert "Event Timeline" in report
    print("  ✓ Event Timeline section present")
    
    assert "Suggested Analysis Prompts" in report
    print("  ✓ Suggested prompts section present")
    
    print("✅ Report generation tests passed!\n")
    
    return report


def test_export_to_file():
    """Test exporting a report to a file."""
    print("🧪 Testing report export to file...")
    
    # Create temp directory for test
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        session = ExecutionSession(
            task_id="export_test",
            task_description="Test export",
            started_at="2026-01-16T01:00:00",
            success=True,
            events=[
                ExecutionEvent(
                    event_type=EventType.TASK_START,
                    timestamp_ms=1000,
                    relative_ms=0,
                    data={"task_id": "export_test"},
                    cursor_x=100, cursor_y=100
                ),
                ExecutionEvent(
                    event_type=EventType.TASK_COMPLETE,
                    timestamp_ms=2000,
                    relative_ms=1000,
                    data={"success": True},
                    cursor_x=100, cursor_y=100
                ),
            ]
        )
        
        generator = DebugReportGenerator()
        original_dir = generator.reports_dir
        generator.reports_dir = temp_dir
        
        # Export to file
        output_path = generator.export_to_file(session)
        
        assert output_path.exists()
        print(f"  ✓ Report file created: {output_path.name}")
        
        content = output_path.read_text()
        assert "Automation Debug Report" in content
        print("  ✓ Report content valid")
        
        generator.reports_dir = original_dir
        
    finally:
        shutil.rmtree(temp_dir)
    
    print("✅ Export tests passed!\n")


def test_extract_errors():
    """Test error extraction with context."""
    print("🧪 Testing error extraction...")
    
    events = [
        ExecutionEvent(event_type=EventType.TASK_START, timestamp_ms=1000, relative_ms=0, data={}, cursor_x=0, cursor_y=0),
        ExecutionEvent(event_type=EventType.ACTION_START, timestamp_ms=1500, relative_ms=500, data={"action": "click:btn1"}, cursor_x=0, cursor_y=0),
        ExecutionEvent(event_type=EventType.ACTION_COMPLETE, timestamp_ms=1600, relative_ms=600, data={"action": "click:btn1", "success": True}, cursor_x=0, cursor_y=0),
        ExecutionEvent(event_type=EventType.ACTION_START, timestamp_ms=2000, relative_ms=1000, data={"action": "type:text"}, cursor_x=0, cursor_y=0),
        ExecutionEvent(event_type=EventType.ACTION_FAILED, timestamp_ms=2500, relative_ms=1500, data={"action": "type:text", "error": "Timeout"}, cursor_x=100, cursor_y=100),
        ExecutionEvent(event_type=EventType.TASK_FAILED, timestamp_ms=3000, relative_ms=2000, data={"error": "Task failed"}, cursor_x=100, cursor_y=100),
    ]
    
    session = ExecutionSession(
        task_id="error_test",
        task_description="Error extraction test",
        started_at="2026-01-16T01:00:00",
        success=False,
        events=events
    )
    
    generator = DebugReportGenerator()
    errors = generator.extract_errors(session)
    
    assert len(errors) == 2  # ACTION_FAILED and TASK_FAILED
    print(f"  ✓ Found {len(errors)} errors")
    
    # Check first error has context
    first_error = errors[0]
    assert len(first_error["context_before"]) > 0
    print(f"  ✓ Error has {len(first_error['context_before'])} events of context before")
    
    print("✅ Error extraction tests passed!\n")


def test_thinking_log_extraction():
    """Test thinking log extraction."""
    print("🧪 Testing thinking log extraction...")
    
    events = [
        ExecutionEvent(event_type=EventType.THINKING_PLANNER, timestamp_ms=1000, relative_ms=0, 
                      data={"component": "planner", "message": "Planning step 1", "level": "info"}, cursor_x=0, cursor_y=0),
        ExecutionEvent(event_type=EventType.THINKING_EXECUTOR, timestamp_ms=1500, relative_ms=500, 
                      data={"component": "executor", "message": "Executing action", "level": "info"}, cursor_x=0, cursor_y=0),
        ExecutionEvent(event_type=EventType.THINKING_SUPERVISOR, timestamp_ms=2000, relative_ms=1000, 
                      data={"component": "supervisor", "message": "Validating result", "level": "info"}, cursor_x=0, cursor_y=0),
    ]
    
    session = ExecutionSession(
        task_id="thinking_test",
        task_description="Thinking log test",
        started_at="2026-01-16T01:00:00",
        success=True,
        events=events
    )
    
    generator = DebugReportGenerator()
    thinking_log = generator.extract_thinking_log(session)
    
    assert len(thinking_log) == 3
    print(f"  ✓ Extracted {len(thinking_log)} thinking entries")
    
    components = {e["component"] for e in thinking_log}
    assert "planner" in components
    assert "executor" in components
    assert "supervisor" in components
    print("  ✓ All component types captured")
    
    print("✅ Thinking log extraction tests passed!\n")


def test_convenience_functions():
    """Test the convenience functions."""
    print("🧪 Testing convenience functions...")
    
    generator = get_debug_report_generator()
    assert generator is not None
    print("  ✓ get_debug_report_generator() works")
    
    # Create a simple session
    session = ExecutionSession(
        task_id="convenience_test",
        task_description="Convenience test",
        started_at="2026-01-16T01:00:00",
        success=True,
        events=[]
    )
    
    report = generate_debug_report(session)
    assert "Automation Debug Report" in report
    print("  ✓ generate_debug_report() works")
    
    print("✅ Convenience function tests passed!\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("🔍 DEBUG REPORT GENERATOR - TEST SUITE")
    print("=" * 60)
    print()
    
    try:
        test_debug_report_generator_init()
        sample_report = test_generate_report_from_session()
        test_export_to_file()
        test_extract_errors()
        test_thinking_log_extraction()
        test_convenience_functions()
        
        print("=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print()
        print("The Debug Report Generator is ready to use:")
        print("  python -m src.main --debug-report           # Latest session")
        print("  python -m src.main --debug-report-session ID")
        print("  python -m src.main --debug-report-all       # All failed sessions")
        print()
        print("Sample report preview (first 500 chars):")
        print("-" * 40)
        print(sample_report[:500])
        print("-" * 40)
        
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
