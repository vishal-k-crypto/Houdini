# Time Travel Debugging (Replay Mode)

## Overview

Houdini Agent now includes **Time Travel Debugging** - the ability to replay past task executions step-by-step. This feature lets you see exactly what happened during any execution:

- **Cursor positions and movements** (sampled every 50ms)
- **AI thinking at each millisecond** (planner, executor, supervisor)
- **Screenshots at checkpoints**
- **Action timing and success/failure states**
- **Phase transitions and supervisor interventions**

## Quick Start

```bash
# Enter interactive replay mode
python -m src.main --replay

# List all available sessions
python -m src.main --replay-list

# Replay a specific session
python -m src.main --replay-session <task_id>
```

## How It Works

### Automatic Recording

Every task execution is now automatically recorded:

1. **Session Start**: When a task begins, a new replay session is created
2. **Event Logging**: All events are timestamped in milliseconds:
   - Cursor movements (every 50ms when position changes by >5px)
   - Thinking window messages
   - Action starts and completions
   - Batch starts and completions
   - Phase transitions
   - Supervisor interventions
   - Screenshot checkpoints
3. **Session End**: When task completes (success or failure), session is saved

Sessions are stored in: `data/replay_sessions/`

### Event Types

| Event Type | Description |
|------------|-------------|
| `cursor_move` | Cursor position change |
| `cursor_click` | Mouse click |
| `thinking_planner` | Planner thinking message |
| `thinking_executor` | Executor thinking message |
| `thinking_supervisor` | Supervisor thinking message |
| `action_start` | Action execution begins |
| `action_complete` | Action completed successfully |
| `action_failed` | Action failed |
| `batch_start` | Batch execution begins |
| `batch_complete` | Batch completed |
| `phase_change` | Execution phase transition |
| `screenshot` | Screenshot checkpoint |
| `supervisor_intervention` | Supervisor took action |
| `key_press` | Single key press |
| `key_hotkey` | Keyboard shortcut |
| `text_type` | Text typing |

## Replay UI

### Textual TUI (Full Interface)

If you have `textual` installed, you get a beautiful full-screen interface:

```
╔═══════════════════════════════════════╗
║  📼 REPLAY: Open Safari and search... ║
╚═══════════════════════════════════════╝

Timeline: [0:05.2s] ████████████░░░░░░░░ [0:15.0s]

🖱️ CURSOR: (523, 412)

🧠 THINKING HISTORY
────────────────────────
📋 Analyzing task structure...
⚡ Executing: hotkey:command,space
👁️ Validated: Safari opened successfully

🏁 MARKERS
────────────────────────
● 0.0s   Batch 1: Open Safari
○ 2.5s   Batch 2: Navigate to search
○ 5.0s   📸 Screenshot checkpoint
```

### Controls

| Key | Action |
|-----|--------|
| `SPACE` | Play/Pause |
| `←` / `→` | Seek backward/forward (1 second) |
| `↑` / `↓` | Speed up/slow down playback |
| `n` | Jump to next marker |
| `p` | Jump to previous marker |
| `r` | Restart from beginning |
| `q` | Quit |

### Rich Console (Fallback)

If `textual` is not installed, you get a simpler Rich console interface with the same controls.

## API Usage

### ExecutionLogger

```python
from src.replay.execution_logger import get_execution_logger

# Get the global logger
logger = get_execution_logger()

# Start a session
logger.start_session(
    task_id="abc123",
    task_description="Open Safari and search for cats",
    metadata={"architecture": "adaptive"}
)

# Log events
logger.log_thinking("planner", "Analyzing task...", "info")
logger.log_action("hotkey:command,space", "blind")
logger.log_action_complete("hotkey:command,space", True, 150.0)
logger.log_cursor_click(523, 412)
logger.log_screenshot("/path/to/screenshot.png", "After batch 1")

# End session
logger.end_session(success=True)
```

### ReplayEngine

