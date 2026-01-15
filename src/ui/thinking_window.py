"""
Floating thinking window - displays real-time AI reasoning process.
Built with Textual for a modern hacker-style terminal UI.

Features:
- Beautiful terminal dashboard with cyber aesthetic
- Real-time updates from planner, executor, supervisor
- Always runs in its own terminal window
- Clean, modern design with rich text formatting
"""

import threading
import asyncio
from queue import Queue, Empty
from datetime import datetime
from typing import Optional, Dict, List
import time
import os
import sys

# Try to import textual - fall back gracefully
try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
    from textual.widgets import Header, Footer, Static, Label, RichLog, Button
    from textual.reactive import reactive
    from textual import events
    from rich.text import Text
    from rich.panel import Panel
    from rich.style import Style
    from rich.console import Console
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


# Fallback to rich console output if textual not available
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class ThinkingMessage:
    """A single thinking message with metadata."""
    
    def __init__(self, component: str, message: str, level: str = "info"):
        self.component = component
        self.message = message
        self.level = level
        self.timestamp = datetime.now().strftime("%H:%M:%S")
    
    def to_rich_text(self) -> Text:
        """Convert to rich text for display."""
        # Color mapping for hacker aesthetic
        colors = {
            "planner": "#00ff88",      # Matrix green
            "executor": "#ff6b2b",      # Cyber orange
            "supervisor": "#bf5af2",    # Neon purple
            "system": "#00d4ff",        # Cyber blue
            "thinking": "#00d4ff",      # Cyber blue
            "success": "#00ff88",       # Matrix green
            "error": "#ff3b30",         # Red alert
            "warning": "#ffd60a",       # Warning yellow
            "info": "#8e8e93",          # Gray
        }
        
        emojis = {
            "planner": "📋",
            "executor": "⚡",
            "supervisor": "👁 ",
            "system": "🤖",
        }
        
        text = Text()
        
        # Timestamp
        text.append(f"[{self.timestamp}] ", style="dim cyan")
        
        # Component badge
        emoji = emojis.get(self.component.lower(), "💭")
        component_color = colors.get(self.component.lower(), "#8e8e93")
        text.append(f"{emoji} {self.component.upper()}", style=f"bold {component_color}")
        text.append(" → ", style="dim white")
        
        # Message with level styling
        level_color = colors.get(self.level, "#d4d4d4")
        text.append(self.message, style=level_color)
        
        return text


