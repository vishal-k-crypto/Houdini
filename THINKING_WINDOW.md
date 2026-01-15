# 💭 Thinking Window - Real-time AI Reasoning Display

The Thinking Window is a beautiful terminal UI (TUI) that displays the real-time thinking process of the Houdini agent's AI components (Planner, Executor, and Supervisor).

## ✨ Features

- **Real-time Updates**: See what the AI is thinking as it plans and executes tasks
- **Component Tracking**: Separate visual styling for Planner, Executor, and Supervisor thoughts
- **Hacker Aesthetic**: Beautiful terminal dashboard with cyber/matrix color scheme
- **Rich Text Formatting**: Uses Textual + Rich for gorgeous terminal output
- **Interactive Controls**: Keyboard shortcuts for clearing, quitting, and more
- **Status Indicator**: Live status with colored indicators (🟢 Running, ✅ Complete, 🔴 Error)

## 🎨 Visual Components

### Component Colors (Cyber Aesthetic)
- **📋 Planner** - Matrix Green (#00ff88): Task analysis and batch generation
- **⚡ Executor** - Cyber Orange (#ff6b2b): Action execution and progress
- **👁  Supervisor** - Neon Purple (#bf5af2): Validation and monitoring
- **🤖 System** - Cyber Blue (#00d4ff): General system messages
- **✅ Success** - Matrix Green: Successful completions
- **❌ Error** - Red Alert (#ff3b30): Errors and failures
- **⚠️ Warning** - Warning Yellow (#ffd60a): Warnings and cautions

### Keyboard Shortcuts
- **q** - Quit the thinking window
- **c** - Clear all messages
- **d** - Toggle dark mode

## 🚀 Installation

The thinking window uses **Textual** (modern Python TUI framework):

```bash
pip install textual
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

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
- Built with **Textual** (modern Python TUI framework)
- Uses **Rich** for beautiful text formatting
- Runs in a **background thread** to avoid blocking agent execution
- Uses a **message queue** for thread-safe communication
- **Auto-scrolling** to latest messages
- **Message history limit** (200 messages) to prevent memory issues

### Graceful Fallback
If Textual is not installed, the window falls back to:
1. **Rich console output** - Beautiful formatted console messages
2. **Plain text** - If Rich is also unavailable

### Platform Support
- **macOS**: Full support with native terminal integration
- **Linux**: Full support with any modern terminal
- **Windows**: Full support with Windows Terminal or ConEmu

### Performance
- Minimal overhead on agent execution
- Non-blocking updates via queue
- Efficient message batching
- Auto-cleanup of old messages

## 🎨 Customization

### CSS Styling
The Textual app uses CSS for styling. Edit the `CSS` class variable in `src/ui/thinking_window.py`:

```python
CSS = """
Screen {
    background: #0a0a0a;
}

ThinkingLog {
    background: #0a0a0a;
    border: round #333;
    scrollbar-color: #00ff88;
}
"""
```

### Color Schemes
Modify the color mappings in `ThinkingMessage.to_rich_text()`:

```python
colors = {
    "planner": "#00ff88",      # Matrix green
    "executor": "#ff6b2b",      # Cyber orange
    "supervisor": "#bf5af2",    # Neon purple
    # Add more...
}
```

## 🐛 Troubleshooting

### Textual not available
If you see "⚠️ Textual not available - using console output":
```bash
pip install textual
```

### Window appears corrupted
- Ensure your terminal supports Unicode and 256+ colors
- Try iTerm2 (macOS), Windows Terminal (Windows), or Alacritty
- Check terminal size is at least 80x24

### Messages not updating
- Check that thinking window is enabled (no `--no-thinking-window` flag)
- Verify the component is catching exceptions (wrapped in try/except)
- Look for errors in terminal output

### Performance issues
- The thinking window runs in a background thread
- If too slow, increase the queue processing interval
- Consider using `--no-thinking-window` for performance-critical tasks

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

## 🔄 Migration from Tkinter

The thinking window was previously built with Tkinter. The new Textual version offers:

| Feature | Tkinter (Old) | Textual (New) |
|---------|---------------|---------------|
| Styling | Limited, platform-dependent | CSS-like, consistent |
| Look & Feel | Dated GUI | Modern terminal aesthetic |
| Installation | Complex (requires system packages) | Simple (`pip install textual`) |
| Thread Safety | Manual queue management | Built-in async support |
| Customization | Code changes required | CSS-based theming |
| Fallback | None | Rich console output |

## 🤝 Contributing

To enhance the thinking window:

1. Edit `src/ui/thinking_window.py`
2. Modify the CSS for visual changes
3. Test with `demo_thinking_window.py`
4. Update integration points in planner/executor/supervisor as needed

## 📄 License

Part of the Houdini Agent project.