```python
from src.replay.replay_engine import ReplayEngine

engine = ReplayEngine()

# List all sessions
sessions = engine.list_sessions()
for s in sessions:
    print(f"{s['task_id']}: {s['task_description']}")

# Load a session
session = engine.load_session("abc123")

# Navigate
session.seek_to(5000)  # 5 seconds in
session.next_marker()  # Jump to next marker

# Get data at current position
cursor_x, cursor_y = session.get_cursor_at_position()
thinking = session.get_thinking_history(10)
event = session.get_current_event()

# Playback
engine.play(on_event=lambda e: print(f"Event: {e.event_type}"))
engine.pause()
engine.set_speed(2.0)  # 2x speed
```

### Importing Legacy Screenshots

If you have older executions with screenshot checkpoints but no full replay data, you can import them:

```python
from src.replay.replay_engine import ReplayEngine

engine = ReplayEngine()

# Import screenshots as a replay session
session = engine.import_from_screenshots("task_id_here")

# Now you can navigate through the screenshots
session.seek_to_marker(0)  # First screenshot
session.next_marker()       # Next screenshot
```

## Data Format

Sessions are saved as JSON files:

```json
{
  "task_id": "abc123",
  "task_description": "Open Safari and search for cats",
  "started_at": "2026-01-15T10:30:00.000000",
  "completed_at": "2026-01-15T10:30:15.500000",
  "success": true,
  "events": [
    {
      "event_type": "task_start",
      "timestamp_ms": 1736934600000,
      "relative_ms": 0,
      "data": {"task_id": "abc123", "task_description": "..."},
      "cursor_x": 500,
      "cursor_y": 300,
      "screenshot_path": null
    },
    {
      "event_type": "thinking_planner",
      "timestamp_ms": 1736934600100,
      "relative_ms": 100,
      "data": {"component": "planner", "message": "Analyzing...", "level": "info"},
      "cursor_x": 500,
      "cursor_y": 300,
      "screenshot_path": null
    }
  ],
  "metadata": {
    "architecture": "adaptive_coordinator"
  }
}
```

## Timeline Markers

Markers are automatically generated for important events:

- **Batch starts** (blue) - Beginning of each batch
- **Errors** (red) - Failed actions
- **Screenshots** (yellow) - Checkpoint screenshots
- **Supervisor interventions** (purple) - When supervisor took action
- **Phase changes** (green) - Execution phase transitions

## Best Practices

### Debugging Failed Tasks

1. Run `python -m src.main --replay`
2. Select the failed session (marked with ✗)
3. Jump to error markers with `n` key
4. Review thinking history and cursor position
5. Check screenshot at that checkpoint

### Performance Analysis

1. Load a successful session
2. Play at 2x speed to get overview
3. Use markers to jump between batches
4. Note action durations in the event log

### Comparing Executions

Run the same task multiple times, then replay each session to compare:
- Which approach was faster?
- Where did the cursor go differently?
- What thinking led to different actions?

## Configuration

### Cursor Sampling Rate

Default: 50ms (20 samples/second)

```python
logger = get_execution_logger()
logger.cursor_sample_rate_ms = 100  # Reduce to 10 samples/second
```

### Session Storage Location

Default: `data/replay_sessions/`

```python
logger = get_execution_logger()
logger.sessions_dir = Path("/custom/path/sessions")
```

## Troubleshooting

### "No replay sessions found"

Run some tasks first! Sessions are recorded automatically during execution.

### Cursor positions show (?, ?)

PyAutoGUI may not have permission to read cursor position. Grant accessibility permissions to your terminal.

### Textual UI not loading

Install Textual: `pip install textual`

### Large session files

Sessions with many cursor movements can get large. Consider:
- Increasing `cursor_sample_rate_ms`
- Filtering events during replay with `session.event_filter`

## Architecture Integration

The replay system integrates with all architectures:

- **Adaptive Coordinator** - Full event logging including phase changes
- **Executor Loop** - Action and batch logging
- **LangGraph Coordinator** - State machine transitions
- **Thinking Window** - All thinking messages are automatically captured