if TEXTUAL_AVAILABLE:
    
    class StatusBar(Static):
        """A status bar showing current agent state."""
        
        status_text = reactive("● Initializing...")
        
        def render(self) -> Text:
            text = Text()
            # Parse status and add appropriate styling
            status = self.status_text
            
            if "running" in status.lower() or "executing" in status.lower():
                text.append("🟢 ", style="green")
            elif "error" in status.lower() or "failed" in status.lower():
                text.append("🔴 ", style="red")
            elif "complete" in status.lower():
                text.append("✅ ", style="green")
            elif "thinking" in status.lower() or "planning" in status.lower():
                text.append("🧠 ", style="cyan")
            else:
                text.append("● ", style="cyan")
            
            text.append(status, style="bold")
            return text
        
        def update_status(self, status: str):
            self.status_text = status
    
    
    class ThinkingLog(RichLog):
        """A scrollable log for thinking messages."""
        
        def __init__(self, *args, **kwargs):
            super().__init__(*args, highlight=True, markup=True, **kwargs)
            self.messages: List[ThinkingMessage] = []
        
        def add_message(self, msg: ThinkingMessage):
            """Add a thinking message to the log."""
            self.messages.append(msg)
            self.write(msg.to_rich_text())
            
            # Keep only last 200 messages
            if len(self.messages) > 200:
                self.messages.pop(0)
    
    
    class HoudiniThinkingApp(App):
        """
        Houdini Thinking Window - A beautiful terminal UI for AI reasoning.
        
        Displays real-time thinking from Planner, Executor, and Supervisor.
        """
        
        CSS = """
        Screen {
            background: #0a0a0a;
        }
        
        #header-container {
            dock: top;
            height: 3;
            background: #1a1a2e;
            border-bottom: solid #00ff88;
        }
        
        #title {
            width: 100%;
            height: 3;
            content-align: center middle;
            text-style: bold;
            color: #00ff88;
            background: #1a1a2e;
        }
        
        #status-container {
            dock: bottom;
            height: 3;
            background: #1a1a2e;
            border-top: solid #333;
            padding: 0 2;
        }
        
        StatusBar {
            width: 100%;
            height: 3;
            content-align: left middle;
            color: #00d4ff;
        }
        
        #log-container {
            width: 100%;
            height: 100%;
            background: #0a0a0a;
            padding: 1;
        }
        
        ThinkingLog {
            background: #0a0a0a;
            border: round #333;
            scrollbar-background: #1a1a2e;
            scrollbar-color: #00ff88;
            scrollbar-color-hover: #00ffaa;
            scrollbar-color-active: #00ffcc;
        }
        
        #controls {
            dock: top;
            height: 1;
            background: #1a1a2e;
            padding: 0 1;
        }
        
        Button {
            min-width: 8;
            height: 1;
            background: #333;
            color: #00ff88;
            border: none;
        }
        
        Button:hover {
            background: #00ff88;
            color: #0a0a0a;
        }
        
        .ascii-art {
            color: #00ff88;
            text-style: bold;
        }
        """
        
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("c", "clear", "Clear"),
            ("d", "toggle_dark", "Dark Mode"),
        ]
        
        def __init__(self, message_queue: Queue, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.message_queue = message_queue
            self.log_widget: Optional[ThinkingLog] = None
            self.status_widget: Optional[StatusBar] = None
        
        def compose(self) -> ComposeResult:
            """Create the UI layout."""
            # Header with ASCII art title
            yield Container(
                Static(
                    "╔═══════════════════════════════════════╗\n"
                    "║  🤖 HOUDINI • THINKING PROCESS        ║\n"
                    "╚═══════════════════════════════════════╝",
                    id="title",
                    classes="ascii-art"
                ),
                id="header-container"
            )
            
            # Main log area
            yield Container(
                ThinkingLog(id="thinking-log"),
                id="log-container"
            )
            
            # Status bar
            yield Container(
                StatusBar(id="status-bar"),
                id="status-container"
            )
            
            # Footer with keybindings
            yield Footer()
        
        def on_mount(self) -> None:
            """Called when app is mounted."""
            self.log_widget = self.query_one("#thinking-log", ThinkingLog)
            self.status_widget = self.query_one("#status-bar", StatusBar)
            
            # Start the message processing loop - 50ms for faster updates
            self.set_interval(0.05, self.process_messages)
            
            # Initial message
            self.log_widget.add_message(
                ThinkingMessage("system", "Houdini thinking window initialized", "info")
            )
        
        def process_messages(self) -> None:
            """Process messages from the queue."""
            try:
                while True:
                    msg = self.message_queue.get_nowait()
                    
                    if msg.get("action") == "clear":
                        if self.log_widget:
                            self.log_widget.clear()
                            self.log_widget.messages.clear()
                    elif msg.get("action") == "status":
                        if self.status_widget:
                            self.status_widget.update_status(msg.get("status", "Idle"))
                    elif msg.get("action") == "quit":
                        self.exit()
                    else:
                        # Regular thinking message
                        if self.log_widget:
                            thinking_msg = ThinkingMessage(
                                component=msg.get("component", "system"),
                                message=msg.get("message", ""),
                                level=msg.get("level", "info")
                            )
                            self.log_widget.add_message(thinking_msg)
            except Empty:
                pass
        
        def action_clear(self) -> None:
            """Clear the log."""
            if self.log_widget:
                self.log_widget.clear()
                self.log_widget.messages.clear()
        
        def action_toggle_dark(self) -> None:
            """Toggle dark mode."""
            self.dark = not self.dark


class ThinkingWindow:
    """
    A thinking window that displays the AI's reasoning process.
    
    Uses Textual for a beautiful terminal UI with hacker aesthetic.
    Falls back to Rich console output if Textual unavailable.
    """
    
    def __init__(self, title: str = "Houdini Thinking", width: int = 80, height: int = 24):
        """
        Initialize the thinking window.
        
        Args:
            title: Window title
            width: Unused (Textual uses full terminal)
            height: Unused (Textual uses full terminal)
        """
        self.title = title
        self.message_queue = Queue()
        self.running = False
        self.window_thread: Optional[threading.Thread] = None
        self.app: Optional['HoudiniThinkingApp'] = None
        self.disabled = not TEXTUAL_AVAILABLE
        self.messages: List[Dict] = []
        
        # Rich console fallback
        self.console = Console() if RICH_AVAILABLE else None
    
    def start(self):
        """Start the window in a background thread."""
        if self.disabled:
            if RICH_AVAILABLE:
                self.console.print(
                    Panel(
                        "[cyan]Textual not available - using console output[/cyan]\n"
                        "[dim]Install with: pip install textual[/dim]",
                        title="⚠️  Thinking Window",
                        border_style="yellow"
                    )
                )
            else:
                print("⚠️  Thinking window disabled (textual not installed)")
                print("   Install with: pip install textual")
            return
        
        if self.running:
            return
        
        self.running = True
        
        # Run Textual app in a separate thread
        self.window_thread = threading.Thread(target=self._run_window, daemon=True)
        self.window_thread.start()
        
        # Wait for window to initialize
        time.sleep(0.5)
    
    def _run_window(self):
        """Run the Textual app."""
        if TEXTUAL_AVAILABLE:
            import signal
            import threading
            
            # Monkey-patch signal.signal to ignore ALL signal registrations in threads
            # This is needed because Textual's driver tries to set up signal handlers
            # (SIGTSTP, SIGCONT, SIGTTOU, etc.) but we're running in a background thread
            # where signal handlers are not allowed
            original_signal = signal.signal
            
            def thread_safe_signal(signum, handler):
                """Signal handler that ignores signal registration in threads."""
                # Check if we're in the main thread
                if threading.current_thread() != threading.main_thread():
                    # Silently ignore - signal handlers only work in main thread
                    return signal.SIG_DFL
                return original_signal(signum, handler)
            
            signal.signal = thread_safe_signal
            
            try:
                self.app = HoudiniThinkingApp(self.message_queue)
                self.app.run()
            finally:
                # Restore original signal function
                signal.signal = original_signal
    
    def stop(self):
        """Stop the window and cleanup."""
        self.running = False
        if self.app:
            self.message_queue.put({"action": "quit"})
    
    def add_thinking(self, component: str, message: str, level: str = "info"):
        """
        Add a thinking message to the window.
        
        Args:
            component: Source component (planner, executor, supervisor)
            message: Thinking message text
            level: Message level (info, success, warning, error, thinking)
        """
        msg = {
            "component": component,
            "message": message,
            "level": level,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        
        self.messages.append(msg)
        
        # Log to replay system for time travel debugging
        try:
            from ..replay.execution_logger import get_execution_logger
            logger = get_execution_logger()
            if logger.current_session:
                logger.log_thinking(component, message, level)
        except Exception:
            pass  # Replay system not available or not recording
        
        if self.disabled:
            # Fallback to console output
            self._console_output(msg)
        else:
            self.message_queue.put(msg)
    
    def _console_output(self, msg: Dict):
        """Output to console when Textual unavailable."""
        if not RICH_AVAILABLE:
            print(f"[{msg['timestamp']}] {msg['component'].upper()}: {msg['message']}")
            return
        
        colors = {
            "planner": "green",
            "executor": "yellow",
            "supervisor": "magenta",
            "system": "cyan",
            "success": "green",
            "error": "red",
            "warning": "yellow",
        }
        
        emojis = {
            "planner": "📋",
            "executor": "⚡",
            "supervisor": "👁 ",
            "system": "🤖",
        }
        
        emoji = emojis.get(msg["component"].lower(), "💭")
        color = colors.get(msg["component"].lower(), "white")
        
        self.console.print(
            f"[dim cyan][{msg['timestamp']}][/dim cyan] "
            f"{emoji} [{color} bold]{msg['component'].upper()}[/{color} bold] → "
            f"[{colors.get(msg['level'], 'white')}]{msg['message']}[/{colors.get(msg['level'], 'white')}]"
        )
    
    def clear(self):
        """Clear all messages."""
        self.messages.clear()
        if not self.disabled:
            self.message_queue.put({"action": "clear"})
    
    def set_status(self, status: str):
        """Update the status bar."""
        if not self.disabled:
            self.message_queue.put({
                "action": "status",
                "status": status
            })
        elif RICH_AVAILABLE:
            color = "green" if "complete" in status.lower() else "cyan"
            self.console.print(f"[{color} bold]Status: {status}[/{color} bold]")


# Global singleton instance
_thinking_window: Optional[ThinkingWindow] = None


def get_thinking_window() -> ThinkingWindow:
    """Get or create the global thinking window instance."""
    global _thinking_window
    if _thinking_window is None:
        _thinking_window = ThinkingWindow()
    return _thinking_window


def start_thinking_window():
    """Start the thinking window."""
    window = get_thinking_window()
    window.start()
    return window


def stop_thinking_window():
    """Stop the thinking window."""
    global _thinking_window
    if _thinking_window:
        _thinking_window.stop()
        _thinking_window = None


# Convenience functions
def show_thinking(component: str, message: str, level: str = "thinking"):
    """Add a thinking message to the window."""
    window = get_thinking_window()
    if window:
        window.add_thinking(component, message, level)


def show_planner_thinking(message: str):
    """Show planner thinking."""
    show_thinking("planner", message, "thinking")


def show_executor_thinking(message: str):
    """Show executor thinking."""
    show_thinking("executor", message, "thinking")


def show_supervisor_thinking(message: str):
    """Show supervisor thinking."""
    show_thinking("supervisor", message, "thinking")


def set_window_status(status: str):
    """Update window status."""
    window = get_thinking_window()
    if window:
        window.set_status(status)


if __name__ == "__main__":
    # Test the window
    print("🚀 Starting Houdini Thinking Window (Textual UI)")
    print("=" * 50)
    
    if not TEXTUAL_AVAILABLE:
        print("❌ Textual not available")
        print("   Install with: pip install textual")
        print("\n   Falling back to Rich console output...\n")
    
    window = start_thinking_window()
    
    import time
    
    # Simulate some thinking
    time.sleep(1)
    show_planner_thinking("Analyzing task: 'Open Spotify and play jazz music'")
    time.sleep(1)
    show_planner_thinking("Breaking down into 3 batches: 1) Launch app, 2) Navigate, 3) Execute action")
    time.sleep(1)
    show_executor_thinking("Executing batch 1: Launching Spotify...")
    time.sleep(1)
    show_executor_thinking("Using keyboard shortcut: cmd+space")
    time.sleep(1)
    show_supervisor_thinking("Validating execution... ✓")
    time.sleep(1)
    show_thinking("system", "Task completed successfully!", "success")
    
    set_window_status("Completed")
    
    if TEXTUAL_AVAILABLE:
        # Keep window open for Textual
        print("\n💡 Press 'q' in the Textual window to quit")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    
    stop_thinking_window()
