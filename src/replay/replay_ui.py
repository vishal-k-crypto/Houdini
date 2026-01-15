"""
Replay UI - Interactive terminal interface for time travel debugging.

Features:
- Timeline scrubber with visual markers
- Thinking window history display
- Cursor trajectory visualization
- Screenshot preview at checkpoints
- Play/pause/speed controls
- Keyboard navigation
"""

import time
from pathlib import Path
from typing import Optional, List, Dict, Callable
from datetime import datetime
import os
import subprocess

from .replay_engine import (
    ReplayEngine, ReplaySession, ReplayState, TimelineMarker,
    list_available_task_ids
)
from .execution_logger import ExecutionEvent, EventType

# Try to import rich for beautiful console output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
    from rich.syntax import Syntax
    from rich.align import Align
    from rich.box import ROUNDED, DOUBLE
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Try to import textual for full TUI
try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
    from textual.widgets import Header, Footer, Static, Label, Button, ProgressBar, DataTable
    from textual.reactive import reactive
    from textual import events
    from textual.binding import Binding
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


class ReplayUI:
    """
    Interactive replay interface.
    
    Supports two modes:
    1. Textual TUI: Full interactive interface with keyboard navigation
    2. Rich Console: Simpler console-based display
    """
    
    def __init__(self):
        self.engine = ReplayEngine()
        self.console = Console() if RICH_AVAILABLE else None
    
    def list_sessions_interactive(self) -> Optional[str]:
        """Show interactive session picker."""
        sessions = self.engine.list_sessions()
        task_ids = list_available_task_ids()
        
        if not sessions and not task_ids:
            if self.console:
                self.console.print(
                    Panel(
                        "[yellow]No replay sessions found![/yellow]\n\n"
                        "Run some tasks first, then use [cyan]--replay[/cyan] to view them.\n\n"
                        "[dim]Sessions are saved to: data/replay_sessions/[/dim]",
                        title="📼 Replay Mode",
                        border_style="yellow"
                    )
                )
            else:
                print("No replay sessions found. Run some tasks first.")
            return None
        
        if self.console:
            return self._rich_session_picker(sessions, task_ids)
        else:
            return self._simple_session_picker(sessions, task_ids)
    
    def _rich_session_picker(self, sessions: List[Dict], task_ids: List[str]) -> Optional[str]:
        """Rich-based session picker."""
        self.console.print()
        self.console.print(Panel(
            "[bold cyan]🕐 TIME TRAVEL DEBUGGING[/bold cyan]\n\n"
            "Select a session to replay. You'll see exactly what happened:\n"
            "• Cursor movements and clicks\n"
            "• AI thinking at each moment\n"
            "• Screenshots at checkpoints",
            title="📼 Replay Mode",
            border_style="cyan"
        ))
        
        # Show logged sessions
        if sessions:
            table = Table(title="📋 Recorded Sessions", box=ROUNDED)
            table.add_column("#", style="dim", width=4)
            table.add_column("Task ID", style="cyan", width=12)
            table.add_column("Description", style="white")
            table.add_column("Started", style="dim")
            table.add_column("Events", justify="right", style="green")
            table.add_column("Status", width=8)
            
            for i, s in enumerate(sessions[:20], 1):
                status = "[green]✓[/green]" if s["success"] else "[red]✗[/red]"
                started = s["started_at"][:19] if s["started_at"] else ""
                desc = s["task_description"][:40] + "..." if len(s["task_description"]) > 40 else s["task_description"]
                table.add_row(
                    str(i),
                    s["task_id"][:10],
                    desc,
                    started,
                    str(s["event_count"]),
                    status
                )
            
            self.console.print(table)
        
        # Show screenshot-based sessions
        if task_ids:
            self.console.print()
            screenshot_table = Table(title="📸 Screenshot Checkpoints (Legacy)", box=ROUNDED)
            screenshot_table.add_column("#", style="dim", width=4)
            screenshot_table.add_column("Task ID", style="yellow")
            screenshot_table.add_column("Screenshots", justify="right")
            
            for i, tid in enumerate(task_ids[:10], len(sessions) + 1):
                ss_dir = Path(__file__).parent.parent.parent / "data" / "screenshots" / tid
                ss_count = len(list(ss_dir.glob("*.png")))
                screenshot_table.add_row(str(i), tid, str(ss_count))
            
            self.console.print(screenshot_table)
        
        # Get user selection
        self.console.print()
        try:
            choice = self.console.input("[bold]Enter session number (or 'q' to quit): [/bold]")
        except (KeyboardInterrupt, EOFError):
            return None
        
        if choice.lower() == 'q':
            return None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                return sessions[idx]["filepath"]
            elif 0 <= idx - len(sessions) < len(task_ids):
                return f"screenshots:{task_ids[idx - len(sessions)]}"
        except ValueError:
            # Try as task ID
            return choice
        
        return None
    
    def _simple_session_picker(self, sessions: List[Dict], task_ids: List[str]) -> Optional[str]:
        """Simple text-based session picker."""
        print("\n📼 REPLAY MODE - Available Sessions\n")
        
        for i, s in enumerate(sessions[:20], 1):
            status = "✓" if s["success"] else "✗"
            print(f"  {i}. [{s['task_id'][:8]}] {s['task_description'][:50]} ({status})")
        
        if task_ids:
            print("\n  Screenshot-only sessions:")
            for i, tid in enumerate(task_ids[:10], len(sessions) + 1):
                print(f"  {i}. [screenshots] {tid}")
        
        try:
            choice = input("\nEnter session number (or 'q' to quit): ")
        except (KeyboardInterrupt, EOFError):
            return None
        
        if choice.lower() == 'q':
            return None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sessions):
                return sessions[idx]["filepath"]
            elif 0 <= idx - len(sessions) < len(task_ids):
                return f"screenshots:{task_ids[idx - len(sessions)]}"
        except ValueError:
            return choice
        
        return None
    
    def replay(self, session_id: Optional[str] = None):
        """Start replay with optional session ID."""
        # Get session to replay
        if not session_id:
            session_id = self.list_sessions_interactive()
        
        if not session_id:
            return
        
        # Load session
        if session_id.startswith("screenshots:"):
            task_id = session_id.split(":", 1)[1]
            session = self.engine.import_from_screenshots(task_id)
        else:
            session = self.engine.load_session(session_id)
        
        if not session:
            if self.console:
                self.console.print(f"[red]Could not load session: {session_id}[/red]")
            else:
                print(f"Could not load session: {session_id}")
            return
        
        # Start replay interface
        if TEXTUAL_AVAILABLE:
            self._run_textual_replay(session)
        elif RICH_AVAILABLE:
            self._run_rich_replay(session)
        else:
            self._run_simple_replay(session)
    
    def _run_textual_replay(self, session: ReplaySession):
        """Full Textual TUI replay interface."""
        app = ReplayTUIApp(session, self.engine)
        app.run()
    
    def _run_rich_replay(self, session: ReplaySession):
        """Rich console-based replay."""
        self.console.clear()
        
        # Header
        self.console.print(Panel(
            f"[bold cyan]📼 REPLAYING: {session.session.task_description}[/bold cyan]\n"
            f"[dim]Task ID: {session.session.task_id} | "
            f"Events: {len(session.session.events)} | "
            f"Duration: {session.duration_ms / 1000:.1f}s[/dim]",
            border_style="cyan"
        ))
        
        # Controls info
        self.console.print(
            "\n[dim]Controls: [/dim]"
            "[bold]SPACE[/bold]=play/pause  "
            "[bold]←/→[/bold]=seek  "
            "[bold]↑/↓[/bold]=speed  "
            "[bold]n/p[/bold]=next/prev marker  "
            "[bold]q[/bold]=quit\n"
        )
        
        # Run playback with Live display
        self._rich_playback_loop(session)
    
    def _rich_playback_loop(self, session: ReplaySession):
        """Rich-based playback loop with live updates."""
        import sys
        import tty
        import termios
        import select
        
        def get_key_nonblocking():
            """Get key press without blocking."""
            if select.select([sys.stdin], [], [], 0)[0]:
                return sys.stdin.read(1)
            return None
        
        # Set terminal to raw mode
        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            
            with Live(self._build_replay_display(session), refresh_per_second=10, console=self.console) as live:
                last_update = time.time()
                
                while True:
                    # Handle input
                    key = get_key_nonblocking()
                    if key:
                        if key == 'q':
                            break
                        elif key == ' ':
                            if session.state == ReplayState.PLAYING:
                                self.engine.pause()
                            else:
                                self.engine.play()
                        elif key == '\x1b':  # Arrow keys start with escape
                            # Read the rest of the arrow key sequence
                            if select.select([sys.stdin], [], [], 0.1)[0]:
                                key2 = sys.stdin.read(1)
                                if key2 == '[':
                                    if select.select([sys.stdin], [], [], 0.1)[0]:
                                        key3 = sys.stdin.read(1)
                                        if key3 == 'D':  # Left
                                            session.seek_relative(-1000)
                                        elif key3 == 'C':  # Right
                                            session.seek_relative(1000)
                                        elif key3 == 'A':  # Up
                                            self.engine.set_speed(session.speed * 1.5)
                                        elif key3 == 'B':  # Down
                                            self.engine.set_speed(session.speed / 1.5)
                        elif key == 'n':
                            session.next_marker()
                        elif key == 'p':
                            session.prev_marker()
                    
                    # Update display periodically
                    now = time.time()
                    if now - last_update > 0.1:
                        live.update(self._build_replay_display(session))
                        last_update = now
                    
                    time.sleep(0.016)  # 60fps
                    
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    def _build_replay_display(self, session: ReplaySession) -> Panel:
        """Build the Rich display for current replay state."""
        layout = Table.grid(padding=1)
        layout.add_column()
        
        # Timeline bar
        progress = session.progress
        bar_width = 60
        filled = int(bar_width * progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        position_str = f"{session.position_ms / 1000:.1f}s"
        duration_str = f"{session.duration_ms / 1000:.1f}s"
        
        timeline = Text()
        timeline.append(f"[{position_str:>6}] ", style="cyan")
        timeline.append(bar, style="green")
        timeline.append(f" [{duration_str}]", style="cyan")
        
        # Status
        state_emoji = {"playing": "▶️", "paused": "⏸️", "stopped": "⏹️"}.get(session.state.value, "?")
        status = Text()
        status.append(f"{state_emoji} {session.state.value.upper()}", style="bold")
        status.append(f"  Speed: {session.speed:.1f}x", style="dim")
        
        # Cursor position
        cursor_x, cursor_y = session.get_cursor_at_position()
        cursor_text = f"🖱️ Cursor: ({cursor_x or '?'}, {cursor_y or '?'})"
        
        # Current event
        current_event = session.get_current_event()
        event_text = ""
        if current_event:
            event_text = f"📍 {current_event.event_type.value}: {str(current_event.data)[:60]}"
        
        # Thinking history
        thinking = session.get_thinking_history(5)
        thinking_panel = Table.grid()
        for msg in thinking:
            component = msg["component"]
            emoji = {"planner": "📋", "executor": "⚡", "supervisor": "👁️"}.get(component.lower(), "💭")
            color = {"planner": "green", "executor": "yellow", "supervisor": "magenta"}.get(component.lower(), "white")
            thinking_panel.add_row(
                Text(f"{emoji} ", style=color),
                Text(msg["message"][:70], style=color)
            )
        
        # Markers
        markers_text = Text()
        for i, marker in enumerate(session.markers[:5]):
            marker_pos_sec = marker.position_ms / 1000
            is_current = marker.position_ms <= session.position_ms < (session.markers[i+1].position_ms if i+1 < len(session.markers) else session.duration_ms)
            style = "bold" if is_current else "dim"
            markers_text.append(f"• {marker.label} ({marker_pos_sec:.1f}s)\n", style=style)
        
        # Combine
        layout.add_row(status)
        layout.add_row(timeline)
        layout.add_row(Text(cursor_text, style="dim"))
        layout.add_row(Text(event_text, style="cyan"))
        layout.add_row(Text())
        layout.add_row(Text("🧠 Thinking History:", style="bold"))
        layout.add_row(thinking_panel)
        layout.add_row(Text())
        layout.add_row(Text("🏁 Markers:", style="bold"))
        layout.add_row(markers_text)
        
        return Panel(layout, title="📼 Replay", border_style="cyan")
    
    def _run_simple_replay(self, session: ReplaySession):
        """Simple text-based replay."""
        print(f"\n📼 Replaying: {session.session.task_description}")
        print(f"   Duration: {session.duration_ms / 1000:.1f}s | Events: {len(session.session.events)}")
        print("\nEvents:")
        
        for i, event in enumerate(session.session.events[:50]):
            time_str = f"{event.relative_ms / 1000:6.2f}s"
            print(f"  [{time_str}] {event.event_type.value}: {str(event.data)[:60]}")
        
        if len(session.session.events) > 50:
            print(f"\n  ... and {len(session.session.events) - 50} more events")


if TEXTUAL_AVAILABLE:
    
    class TimelineWidget(Static):
        """Timeline widget showing playback position and markers."""
        
        position = reactive(0)
        duration = reactive(1000)
        
        def __init__(self, session: ReplaySession, **kwargs):
            super().__init__(**kwargs)
            self.session = session
        
        def render(self) -> Text:
            text = Text()
            
            # Progress bar
            progress = (self.position / max(self.duration, 1)) * 100
            bar_width = 60
            filled = int(bar_width * progress / 100)
            
            text.append(f"{self.position / 1000:5.1f}s ", style="cyan bold")
            text.append("█" * filled, style="green")
            text.append("░" * (bar_width - filled), style="dim")
            text.append(f" {self.duration / 1000:.1f}s", style="cyan")
            
            return text
        
        def update_position(self, pos_ms: int, dur_ms: int):
            self.position = pos_ms
            self.duration = dur_ms
    
    
    class ThinkingHistoryWidget(Static):
        """Widget showing thinking window history."""
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.messages: List[Dict] = []
        
        def render(self) -> Text:
            text = Text()
            text.append("🧠 THINKING HISTORY\n", style="bold cyan")
            text.append("─" * 40 + "\n", style="dim")
            
            for msg in self.messages[-10:]:
                component = msg.get("component", "system")
                emoji = {"planner": "📋", "executor": "⚡", "supervisor": "👁️"}.get(component.lower(), "💭")
                color = {"planner": "#00ff88", "executor": "#ff6b2b", "supervisor": "#bf5af2"}.get(component.lower(), "#00d4ff")
                
                text.append(f"{emoji} ", style=color)
                text.append(msg.get("message", "")[:60] + "\n", style=color)
            
            return text
        
        def update_messages(self, messages: List[Dict]):
            self.messages = messages
            self.refresh()
    
    
    class CursorWidget(Static):
        """Widget showing cursor position."""
        
        cursor_x = reactive(0)
        cursor_y = reactive(0)
        
        def render(self) -> Text:
            text = Text()
            text.append("🖱️ CURSOR: ", style="bold")
            text.append(f"({self.cursor_x}, {self.cursor_y})", style="cyan")
            return text
        
        def update_cursor(self, x: int, y: int):
            self.cursor_x = x or 0
            self.cursor_y = y or 0
    
    
    class EventWidget(Static):
        """Widget showing current event."""
        
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.current_event: Optional[ExecutionEvent] = None
        
        def render(self) -> Text:
            text = Text()
            text.append("📍 CURRENT EVENT\n", style="bold yellow")
            
            if self.current_event:
                text.append(f"Type: {self.current_event.event_type.value}\n", style="cyan")
                text.append(f"Data: {str(self.current_event.data)[:80]}\n", style="dim")
            else:
                text.append("(no event)", style="dim")
            
            return text
        
        def update_event(self, event: Optional[ExecutionEvent]):
            self.current_event = event
            self.refresh()
    
    
    class MarkersWidget(Static):
        """Widget showing timeline markers."""
        
        def __init__(self, markers: List[TimelineMarker], **kwargs):
            super().__init__(**kwargs)
            self.markers = markers
            self.current_position = 0
        
        def render(self) -> Text:
            text = Text()
            text.append("🏁 MARKERS\n", style="bold magenta")
            text.append("─" * 30 + "\n", style="dim")
            
            for i, marker in enumerate(self.markers[:8]):
                pos_sec = marker.position_ms / 1000
                is_past = marker.position_ms <= self.current_position
                style = "bold" if is_past else "dim"
                icon = "●" if is_past else "○"
                text.append(f"{icon} {pos_sec:5.1f}s  {marker.label[:30]}\n", style=style)
            
            if len(self.markers) > 8:
                text.append(f"  ... +{len(self.markers) - 8} more\n", style="dim")
            
            return text
        
        def update_position(self, pos_ms: int):
            self.current_position = pos_ms
            self.refresh()
    
    
    class ReplayTUIApp(App):
        """Full Textual TUI application for replay."""
        
        CSS = """
        Screen {
            background: #0a0a0a;
        }
        
        #header {
            dock: top;
            height: 5;
            background: #1a1a2e;
            border-bottom: solid #00ff88;
            padding: 1;
        }
        
        #timeline {
            dock: top;
            height: 3;
            background: #1a1a1a;
            border-bottom: solid #333;
            padding: 0 1;
        }
        
        #main-content {
            layout: horizontal;
        }
        
        #left-panel {
            width: 60%;
            padding: 1;
        }
        
        #right-panel {
            width: 40%;
            padding: 1;
            border-left: solid #333;
        }
        
        #controls {
            dock: bottom;
            height: 3;
            background: #1a1a2e;
            border-top: solid #333;
            padding: 0 1;
        }
        
        .widget-box {
            margin-bottom: 1;
            padding: 1;
            background: #151515;
            border: round #333;
        }
        """
        
        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("space", "toggle_play", "Play/Pause"),
            Binding("left", "seek_back", "Seek -1s"),
            Binding("right", "seek_forward", "Seek +1s"),
            Binding("up", "speed_up", "Speed Up"),
            Binding("down", "speed_down", "Speed Down"),
            Binding("n", "next_marker", "Next Marker"),
            Binding("p", "prev_marker", "Prev Marker"),
            Binding("r", "restart", "Restart"),
        ]
        
        def __init__(self, session: ReplaySession, engine: ReplayEngine):
            super().__init__()
            self.session = session
            self.engine = engine
        
        def compose(self) -> ComposeResult:
            yield Container(
                Static(
                    f"📼 REPLAY: {self.session.session.task_description}\n"
                    f"[dim]Task ID: {self.session.session.task_id} | "
                    f"Events: {len(self.session.session.events)} | "
                    f"Duration: {self.session.duration_ms / 1000:.1f}s[/dim]",
                    id="header-text"
                ),
                id="header"
            )
            
            yield Container(
                TimelineWidget(self.session, id="timeline-widget"),
                id="timeline"
            )
            
            yield Container(
                Container(
                    ThinkingHistoryWidget(id="thinking", classes="widget-box"),
                    EventWidget(id="event", classes="widget-box"),
                    id="left-panel"
                ),
                Container(
                    CursorWidget(id="cursor", classes="widget-box"),
                    MarkersWidget(self.session.markers, id="markers", classes="widget-box"),
                    id="right-panel"
                ),
                id="main-content"
            )
            
            yield Container(
                Static(
                    "[bold]SPACE[/bold]=Play/Pause  "
                    "[bold]←/→[/bold]=Seek  "
                    "[bold]↑/↓[/bold]=Speed  "
                    "[bold]n/p[/bold]=Markers  "
                    "[bold]r[/bold]=Restart  "
                    "[bold]q[/bold]=Quit",
                    id="controls-text"
                ),
                id="controls"
            )
            
            yield Footer()
        
        def on_mount(self):
            """Start update loop."""
            self.set_interval(0.1, self._update_display)
        
        def _update_display(self):
            """Update all widgets with current state."""
            # Update timeline
            timeline = self.query_one("#timeline-widget", TimelineWidget)
            timeline.update_position(self.session.position_ms, self.session.duration_ms)
            
            # Update cursor
            cursor = self.query_one("#cursor", CursorWidget)
            x, y = self.session.get_cursor_at_position()
            cursor.update_cursor(x, y)
            
            # Update thinking history
            thinking = self.query_one("#thinking", ThinkingHistoryWidget)
            thinking.update_messages(self.session.get_thinking_history(10))
            
            # Update current event
            event_widget = self.query_one("#event", EventWidget)
            event_widget.update_event(self.session.get_current_event())
            
            # Update markers
            markers = self.query_one("#markers", MarkersWidget)
            markers.update_position(self.session.position_ms)
        
        def action_toggle_play(self):
            if self.session.state == ReplayState.PLAYING:
                self.engine.pause()
            else:
                self.engine.play()
        
        def action_seek_back(self):
            self.session.seek_relative(-1000)
        
        def action_seek_forward(self):
            self.session.seek_relative(1000)
        
        def action_speed_up(self):
            self.engine.set_speed(self.session.speed * 1.5)
        
        def action_speed_down(self):
            self.engine.set_speed(self.session.speed / 1.5)
        
        def action_next_marker(self):
            self.session.next_marker()
        
        def action_prev_marker(self):
            self.session.prev_marker()
        
        def action_restart(self):
            self.engine.stop()
            self.session.seek_to(0)


