# Screenshot Checkpoints

## Overview
Screenshot checkpoints capture the screen state at key moments during task execution, enabling visual debugging and recovery from unexpected situations.

## When Screenshots Are Captured

### 1. **After Each Batch Completion**
- Captures screen state after every batch of actions completes
- Stored with checkpoint ID and batch number
- Location: `data/screenshots/<task_id>/YYYYMMDD_HHMMSS_checkpoint_<id>.png`

### 2. **On Action Failures**
- Automatically captures screenshot when any action fails
- Helps debug why the action didn't work
- Location: `data/screenshots/<task_id>/YYYYMMDD_HHMMSS_action_<type>_<batch>_<action>.png`

### 3. **During Vision Action Failures**
- Captures screen when vision-based clicks fail
- Critical for understanding element targeting issues
- Location: Same as action failures

### 4. **When Stuck is Detected**
- Recovery handler captures screenshot when agent is stuck
- Includes full UI context for LLM-guided recovery
- Location: `data/screenshots/<task_id>/YYYYMMDD_HHMMSS_stuck_condition.png`

## Directory Structure

```
data/
  screenshots/
    <task_id>/
      20260113_215400_checkpoint_a1b2c3d4.png
      20260113_215405_action_blind_1_2.png
      20260113_215410_stuck_condition.png
      ...
```

## Accessing Screenshots

### In Code

```python
from src.loop import LoopState

# Get checkpoint with screenshot
state = LoopState(...)
checkpoint = state.save_checkpoint("After opening Safari", capture_screenshot=True)
print(f"Screenshot: {checkpoint.screenshot_path}")

# Get action record with screenshot
for action in state.action_history:
    if action.screenshot_path:
        print(f"Action: {action.action}")
        print(f"Screenshot: {action.screenshot_path}")
```

### Viewing Recent Screenshots

```bash
# List all screenshots for latest task
ls -lht data/screenshots/*/

# View latest screenshot (macOS)
open $(ls -t data/screenshots/*/*.png | head -1)
```

## Benefits

1. **Visual Debugging**: See exactly what the agent saw when things went wrong
2. **Recovery Context**: LLM can analyze screenshots to determine best recovery action
3. **Pattern Learning**: Screenshots help identify UI patterns for future optimizations
4. **Audit Trail**: Complete visual record of agent's actions

## Performance Impact

- Screenshot capture: ~30-50ms per screenshot
- Disk usage: ~500KB-2MB per screenshot
- Automatic cleanup: Screenshots older than 7 days are removed (TODO)

## Configuration

Screenshots are enabled by default. To disable:

```python
# In executor_loop.py
checkpoint = state.save_checkpoint(
    description="After batch",
    capture_screenshot=False  # Disable screenshot
)

# For actions
state.record_action(
    action_type="blind",
    action=action,
    success=True,
    capture_screenshot=False  # Disable screenshot
)
```

## Troubleshooting

### Screenshots Not Being Saved
- Ensure `screencapture` command is available (macOS only)
- Check permissions for screen recording
- Verify `data/screenshots` directory exists

### Too Many Screenshots
- Screenshots accumulate over time
- Clean up old screenshots manually:
  ```bash
  find data/screenshots -name "*.png" -mtime +7 -delete
  ```

## Future Enhancements

- [ ] Automatic cleanup of old screenshots
- [ ] Screenshot compression
- [ ] Optional screenshot upload to cloud storage
- [ ] Video recording of entire task execution
- [ ] Screenshot comparison for detecting UI changes
