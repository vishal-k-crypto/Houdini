# 💭 Thinking Window - Real-time AI Reasoning Display

The Thinking Window is a floating, always-on-top window that displays the real-time thinking process of the Houdini agent's AI components (Planner, Executor, and Supervisor).

## ✨ Features

- **Real-time Updates**: See what the AI is thinking as it plans and executes tasks
- **Component Tracking**: Separate visual styling for Planner, Executor, and Supervisor thoughts
- **macOS-style Design**: Clean, modern interface inspired by ChatGPT Mac app
- **Always on Top**: Window stays visible above other applications
- **Draggable**: Click and drag the header to reposition
- **Collapsible**: Minimize to a compact header bar when not needed
- **Status Indicator**: Live status with colored indicators (🟢 Running, ✅ Complete, 🔴 Error)

## 🎨 Visual Components

### Component Colors
- **🧠 Thinking** - Light Blue: General reasoning and analysis
- **📋 Planner** - Teal: Task analysis and batch generation
- **⚡ Executor** - Orange: Action execution and progress
- **👁 Supervisor** - Purple: Validation and monitoring
- **✅ Success** - Green: Successful completions
- **❌ Error** - Red: Errors and failures
- **⚠️ Warning** - Yellow: Warnings and cautions

### Window Controls
- **−/+** button: Collapse/expand window
- **🗑** button: Clear all messages
- **Header**: Drag to move window
- **Status bar**: Shows current agent state

## 🚀 Usage

### Automatic (Default)
The thinking window starts automatically when running tasks in loop mode:

```bash
python -m src.main --task "open safari and search python" --loop
```

### Disable Thinking Window
If you prefer to run without the thinking window:

```bash
python -m src.main --task "your task" --loop --no-thinking-window
```

### Demo Mode
Test the thinking window with a simulated task:

```bash
python demo_thinking_window.py
```

## 🔧 Programmatic Usage

### Basic Usage

```python
from src.ui.thinking_window import (
    start_thinking_window,
    show_planner_thinking,
    show_executor_thinking,
    show_supervisor_thinking,
    set_window_status
)

# Start the window
start_thinking_window()

# Add thinking messages
show_planner_thinking("Analyzing task structure...")
show_executor_thinking("Executing action: open Safari")
show_supervisor_thinking("Validating execution...")

# Update status
set_window_status("Executing...")
```

### Advanced Usage

```python
from src.ui.thinking_window import ThinkingWindow, get_thinking_window

# Get the window instance
window = get_thinking_window()

# Start it
window.start()

# Add custom messages with different levels
window.add_thinking(
    component="planner",
    message="Breaking task into 3 batches",
    level="thinking"
)

window.add_thinking(
    component="system",
    message="Task completed!",
    level="success"
)

# Clear all messages
window.clear()

# Update status
window.set_status("Running task...")
```

## 📝 Message Levels

- **thinking**: AI reasoning and analysis (default for component thinking)
- **info**: General information
- **success**: Successful operations
- **warning**: Warnings and potential issues
- **error**: Errors and failures

## 🎯 Integration Points

The thinking window is automatically integrated with:

1. **Loop Coordinator** - Shows high-level task flow
   - Task planning phase
   - Execution start/completion
   - Final results

2. **Planner** - Shows planning decisions
   - Task analysis
   - Pattern matching
   - Batch generation
   - Cache/pattern usage

3. **Executor Loop** - Shows execution progress
   - Batch execution start
   - Individual action completion
   - Vision action handling

4. **Supervisor Loop** - Shows validation
   - Monitoring start
   - Action validation results
   - Intervention decisions

## 🛠 Technical Details

### Architecture
- Built with **Tkinter** (included with Python, no extra dependencies)
- Runs in a **background thread** to avoid blocking agent execution
- Uses a **message queue** for thread-safe communication
- **Auto-scrolling** to latest messages
- **Message history limit** (100 messages) to prevent memory issues

### Platform Support
- **macOS**: Full support with native styling
- **Linux**: Supported with GTK/TK
- **Windows**: Supported (may need minor styling adjustments)

### Performance
- Minimal overhead on agent execution
- Non-blocking updates via queue
- Efficient message batching
- Auto-cleanup of old messages

## 🎨 Customization

### Window Size
Edit the window initialization in your code:

```python
window = ThinkingWindow(
    title="My Agent Thinking",
    width=500,  # pixels
    height=700  # pixels
)
```

### Colors and Styling
Modify the tag configurations in `src/ui/thinking_window.py`:

```python
self.text_area.tag_config("thinking", foreground="#9cdcfe")
self.text_area.tag_config("planner", foreground="#4ec9b0")
# ... etc
```

## 🐛 Troubleshooting

### Tkinter not available
If you see "⚠️ Tkinter not available - thinking window disabled":
- Tkinter is required but not installed
- See [TKINTER_INSTALL.md](TKINTER_INSTALL.md) for installation instructions
- Quick fix (macOS): `brew install python-tk@3.14`
- The agent will still work, just without the thinking window

### Window doesn't appear
- Ensure Tkinter is installed: `python3 -m tkinter` (should show a test window)
- Check if running in headless environment
- Try running the demo: `python demo_thinking_window.py`

### Window appears behind other windows
- This is expected behavior when other apps have focus
- Click the window to bring it forward
- The window is set to "always on top" within VS Code/terminal context

### Messages not updating
- Check that thinking window is enabled (no `--no-thinking-window` flag)
- Verify the component is catching exceptions (wrapped in try/except)
- Look for errors in terminal output

## 📚 Examples

### Example 1: Simple Task
```bash
python -m src.main --task "open calculator" --loop
```
Watch the window show:
1. Planner analyzing the task
2. Executor opening the app
3. Supervisor validating success

### Example 2: Complex Task
```bash
python -m src.main --task "search for python tutorials on safari" --loop
```
Watch the window show:
1. Planner breaking into batches
2. Executor running blind actions (keyboard shortcuts)
3. Executor requesting vision action (clicking search result)
4. Supervisor validating each step

## 🤝 Contributing

To enhance the thinking window:

1. Edit `src/ui/thinking_window.py`
2. Add new message types or styling in the `_create_ui` method
3. Test with `demo_thinking_window.py`
4. Update integration points in planner/executor/supervisor as needed

## 📄 License

Part of the Houdini Agent project.