def run_replay(session_id: Optional[str] = None):
    """Main entry point for replay mode."""
    ui = ReplayUI()
    ui.replay(session_id)


def list_sessions():
    """List available replay sessions."""
    ui = ReplayUI()
    sessions = ui.engine.list_sessions()
    task_ids = list_available_task_ids()
    
    if RICH_AVAILABLE:
        console = Console()
        
        if sessions:
            table = Table(title="📋 Recorded Sessions")
            table.add_column("Task ID", style="cyan")
            table.add_column("Description")
            table.add_column("Started")
            table.add_column("Events", justify="right")
            table.add_column("Status")
            
            for s in sessions:
                status = "✓" if s["success"] else "✗"
                console.print_row = table.add_row(
                    s["task_id"][:10],
                    s["task_description"][:40],
                    s["started_at"][:19] if s["started_at"] else "",
                    str(s["event_count"]),
                    status
                )
            
            console.print(table)
        
        if task_ids:
            console.print("\n📸 Screenshot-based sessions (legacy):")
            for tid in task_ids:
                console.print(f"  • {tid}")
    else:
        print("📋 Available Sessions:")
        for s in sessions:
            print(f"  {s['task_id']}: {s['task_description'][:50]}")
        for tid in task_ids:
            print(f"  [screenshots] {tid}")
