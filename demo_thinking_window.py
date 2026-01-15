#!/usr/bin/env python3
"""
Demo script to test the thinking window.
Shows how the window displays AI thinking in real-time using Textual TUI.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui.thinking_window import (
    start_thinking_window,
    stop_thinking_window,
    show_planner_thinking,
    show_executor_thinking,
    show_supervisor_thinking,
    show_thinking,
    set_window_status,
    TEXTUAL_AVAILABLE
)


def demo_console_mode():
    """Run demo in console-only mode (no full Textual app)."""
    print("🚀 Starting Thinking Window Demo (Console Mode)")
    print("=" * 60)
    
    # Start the window (will use Rich console fallback)
    window = start_thinking_window()
    time.sleep(0.5)
    
    print("\n📋 Simulating task planning...")
    set_window_status("Planning task...")
    show_thinking("system", "Task received: 'Open Safari and search for Python tutorials'", "info")
    time.sleep(1)
    
    show_planner_thinking("Analyzing task structure and requirements")
    time.sleep(0.8)
    
    show_planner_thinking("Breaking down into executable steps")
    time.sleep(0.8)
    
    show_planner_thinking("Identified 2 batches: 1 blind, 1 vision")
    time.sleep(0.8)
    
    show_planner_thinking("Batch 1: [BLIND] Open Safari and navigate to search")
    time.sleep(0.6)
    
    show_planner_thinking("Batch 2: [VISION] Click first search result")
    time.sleep(1)
    
    print("\n⚡ Simulating execution...")
    set_window_status("Executing...")
    show_executor_thinking("Starting execution loop")
    time.sleep(0.8)
    
    show_executor_thinking("Batch 1/2: Opening Safari...")
    time.sleep(0.6)
    
    show_executor_thinking("Executed: hotkey:command,space")
    time.sleep(0.4)
    
    show_executor_thinking("Executed: type:Safari")
    time.sleep(0.4)
    
    show_executor_thinking("Executed: key:enter")
    time.sleep(0.6)
    
    show_executor_thinking("Waiting for app to launch...")
    time.sleep(0.8)
    
    show_executor_thinking("Executed: hotkey:command,l (focus URL bar)")
    time.sleep(0.4)
    
    show_executor_thinking("Executed: type:Python tutorials")
    time.sleep(0.4)
    
    show_executor_thinking("Executed: key:enter")
    time.sleep(0.8)
    
    print("\n👁️  Simulating supervisor validation...")
    show_supervisor_thinking("Supervisor monitoring started")
    time.sleep(0.6)
    
    show_supervisor_thinking("✓ Validated: Safari opened successfully")
    time.sleep(0.5)
    
    show_supervisor_thinking("✓ Validated: Search query entered")
    time.sleep(0.5)
    
    show_supervisor_thinking("✓ Validated: Search initiated")
    time.sleep(0.8)
    
    print("\n🎯 Simulating vision action...")
    show_executor_thinking("Batch 2/2: Vision action required")
    time.sleep(0.6)
    
    show_executor_thinking("Vision action: Click first search result")
    time.sleep(0.8)
    
    show_supervisor_thinking("✓ Validated: Correct element identified")
    time.sleep(0.6)
    
    show_executor_thinking("Vision action completed successfully")
    time.sleep(0.8)
    
    print("\n✅ Task completion...")
    set_window_status("✅ Completed")
    show_thinking("system", "Task completed successfully in 8.2s", "success")
    show_thinking("system", "Actions: 8/8 successful | Batches: 2/2 completed", "success")
    time.sleep(1)
    
    print("\n" + "=" * 60)
    print("✨ Demo complete!")
    print("=" * 60)
    
    stop_thinking_window()


def demo_textual_mode():
    """Run demo with full Textual TUI app."""
    from threading import Thread
    
    print("🚀 Starting Thinking Window Demo (Textual TUI)")
    print("=" * 60)
    print("💡 Press 'q' to quit, 'c' to clear the log")
    print("=" * 60)
    
    # Start the Textual window
    window = start_thinking_window()
    time.sleep(1)  # Wait for window to initialize
    
    # Run the demo sequence in a background thread
    def run_demo():
        time.sleep(0.5)
        
        set_window_status("Planning task...")
        show_thinking("system", "Task received: 'Open Safari and search for Python tutorials'", "info")
        time.sleep(1.5)
        
        show_planner_thinking("Analyzing task structure and requirements")
        time.sleep(1)
        
        show_planner_thinking("Breaking down into executable steps")
        time.sleep(1)
        
        show_planner_thinking("Identified 2 batches: 1 blind, 1 vision")
        time.sleep(1)
        
        show_planner_thinking("Batch 1: [BLIND] Open Safari and navigate to search")
        time.sleep(0.8)
        
        show_planner_thinking("Batch 2: [VISION] Click first search result")
        time.sleep(1.5)
        
        set_window_status("Executing...")
        show_executor_thinking("Starting execution loop")
        time.sleep(1)
        
        show_executor_thinking("Batch 1/2: Opening Safari...")
        time.sleep(0.8)
        
        show_executor_thinking("Executed: hotkey:command,space")
        time.sleep(0.5)
        
        show_executor_thinking("Executed: type:Safari")
        time.sleep(0.5)
        
        show_executor_thinking("Executed: key:enter")
        time.sleep(0.8)
        
        show_executor_thinking("Waiting for app to launch...")
        time.sleep(1)
        
        show_executor_thinking("Executed: hotkey:command,l (focus URL bar)")
        time.sleep(0.5)
        
        show_executor_thinking("Executed: type:Python tutorials")
        time.sleep(0.5)
        
        show_executor_thinking("Executed: key:enter")
        time.sleep(1)
        
        show_supervisor_thinking("Supervisor monitoring started")
        time.sleep(0.8)
        
        show_supervisor_thinking("✓ Validated: Safari opened successfully")
        time.sleep(0.6)
        
        show_supervisor_thinking("✓ Validated: Search query entered")
        time.sleep(0.6)
        
        show_supervisor_thinking("✓ Validated: Search initiated")
        time.sleep(1)
        
        show_executor_thinking("Batch 2/2: Vision action required")
        time.sleep(0.8)
        
        show_executor_thinking("Vision action: Click first search result")
        time.sleep(1)
        
        show_supervisor_thinking("✓ Validated: Correct element identified")
        time.sleep(0.8)
        
        show_executor_thinking("Vision action completed successfully")
        time.sleep(1)
        
        set_window_status("✅ Completed")
        show_thinking("system", "Task completed successfully in 8.2s", "success")
        show_thinking("system", "Actions: 8/8 successful | Batches: 2/2 completed", "success")
    
    # Start demo in background
    demo_thread = Thread(target=run_demo, daemon=True)
    demo_thread.start()
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Exiting demo...")
        stop_thinking_window()


def demo_thinking_window():
    """Run the demo in appropriate mode."""
    if TEXTUAL_AVAILABLE:
        demo_textual_mode()
    else:
        demo_console_mode()


if __name__ == "__main__":
    demo_thinking_window()
