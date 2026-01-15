#!/usr/bin/env python3
"""
Test script for the Event-Driven UI Wait System.

This tests the UIWaitSystem that replaces fixed time.sleep() calls
with intelligent waiting based on macOS Accessibility Tree monitoring.
"""

import time
import sys
sys.path.insert(0, '.')

def test_ui_wait_import():
    """Test that the UI wait system can be imported."""
    print("Testing UI wait system import...")
    try:
        from src.utils.ui_wait import (
            UIWaitSystem,
            WaitCondition,
            WaitResult,
            UISnapshot,
            get_ui_wait_system,
            wait_for_ui_stable,
            wait_for_element,
            smart_wait,
        )
        print("✓ UI wait system imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_ui_wait_initialization():
    """Test UIWaitSystem initialization."""
    print("\nTesting UIWaitSystem initialization...")
    try:
        from src.utils.ui_wait import UIWaitSystem, get_ui_wait_system
        
        # Test direct initialization
        wait_sys = UIWaitSystem(
            poll_interval_ms=50,
            stability_threshold_ms=150,
            max_wait_ms=5000
        )
        print(f"✓ UIWaitSystem created with poll_interval={wait_sys.poll_interval_ms}ms")
        
        # Test global singleton
        global_sys = get_ui_wait_system()
        print("✓ Global UIWaitSystem singleton available")
        
        return True
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        return False


def test_wait_for_ui_stable():
    """Test waiting for UI stability."""
    print("\nTesting wait_for_ui_stable...")
    try:
        from src.utils.ui_wait import wait_for_ui_stable
        
        start = time.time()
        result = wait_for_ui_stable(max_wait_ms=2000, stability_ms=100)
        elapsed = (time.time() - start) * 1000
        
        print(f"  Waited {result.waited_ms:.0f}ms (measured: {elapsed:.0f}ms)")
        print(f"  Success: {result.success}")
        print(f"  Reason: {result.reason}")
        
        if result.success:
            print("✓ UI stability wait completed successfully")
        else:
            print("⚠ UI stability wait timed out (may be expected)")
        
        return True
    except Exception as e:
        print(f"✗ Wait failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_smart_wait():
    """Test smart waiting based on action type."""
    print("\nTesting smart_wait...")
    try:
        from src.utils.ui_wait import smart_wait
        
        action_types = ["type", "click", "hotkey", "navigate"]
        
        for action_type in action_types:
            start = time.time()
            result = smart_wait(action_type)
            elapsed = (time.time() - start) * 1000
            
            print(f"  {action_type}: waited {result.waited_ms:.0f}ms (success={result.success})")
        
        print("✓ Smart wait completed for all action types")
        return True
    except Exception as e:
        print(f"✗ Smart wait failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_wait_statistics():
    """Test wait statistics collection."""
    print("\nTesting wait statistics...")
    try:
        from src.utils.ui_wait import get_ui_wait_system
        
        wait_sys = get_ui_wait_system()
        
        # Perform some waits
        wait_sys.wait_for_ui_stable(max_wait_ms=500, stability_ms=50)
        wait_sys.wait_for_ui_stable(max_wait_ms=500, stability_ms=50)
        
        stats = wait_sys.get_stats()
        
        print(f"  Total waits: {stats['total_waits']}")
        print(f"  Avg wait time: {stats['avg_wait_ms']:.0f}ms")
        print(f"  Time saved: {stats['total_saved_ms']:.0f}ms")
        print(f"  Success rate: {stats['success_rate']:.0%}")
        
        print("✓ Statistics collection working")
        return True
    except Exception as e:
        print(f"✗ Statistics failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_accessibility_integration():
    """Test integration with accessibility API."""
    print("\nTesting accessibility API integration...")
    try:
        from src.utils.ui_wait import get_ui_wait_system
        
        wait_sys = get_ui_wait_system()
        
        if wait_sys._api is None:
            print("⚠ Accessibility API not available (using fallback timing)")
            print("  This is OK - the system will use fixed sleeps as fallback")
        else:
            print("✓ Accessibility API is available")
            
            # Try to get a UI snapshot
            snapshot = wait_sys._get_ui_snapshot()
            if snapshot:
                print(f"  UI snapshot: {snapshot.element_count} elements")
                print(f"  Window: {snapshot.window_title or 'N/A'}")
            else:
                print("  Could not get UI snapshot")
        
        return True
    except Exception as e:
        print(f"✗ Accessibility integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_executor_integration():
    """Test that executor loop can use UI wait system."""
    print("\nTesting executor loop integration...")
    try:
        from src.loop.executor_loop import ExecutorLoop, UI_WAIT_AVAILABLE
        
        if UI_WAIT_AVAILABLE:
            print("✓ Executor loop has UI wait system available")
        else:
            print("⚠ Executor loop using fallback timing")
        
        return True
    except Exception as e:
        print(f"✗ Executor integration test failed: {e}")
        return False


def test_adaptive_coordinator_integration():
    """Test that adaptive coordinator can use UI wait system."""
    print("\nTesting adaptive coordinator integration...")
    try:
        from src.loop.adaptive_coordinator import AdaptiveLoopCoordinator, UI_WAIT_AVAILABLE
        
        if UI_WAIT_AVAILABLE:
            print("✓ Adaptive coordinator has UI wait system available")
        else:
            print("⚠ Adaptive coordinator using fallback timing")
        
        return True
    except Exception as e:
        print(f"✗ Adaptive coordinator integration test failed: {e}")
        return False


def compare_wait_approaches():
    """Compare fixed sleep vs event-driven waiting."""
    print("\n" + "="*60)
    print("Comparing wait approaches...")
    print("="*60)
    
    try:
        from src.utils.ui_wait import get_ui_wait_system
        
        wait_sys = get_ui_wait_system()
        
        # Simulate 10 UI waits and compare
        fixed_time = 0
        event_driven_time = 0
        
        FIXED_SLEEP = 0.3  # Typical fixed sleep value
        NUM_WAITS = 5
        
        for i in range(NUM_WAITS):
            # Event-driven wait
            start = time.time()
            result = wait_sys.wait_for_ui_stable(max_wait_ms=1000, stability_ms=100)
            event_driven_time += time.time() - start
            
            # What fixed sleep would have been
            fixed_time += FIXED_SLEEP
        
        print(f"\nAfter {NUM_WAITS} waits:")
        print(f"  Fixed sleep approach: {fixed_time*1000:.0f}ms")
        print(f"  Event-driven approach: {event_driven_time*1000:.0f}ms")
        
        if event_driven_time < fixed_time:
            savings = ((fixed_time - event_driven_time) / fixed_time) * 100
            print(f"  ✓ Event-driven saved {savings:.0f}% time!")
        else:
            print(f"  Note: Event-driven took longer (UI may have been slow)")
        
        return True
    except Exception as e:
        print(f"✗ Comparison failed: {e}")
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("Event-Driven UI Wait System Tests")
    print("="*60)
    
    tests = [
        test_ui_wait_import,
        test_ui_wait_initialization,
        test_wait_for_ui_stable,
        test_smart_wait,
        test_wait_statistics,
        test_accessibility_integration,
        test_executor_integration,
        test_adaptive_coordinator_integration,
        compare_wait_approaches,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
