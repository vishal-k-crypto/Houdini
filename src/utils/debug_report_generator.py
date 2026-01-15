"""
Debug Report Generator - Creates AI-readable debug reports from execution sessions.

This module generates comprehensive markdown reports that can be directly
shared with an AI for root cause analysis of automation failures.

Report includes:
- Executive summary with task outcome
- Chronological timeline of events
- Error analysis with before/after context
- Embedded screenshots (base64)
- Full thinking logs from planner/executor/supervisor
- Environment information
- Suggested analysis prompts for AI
"""

import base64
import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import io

try:
    from PIL import Image
    import pyautogui
    SCREENSHOT_AVAILABLE = True
except ImportError:
    SCREENSHOT_AVAILABLE = False

from ..replay.execution_logger import (
    ExecutionSession, ExecutionEvent, EventType,
    get_execution_logger
)


class DebugReportGenerator:
    """
    Generates AI-readable debug reports from execution sessions.
    
    The reports are self-contained markdown files with embedded
    screenshots that can be shared with any AI for analysis.
    """
    
    def __init__(self):
        self.reports_dir = Path(__file__).parent.parent.parent / "data" / "debug_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def capture_screenshot_base64(self, max_width: int = 800) -> Optional[str]:
        """Capture current screen and return as base64 string."""
        if not SCREENSHOT_AVAILABLE:
            return None
        
        try:
            screenshot = pyautogui.screenshot()
            
            # Resize if too large
            if screenshot.width > max_width:
                ratio = max_width / screenshot.width
                new_height = int(screenshot.height * ratio)
                screenshot = screenshot.resize((max_width, new_height), Image.LANCZOS)
            
            # Convert to base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG", optimize=True)
            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode('utf-8')
        except Exception as e:
            return None
    
    def load_screenshot_as_base64(self, filepath: str, max_width: int = 800) -> Optional[str]:
        """Load an existing screenshot file and return as base64."""
        if not filepath or not Path(filepath).exists():
            return None
        
        try:
            with Image.open(filepath) as img:
                # Resize if too large
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.LANCZOS)
                
                buffer = io.BytesIO()
                img.save(buffer, format="PNG", optimize=True)
                buffer.seek(0)
                return base64.b64encode(buffer.read()).decode('utf-8')
        except Exception:
            return None
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Collect environment information for debugging context."""
        info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "machine": platform.machine(),
            "timestamp": datetime.now().isoformat(),
        }
        
        # Try to get macOS version
        try:
            result = subprocess.run(
                ["sw_vers", "-productVersion"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info["macos_version"] = result.stdout.strip()
        except:
            pass
        
        # Try to get frontmost app
        try:
            script = 'tell application "System Events" to get name of first process whose frontmost is true'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                info["frontmost_app"] = result.stdout.strip()
        except:
            pass
        
        return info
    
    def extract_errors(self, session: ExecutionSession) -> List[Dict[str, Any]]:
        """Extract all errors from the session with surrounding context."""
        errors = []
        events = session.events
        
        for i, event in enumerate(events):
            if event.event_type in (EventType.ACTION_FAILED, EventType.TASK_FAILED):
                error_entry = {
                    "timestamp_ms": event.relative_ms,
                    "event_type": event.event_type.value,
                    "error_data": event.data,
                    "cursor_position": (event.cursor_x, event.cursor_y),
                    "screenshot_path": event.screenshot_path,
                }
                
                # Get context: 5 events before and 2 after
                start_idx = max(0, i - 5)
                end_idx = min(len(events), i + 3)
                error_entry["context_before"] = [
                    {
                        "type": e.event_type.value,
                        "time_ms": e.relative_ms,
                        "data": e.data
                    }
                    for e in events[start_idx:i]
                ]
                error_entry["context_after"] = [
                    {
                        "type": e.event_type.value,
                        "time_ms": e.relative_ms,
                        "data": e.data
                    }
                    for e in events[i+1:end_idx]
                ]
                
                errors.append(error_entry)
        
        return errors
    
    def extract_thinking_log(self, session: ExecutionSession) -> List[Dict[str, Any]]:
        """Extract all thinking events from the session."""
        thinking_types = (
            EventType.THINKING_PLANNER,
            EventType.THINKING_EXECUTOR,
            EventType.THINKING_SUPERVISOR,
            EventType.THINKING_SYSTEM,
        )
        
        return [
            {
                "component": event.data.get("component", "unknown"),
                "message": event.data.get("message", ""),
                "level": event.data.get("level", "info"),
                "timestamp_ms": event.relative_ms,
            }
            for event in session.events
            if event.event_type in thinking_types
        ]
    
    def format_duration(self, ms: int) -> str:
        """Format milliseconds as human-readable duration."""
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms/1000:.1f}s"
        else:
            minutes = ms // 60000
            seconds = (ms % 60000) / 1000
            return f"{minutes}m {seconds:.1f}s"
    
    def generate_report(self, session: ExecutionSession, 
                       include_screenshots: bool = True) -> str:
        """
        Generate a comprehensive markdown debug report from an execution session.
        
        Args:
            session: The execution session to generate a report for
            include_screenshots: Whether to embed screenshots as base64
            
        Returns:
            Markdown string containing the full debug report
        """
        lines = []
        
        # Header
        lines.append("# 🔍 Automation Debug Report")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Executive Summary
        lines.append("## 📋 Executive Summary")
        lines.append("")
        status_emoji = "✅" if session.success else "❌"
        lines.append(f"| Property | Value |")
        lines.append(f"|----------|-------|")
        lines.append(f"| **Task ID** | `{session.task_id}` |")
        lines.append(f"| **Task** | {session.task_description} |")
        lines.append(f"| **Status** | {status_emoji} {'Success' if session.success else 'Failed'} |")
        lines.append(f"| **Started** | {session.started_at} |")
        lines.append(f"| **Completed** | {session.completed_at or 'N/A'} |")
        lines.append(f"| **Duration** | {self.format_duration(session.duration_ms())} |")
        lines.append(f"| **Total Events** | {len(session.events)} |")
        lines.append("")
        
        # Event counts
        event_counts = session.event_count_by_type()
        if event_counts:
            lines.append("### Event Breakdown")
            lines.append("```")
            for event_type, count in sorted(event_counts.items()):
                lines.append(f"  {event_type}: {count}")
            lines.append("```")
            lines.append("")
        
        # Environment Info
        lines.append("## 🖥️ Environment")
        lines.append("")
        env_info = self.get_environment_info()
        lines.append("```json")
        lines.append(json.dumps(env_info, indent=2))
        lines.append("```")
        lines.append("")
        
        # Session Metadata
        if session.metadata:
            lines.append("### Session Metadata")
            lines.append("```json")
            lines.append(json.dumps(session.metadata, indent=2))
            lines.append("```")
            lines.append("")
        
        # Error Analysis (if any errors)
        errors = self.extract_errors(session)
        if errors:
            lines.append("## ❌ Error Analysis")
            lines.append("")
            lines.append("> [!CAUTION]")
            lines.append(f"> Found {len(errors)} error(s) during execution")
            lines.append("")
            
            for i, error in enumerate(errors, 1):
                lines.append(f"### Error {i}: {error['event_type']}")
                lines.append("")
                lines.append(f"**Time**: {self.format_duration(error['timestamp_ms'])}")
                lines.append(f"**Cursor Position**: {error['cursor_position']}")
                lines.append("")
                
                lines.append("**Error Data:**")
                lines.append("```json")
                lines.append(json.dumps(error['error_data'], indent=2))
                lines.append("```")
                lines.append("")
                
                if error['context_before']:
                    lines.append("**Events Before Error:**")
                    lines.append("```")
                    for ctx in error['context_before']:
                        lines.append(f"  [{self.format_duration(ctx['time_ms'])}] {ctx['type']}: {ctx['data']}")
                    lines.append("```")
                    lines.append("")
                
                if error['context_after']:
                    lines.append("**Events After Error:**")
                    lines.append("```")
                    for ctx in error['context_after']:
                        lines.append(f"  [{self.format_duration(ctx['time_ms'])}] {ctx['type']}: {ctx['data']}")
                    lines.append("```")
                    lines.append("")
                
                # Embed screenshot if available
                if include_screenshots and error['screenshot_path']:
                    b64 = self.load_screenshot_as_base64(error['screenshot_path'])
                    if b64:
                        lines.append(f"**Screenshot at Error:**")
                        lines.append(f"![Error Screenshot](data:image/png;base64,{b64})")
                        lines.append("")
        
        # Screenshots Gallery
        screenshot_events = [
            e for e in session.events 
            if e.event_type == EventType.SCREENSHOT and e.screenshot_path
        ]
        if include_screenshots and screenshot_events:
            lines.append("## 📸 Screenshot Timeline")
            lines.append("")
            
            for i, event in enumerate(screenshot_events, 1):
                lines.append(f"### Screenshot {i}: {event.data.get('description', 'Checkpoint')}")
                lines.append(f"**Time**: {self.format_duration(event.relative_ms)}")
                lines.append("")
                
                b64 = self.load_screenshot_as_base64(event.screenshot_path)
                if b64:
                    lines.append(f"![Screenshot {i}](data:image/png;base64,{b64})")
                else:
                    lines.append(f"*Screenshot file: `{event.screenshot_path}`*")
                lines.append("")
        
        # Thinking Log
        thinking_log = self.extract_thinking_log(session)
        if thinking_log:
            lines.append("## 🧠 AI Thinking Log")
            lines.append("")
            lines.append("Full log of AI reasoning during execution:")
            lines.append("")
            
            # Group by component
            components = {}
            for entry in thinking_log:
                comp = entry['component']
                if comp not in components:
                    components[comp] = []
                components[comp].append(entry)
            
            for comp, entries in components.items():
                icon = {"planner": "📋", "executor": "⚡", "supervisor": "👁️"}.get(comp.lower(), "💭")
                lines.append(f"### {icon} {comp.title()} ({len(entries)} messages)")
                lines.append("")
                lines.append("```")
                for entry in entries:
                    time_str = self.format_duration(entry['timestamp_ms'])
                    level = entry['level'].upper()
                    msg = entry['message'][:200] + "..." if len(entry['message']) > 200 else entry['message']
                    lines.append(f"[{time_str}] [{level}] {msg}")
                lines.append("```")
                lines.append("")
        
        # Full Timeline
        lines.append("## ⏱️ Event Timeline")
        lines.append("")
        lines.append("Complete chronological sequence of events:")
        lines.append("")
        lines.append("| Time | Type | Details |")
        lines.append("|------|------|---------|")
        
        # Show key events only (not cursor moves)
        key_events = [
            e for e in session.events
            if e.event_type not in (EventType.CURSOR_MOVE,)
        ][:100]  # Limit to 100 entries
        
        for event in key_events:
            time_str = self.format_duration(event.relative_ms)
            event_type = event.event_type.value
            
            # Summarize data
            data_summary = ""
            if event.event_type == EventType.ACTION_START:
                data_summary = event.data.get("action", "")[:50]
            elif event.event_type == EventType.ACTION_COMPLETE:
                success = "✓" if event.data.get("success") else "✗"
                data_summary = f"{success} {event.data.get('action', '')[:40]}"
            elif event.event_type == EventType.BATCH_START:
                data_summary = event.data.get("description", "")[:50]
            elif event.event_type in (EventType.THINKING_PLANNER, EventType.THINKING_EXECUTOR, EventType.THINKING_SUPERVISOR):
                data_summary = event.data.get("message", "")[:50]
            elif event.event_type == EventType.CURSOR_CLICK:
                data_summary = f"({event.data.get('x')}, {event.data.get('y')})"
            else:
                data_summary = str(event.data)[:50]
            
            lines.append(f"| {time_str} | `{event_type}` | {data_summary} |")
        
        if len(session.events) > len(key_events):
            lines.append(f"| ... | *{len(session.events) - len(key_events)} more events* | ... |")
        
        lines.append("")
        
        # Suggested Analysis Prompts
        lines.append("## 🤖 Suggested Analysis Prompts")
        lines.append("")
        lines.append("Copy one of these prompts to ask an AI for analysis:")
        lines.append("")
        lines.append("1. **Root Cause Analysis**:")
        lines.append("   > \"Based on this debug report, what is the most likely root cause of the failure?\"")
        lines.append("")
        lines.append("2. **Action Sequence Review**:")
        lines.append("   > \"Review the action sequence and identify any actions that might have failed or been incorrect.\"")
        lines.append("")
        lines.append("3. **Timing Analysis**:")
        lines.append("   > \"Are there any suspicious gaps or delays in the timeline that might indicate waiting issues?\"")
        lines.append("")
        lines.append("4. **Screen State Analysis**:")
        lines.append("   > \"Based on the screenshots, what was the screen state when the error occurred?\"")
        lines.append("")
        lines.append("5. **Recovery Suggestion**:")
        lines.append("   > \"What changes to the automation would prevent this type of failure?\"")
        lines.append("")
        
        # Raw Session Data (collapsed)
        lines.append("## 📦 Raw Session Data")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>Click to expand full JSON session data</summary>")
        lines.append("")
        lines.append("```json")
        # Truncate for size
        session_dict = session.to_dict()
        session_dict["events"] = session_dict["events"][:50]  # Limit events
        lines.append(json.dumps(session_dict, indent=2))
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")
        
        return "\n".join(lines)
    
    def export_to_file(self, session: ExecutionSession, 
                       output_path: Optional[Path] = None) -> Path:
        """
        Export a debug report to a markdown file.
        
        Args:
            session: The execution session to export
            output_path: Optional custom output path
            
        Returns:
            Path to the generated report file
        """
        report_content = self.generate_report(session)
        
        if output_path is None:
            # Generate filename from task ID and timestamp
            safe_id = "".join(c if c.isalnum() else "_" for c in session.task_id[:20])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_report_{safe_id}_{timestamp}.md"
            output_path = self.reports_dir / filename
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_content, encoding="utf-8")
        
        return output_path
    
    def export_latest_session(self) -> Optional[Path]:
        """
        Export a debug report for the most recent execution session.
        
        Returns:
            Path to the generated report, or None if no sessions found
        """
        logger = get_execution_logger()
        session_files = logger.get_session_files()
        
        if not session_files:
            return None
        
        # Load the most recent session
        latest_session = logger.load_session(session_files[0])
        return self.export_to_file(latest_session)
    
    def export_failed_sessions(self, limit: int = 10) -> List[Path]:
        """
        Export debug reports for all failed sessions.
        
        Args:
            limit: Maximum number of reports to generate
            
        Returns:
            List of paths to generated reports
        """
        logger = get_execution_logger()
        session_files = logger.get_session_files()
        
        reports = []
        for filepath in session_files[:limit * 2]:  # Check more files to find failures
            if len(reports) >= limit:
                break
            
            session = logger.load_session(filepath)
            if not session.success:
                report_path = self.export_to_file(session)
                reports.append(report_path)
        
        return reports


# Global instance
_debug_report_generator: Optional[DebugReportGenerator] = None


def get_debug_report_generator() -> DebugReportGenerator:
    """Get the global debug report generator instance."""
    global _debug_report_generator
    if _debug_report_generator is None:
        _debug_report_generator = DebugReportGenerator()
    return _debug_report_generator


def generate_debug_report(session: ExecutionSession) -> str:
    """Convenience function to generate a debug report."""
    return get_debug_report_generator().generate_report(session)


def export_debug_report(session: ExecutionSession,
                       output_path: Optional[Path] = None) -> Path:
    """Convenience function to export a debug report to file."""
    return get_debug_report_generator().export_to_file(session, output_path)


def export_latest_debug_report() -> Optional[Path]:
    """Convenience function to export report for the latest session."""
    return get_debug_report_generator().export_latest_session()
