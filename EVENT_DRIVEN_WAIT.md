# Event-Driven UI Wait System

## Overview

The Houdini Agent now uses an **event-driven observation model** instead of fixed `time.sleep()` calls. The executor monitors the macOS Accessibility Tree (using `AXUIElement`) and only proceeds once the UI "settles" or a specific element appears.

## Benefits

1. **Faster Execution**: No over-sleeping when UI is responsive
2. **More Reliable**: No under-sleeping when UI is slow
3. **Adaptive**: Automatically adjusts to system performance
4. **Resource-Aware**: Uses accessibility API for intelligent waiting

## How It Works

### Traditional Approach (Fixed Sleep)
```python
# Old way: Fixed sleep regardless of UI state
pyautogui.click(x, y)
time.sleep(0.5)  # Always wait 500ms, even if UI is ready in 50ms
```

### Event-Driven Approach (New)
```python
# New way: Wait until UI stabilizes
pyautogui.click(x, y)
wait_for_ui_stable()  # Waits 50-500ms depending on actual UI state
```

## Architecture

### UIWaitSystem Class

```
┌─────────────────────────────────────────────────────────────┐
│                     UIWaitSystem                             │
├─────────────────────────────────────────────────────────────┤
│ poll_interval_ms: 50      # How often to check UI           │
│ stability_threshold_ms: 150  # How long UI must be stable   │
│ max_wait_ms: 10000        # Maximum wait time                │
├─────────────────────────────────────────────────────────────┤
│ wait_for_ui_stable()      # Wait for UI tree to stop changing│
│ wait_for_element()        # Wait for element to appear       │
│ wait_for_element_gone()   # Wait for element to disappear    │
│ wait_for_window_ready()   # Wait for window to be interactive│
│ smart_wait_after_action() # Auto-adjust based on action type │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     AccessibilityAPI          │
              │  (AXUIElement monitoring)     │
              │                               │
              │  - Gets UI element tree       │
              │  - Tracks focused element     │
              │  - Detects UI changes         │
              └───────────────────────────────┘
```

### UI Stability Detection

The system creates "snapshots" of the UI state by:
1. Getting the accessibility tree from the frontmost app
2. Counting total elements
3. Computing a hash of the tree structure
4. Comparing snapshots over time

When two consecutive snapshots match for `stability_threshold_ms`, the UI is considered "stable".

## Wait Conditions

### UI_STABLE
Wait for the accessibility tree to stop changing.
```python
from src.utils.ui_wait import wait_for_ui_stable

result = wait_for_ui_stable(max_wait_ms=2000, stability_ms=150)
if result.success:
    print(f"UI stable after {result.waited_ms}ms")
```

### ELEMENT_PRESENT
Wait for a specific element to appear.
```python
from src.utils.ui_wait import wait_for_element

# Wait for a button with text "Submit"
result = wait_for_element(text="Submit", timeout_ms=5000)
if result.success:
    print(f"Found element: {result.element}")
```

### ELEMENT_ABSENT
Wait for an element to disappear (e.g., loading spinner).
```python
from src.utils.ui_wait import wait_for_element_gone

result = wait_for_element_gone(text="Loading...", timeout_ms=10000)
```

### WINDOW_READY
Wait for a window to be fully interactive.
```python
from src.utils.ui_wait import wait_for_window_ready

result = wait_for_window_ready(app_name="Safari", timeout_ms=5000)
```

## Smart Wait

The `smart_wait_after_action()` method automatically adjusts timing based on what action was just performed:

| Action Type | Max Wait | Stability Threshold |
|------------|----------|---------------------|
| `type`     | 200ms    | 50ms                |
| `click`    | 2000ms   | 150ms               |
| `hotkey`   | 1500ms   | 200ms               |
| `navigate` | 5000ms   | 300ms               |

## New Action Commands

The executor now supports two new action types:

### wait_for:element_text
Wait for a specific element to appear:
```
wait_for:Search Results
```

### wait_stable
Wait for UI to stabilize:
```
wait_stable
```

## Integration

The event-driven wait system is integrated into:

1. **ExecutorLoop** (`src/loop/executor_loop.py`)
2. **AdaptiveLoopCoordinator** (`src/loop/adaptive_coordinator.py`)
3. **LangGraphCoordinator** (`src/loop/langgraph_coordinator.py`)

All coordinators automatically use event-driven waiting when the accessibility API is available, with fallback to fixed sleeps if not.

## Statistics

The system tracks wait statistics:
```python
from src.utils.ui_wait import get_ui_wait_system

stats = get_ui_wait_system().get_stats()
print(f"Total waits: {stats['total_waits']}")
print(f"Average wait: {stats['avg_wait_ms']}ms")
print(f"Time saved: {stats['total_saved_ms']}ms")
print(f"Success rate: {stats['success_rate']:.0%}")
```

## Fallback Behavior

If PyObjC or the accessibility API is not available, the system falls back to sensible fixed sleeps:
- Type actions: 50ms
- Click actions: 150ms
- Batch completion: 300ms
- Vision actions: 300ms

## Requirements

For full functionality:
```bash
pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ApplicationServices
```

## Testing

Run the test script:
```bash
python test_ui_wait.py
```

This will test:
- Import functionality
- Initialization
- UI stability detection
- Smart wait behavior
- Statistics collection
- Accessibility API integration
- Executor/coordinator integration
- Comparison with fixed sleep approach
