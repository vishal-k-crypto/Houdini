"""
Floating thinking window - displays real-time AI reasoning process.
Similar to ChatGPT Mac app's floating window interface.
"""

import threading
from queue import Queue, Empty
from datetime import datetime
from typing import Optional, Dict, List
import time

# Try to import tkinter - may not be available
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    tk = None
    ttk = None
    scrolledtext = None


class ThinkingWindow:
    """
    A floating, always-on-top window that displays the AI's thinking process.
    
    Features:
    - Always on top, semi-transparent
    - Real-time updates from planner, executor, supervisor
    - Collapsible/expandable
    - Draggable
    - Clean, modern macOS-style design
    """
    
    def __init__(self, title: str = "Houdini Thinking", width: int = 400, height: int = 600):
        """
        Initialize the thinking window.
        
        Args:
            title: Window title
            width: Window width in pixels
            height: Window height in pixels
        """
        if not TKINTER_AVAILABLE:
            print("⚠️  Tkinter not available - thinking window disabled")
            print("   To enable: brew install python-tk@3.14 (or your Python version)")
            self.disabled = True
            return
        
        self.disabled = False
        self.width = width
        self.height = height
        self.title = title
        
        # Threading
        self.message_queue = Queue()
        self.running = False
        self.window_thread: Optional[threading.Thread] = None
        
        # Window reference (created in UI thread)
        self.root: Optional[tk.Tk] = None
        self.text_area: Optional[scrolledtext.ScrolledText] = None
        self.status_label: Optional[tk.Label] = None
        
        # State
        self.is_collapsed = False
        self.messages: List[Dict] = []
        
    def start(self):
        """Start the window in a background thread."""
        if hasattr(self, 'disabled') and self.disabled:
            return
        
        if self.running:
            return
        
        self.running = True
        self.window_thread = threading.Thread(target=self._run_window, daemon=True)
        self.window_thread.start()
        
        # Wait for window to initialize
        time.sleep(0.5)
    
    def stop(self):
        """Stop the window and cleanup."""
        if hasattr(self, 'disabled') and self.disabled:
            return
        
        self.running = False
        if self.root:
            try:
                self.root.quit()
            except:
                pass
    
    def add_thinking(self, component: str, message: str, level: str = "info"):
        """
        Add a thinking message to the window.
        
        Args:
            component: Source component (planner, executor, supervisor)
            message: Thinking message text
            level: Message level (info, success, warning, error, thinking)
        """
        if hasattr(self, 'disabled') and self.disabled:
            return
        
        self.message_queue.put({
            "component": component,
            "message": message,
            "level": level,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
    
    def clear(self):
        """Clear all messages."""
        if hasattr(self, 'disabled') and self.disabled:
            return
        
        self.message_queue.put({"action": "clear"})
    
    def set_status(self, status: str):
        """Update the status bar."""
        if hasattr(self, 'disabled') and self.disabled:
            return
        
        self.message_queue.put({
            "action": "status",
            "status": status
        })
    
    def _run_window(self):
        """Run the Tkinter window (called in background thread)."""
        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.geometry(f"{self.width}x{self.height}+50+50")  # Position on screen
        
        # Window style
        self.root.attributes('-topmost', True)  # Always on top
        self.root.attributes('-alpha', 0.95)    # Slightly transparent
        
        # macOS specific styling
        try:
            self.root.configure(bg='#1e1e1e')
        except:
            pass
        
        # Create UI
        self._create_ui()
        
        # Start update loop
        self.root.after(100, self._process_queue)
        
        # Run
        self.root.mainloop()
    
    def _create_ui(self):
        """Create the UI components."""
        # Header frame
        header_frame = tk.Frame(self.root, bg='#2d2d2d', height=40)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)
        
        # Title label
        title_label = tk.Label(
            header_frame,
            text="🤖 Thinking Process",
            font=("SF Pro", 13, "bold"),
            bg='#2d2d2d',
            fg='#ffffff',
            pady=8
        )
        title_label.pack(side=tk.LEFT, padx=15)
        
        # Collapse/expand button
        self.collapse_btn = tk.Button(
            header_frame,
            text="−",
            font=("SF Pro", 16),
            bg='#2d2d2d',
            fg='#888888',
            bd=0,
            padx=8,
            pady=0,
            cursor="hand2",
            command=self._toggle_collapse
        )
        self.collapse_btn.pack(side=tk.RIGHT, padx=5)
        
        # Clear button
        clear_btn = tk.Button(
            header_frame,
            text="🗑",
            font=("SF Pro", 12),
            bg='#2d2d2d',
            fg='#888888',
            bd=0,
            padx=8,
            cursor="hand2",
            command=self._clear_text
        )
        clear_btn.pack(side=tk.RIGHT, padx=2)
        
        # Content frame (collapsible)
        self.content_frame = tk.Frame(self.root, bg='#1e1e1e')
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Text area with scrollbar
        self.text_area = scrolledtext.ScrolledText(
            self.content_frame,
            wrap=tk.WORD,
            font=("SF Mono", 11),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='#ffffff',
            selectbackground='#264f78',
            relief=tk.FLAT,
            padx=12,
            pady=10
        )
        self.text_area.pack(fill=tk.BOTH, expand=True)
        
        # Configure tags for different message types
        self.text_area.tag_config("thinking", foreground="#9cdcfe")  # Light blue
        self.text_area.tag_config("planner", foreground="#4ec9b0")    # Teal
        self.text_area.tag_config("executor", foreground="#ce9178")   # Orange
        self.text_area.tag_config("supervisor", foreground="#c586c0") # Purple
        self.text_area.tag_config("success", foreground="#4ec9b0")    # Green
        self.text_area.tag_config("error", foreground="#f48771")      # Red
        self.text_area.tag_config("warning", foreground="#dcdcaa")    # Yellow
        self.text_area.tag_config("info", foreground="#d4d4d4")       # Gray
        self.text_area.tag_config("timestamp", foreground="#6a9955")  # Dark green
        self.text_area.tag_config("bold", font=("SF Mono", 11, "bold"))
        
        # Status bar
        status_frame = tk.Frame(self.root, bg='#2d2d2d', height=30)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(
            status_frame,
            text="● Idle",
            font=("SF Pro", 10),
            bg='#2d2d2d',
            fg='#888888',
            anchor=tk.W,
            padx=15
        )
        self.status_label.pack(fill=tk.X)
        
        # Make window draggable
        header_frame.bind('<Button-1>', self._start_drag)
        header_frame.bind('<B1-Motion>', self._on_drag)
        title_label.bind('<Button-1>', self._start_drag)
        title_label.bind('<B1-Motion>', self._on_drag)
    
    def _toggle_collapse(self):
        """Toggle window collapsed state."""
        if self.is_collapsed:
            # Expand
            self.content_frame.pack(fill=tk.BOTH, expand=True)
            self.collapse_btn.config(text="−")
            self.root.geometry(f"{self.width}x{self.height}")
        else:
            # Collapse
            self.content_frame.pack_forget()
            self.collapse_btn.config(text="+")
            self.root.geometry(f"{self.width}x70")
        
        self.is_collapsed = not self.is_collapsed
    
    def _start_drag(self, event):
        """Start dragging the window."""
        self._drag_start_x = event.x
        self._drag_start_y = event.y
    
    def _on_drag(self, event):
        """Handle window dragging."""
        x = self.root.winfo_x() + event.x - self._drag_start_x
        y = self.root.winfo_y() + event.y - self._drag_start_y
        self.root.geometry(f"+{x}+{y}")
    
    def _clear_text(self):
        """Clear the text area."""
        if self.text_area:
            self.text_area.delete(1.0, tk.END)
            self.messages.clear()
    
    def _process_queue(self):
        """Process message queue and update UI."""
        if not self.running:
            return
        
        try:
            # Process all pending messages
            while True:
                try:
                    msg = self.message_queue.get_nowait()
                    
                    # Handle special actions
                    if msg.get("action") == "clear":
                        self._clear_text()
                        continue
                    elif msg.get("action") == "status":
                        self._update_status(msg.get("status", "Idle"))
                        continue
                    
                    # Regular thinking message
                    self._append_message(msg)
                    
                except Empty:
                    break
        except:
            pass
        
        # Schedule next check
        if self.root:
            self.root.after(100, self._process_queue)
    
    def _update_status(self, status: str):
        """Update status label."""
        if self.status_label:
            # Add colored dot based on status
            if "running" in status.lower() or "executing" in status.lower():
                dot = "🟢"
            elif "error" in status.lower() or "failed" in status.lower():
                dot = "🔴"
            elif "complete" in status.lower():
                dot = "✅"
            elif "thinking" in status.lower() or "planning" in status.lower():
                dot = "🧠"
            else:
                dot = "●"
            
            self.status_label.config(text=f"{dot} {status}")
    
    def _append_message(self, msg: Dict):
        """Append a message to the text area with formatting."""
        if not self.text_area:
            return
        
        self.messages.append(msg)
        
        component = msg.get("component", "system")
        message = msg.get("message", "")
        level = msg.get("level", "info")
        timestamp = msg.get("timestamp", "")
        
        # Format message
        # Timestamp
        self.text_area.insert(tk.END, f"[{timestamp}] ", "timestamp")
        
        # Component badge
        component_upper = component.upper()
        emoji = {
            "PLANNER": "📋",
            "EXECUTOR": "⚡",
            "SUPERVISOR": "👁",
            "SYSTEM": "🤖"
        }.get(component_upper, "💭")
        
        self.text_area.insert(tk.END, f"{emoji} {component_upper}: ", (component.lower(), "bold"))
        
        # Message content
        self.text_area.insert(tk.END, f"{message}\n", level)
        
        # Separator for thinking messages
        if level == "thinking":
            self.text_area.insert(tk.END, "─" * 50 + "\n", "info")
        
        self.text_area.insert(tk.END, "\n")
        
        # Auto-scroll to bottom
        self.text_area.see(tk.END)
        
        # Limit message history (keep last 100)
        if len(self.messages) > 100:
            self.messages.pop(0)


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
    if not TKINTER_AVAILABLE:
        print("⚠️  Thinking window unavailable (tkinter not installed)")
        return None
    
    window = get_thinking_window()
    if window and not (hasattr(window, 'disabled') and window.disabled):
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
    if not TKINTER_AVAILABLE:
        return
    
    window = get_thinking_window()
    if window and window.running:
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
    if not TKINTER_AVAILABLE:
        return
    
    window = get_thinking_window()
    if window and window.running:
        window.set_status(status)


if __name__ == "__main__":
    # Test the window
    if not TKINTER_AVAILABLE:
        print("❌ Cannot run demo: tkinter not available")
        print("   Install with: brew install python-tk@3.14")
        exit(1)
    
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
    
    # Keep window open
    input("Press Enter to close...")
    stop_thinking_window()
