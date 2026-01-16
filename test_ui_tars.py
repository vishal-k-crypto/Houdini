#!/usr/bin/env python3
"""
Test script for UI-TARS via MLX - Semantic UI Element Localization.

This tests the local ML model that runs on Apple Silicon for finding
UI elements by natural language description.

NOW WITH ADAPTIVE LEARNING: The system learns from your clicks and
improves over time using a LangGraph-based feedback loop.

Usage:
    python test_ui_tars.py                          # Interactive mode
    python test_ui_tars.py "search button"          # Find specific element
    python test_ui_tars.py --click "submit button"  # Find and click element
    python test_ui_tars.py --stats                  # Show learning stats
    python test_ui_tars.py --adaptive "close icon"  # Use adaptive mode (default)
    python test_ui_tars.py --basic "close icon"     # Use basic mode (no learning)
"""

import sys
import time
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

console = Console()


def check_dependencies():
    """Check if MLX-VLM is available."""
    console.print("\n[bold cyan]🔍 Checking Dependencies[/bold cyan]")
    
    # Check MLX-VLM
    try:
        from mlx_vlm import load, generate
        console.print("  ✅ MLX-VLM available")
    except ImportError:
        console.print("  ❌ MLX-VLM not installed")
        console.print("     Install with: [yellow]pip install mlx-vlm[/yellow]")
        return False
    
    # Check PyAutoGUI
    try:
        import pyautogui
        w, h = pyautogui.size()
        console.print(f"  ✅ PyAutoGUI available (screen: {w}x{h})")
    except ImportError:
        console.print("  ❌ PyAutoGUI not installed")
        console.print("     Install with: [yellow]pip install pyautogui[/yellow]")
        return False
    
    # Check PIL
    try:
        from PIL import Image
        console.print("  ✅ Pillow available")
    except ImportError:
        console.print("  ❌ Pillow not installed")
        return False
    
    # Check LangGraph (optional but recommended)
    try:
        from langgraph.graph import StateGraph
        console.print("  ✅ LangGraph available (adaptive learning enabled)")
    except ImportError:
        console.print("  ⚠️ LangGraph not installed (adaptive learning disabled)")
        console.print("     Install with: [yellow]pip install langgraph langchain-core[/yellow]")
    
    return True


def load_ui_tars(use_adaptive: bool = True):
    """Load the UI-TARS localizer."""
    
    if use_adaptive:
        console.print("\n[bold cyan]⏳ Loading Adaptive Vision Localizer[/bold cyan]")
        console.print("  Mode: [green]Adaptive with LangGraph feedback loop[/green]")
        console.print("  Model: [yellow]mlx-community/UI-TARS-7B-SFT-4bit[/yellow]")
        
        try:
            from utils.vision_feedback_loop import AdaptiveVisionLocalizer
            
            start = time.time()
            localizer = AdaptiveVisionLocalizer()
            
            # Force load the underlying model
            if hasattr(localizer, '_base_localizer'):
                ui_tars = localizer._base_localizer._get_ui_tars()
                if ui_tars:
                    ui_tars._ensure_loaded()
            
            elapsed = time.time() - start
            console.print(f"  ✅ Adaptive localizer ready in {elapsed:.1f}s")
            
            # Show stats
            stats = localizer.get_stats()
            if stats["patterns_learned"] > 0:
                console.print(f"  📚 Loaded {stats['patterns_learned']} learned patterns from {stats['apps_learned']} apps")
            
            return localizer
            
        except Exception as e:
            console.print(f"  ⚠️ Adaptive mode failed: {e}")
            console.print("  Falling back to basic mode...")
    
    # Basic mode
    console.print("\n[bold cyan]⏳ Loading UI-TARS Model (Basic Mode)[/bold cyan]")
    console.print("  Model: [yellow]mlx-community/UI-TARS-7B-SFT-4bit[/yellow]")
    console.print("  (First run will download ~4GB model)")
    
    try:
        from utils.local_vision_localizer import UITARSLocalizer, UITARSConfig
        
        config = UITARSConfig(
            model_path="mlx-community/UI-TARS-7B-SFT-4bit",
            max_tokens=512,
            temperature=0.1,
            verbose=True
        )
        
        start = time.time()
        localizer = UITARSLocalizer(config)
        
        # Force load the model
        localizer._ensure_loaded()
        
        elapsed = time.time() - start
        console.print(f"  ✅ Model loaded in {elapsed:.1f}s")
        
        return localizer
        
    except Exception as e:
        console.print(f"  ❌ Failed to load: {e}")
        return None


def take_screenshot():
    """Capture current screen."""
    import pyautogui
    import tempfile
    import os
    
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    
    screenshot = pyautogui.screenshot()
    screenshot.save(path)
    
    return path


def find_element(localizer, description: str, click: bool = False, use_adaptive: bool = True):
    """Find an element using UI-TARS."""
    console.print(f"\n[bold cyan]🎯 Finding: [yellow]{description}[/yellow][/bold cyan]")
    
    # Take screenshot
    console.print("  📸 Taking screenshot...")
    screenshot_path = take_screenshot()
    
    # Find element - handle both adaptive and basic localizer
    console.print("  🔍 Analyzing with UI-TARS...")
    start = time.time()
    
    # Check if this is an adaptive localizer
    is_adaptive = hasattr(localizer, 'find_element') and hasattr(localizer, 'record_click_result')
    
    if is_adaptive:
        # Adaptive localizer - different signature
        result = localizer.find_element(
            element_description=description,
            image_path=screenshot_path,
            app_name="Test",
            task_context="Manual testing"
        )
    else:
        # Basic UITARSLocalizer
        result = localizer.find_element(
            image_path=screenshot_path,
            element_description=description,
            return_bbox=True
        )
    
    elapsed = (time.time() - start) * 1000
    
    # Display result
    if result.found:
        console.print(Panel(
            f"[green]✅ Found![/green]\n\n"
            f"  Coordinates: [bold]({result.x}, {result.y})[/bold]\n"
            f"  Confidence: {result.confidence:.0%}\n"
            f"  Method: {result.method}\n"
            f"  Latency: {elapsed:.0f}ms\n"
            f"  Reasoning: {result.reasoning[:100] if result.reasoning else 'N/A'}...",
            title="Result",
            border_style="green"
        ))
        
        if result.bounding_box:
            x1, y1, x2, y2 = result.bounding_box
            console.print(f"  Bounding box: ({x1}, {y1}) → ({x2}, {y2})")
        
        # Click if requested
        if click:
            console.print(f"\n  🖱️ Clicking at ({result.x}, {result.y})...")
            import pyautogui
            pyautogui.click(result.x, result.y)
            console.print("  ✅ Clicked!")
            
            # Ask for feedback if adaptive
            if is_adaptive:
                time.sleep(0.5)  # Let the click take effect
                worked = Confirm.ask("  Did the click work as expected?", default=True)
                localizer.record_click_result(description, worked)
                if worked:
                    console.print("  📝 [green]Recorded as successful![/green]")
                else:
                    console.print("  📝 [yellow]Recorded as failed - will try differently next time[/yellow]")
            
    else:
        console.print(Panel(
            f"[red]❌ Not Found[/red]\n\n"
            f"  Latency: {elapsed:.0f}ms\n"
            f"  Reasoning: {result.reasoning}",
            title="Result",
            border_style="red"
        ))
        
        # Record failure for adaptive learning
        if is_adaptive:
            localizer.record_click_result(description, False)
    
    # Cleanup
    import os
    os.unlink(screenshot_path)
    
    return result


def show_learning_stats(localizer):
    """Show learning statistics."""
    if not hasattr(localizer, 'get_stats'):
        console.print("[yellow]Stats only available in adaptive mode[/yellow]")
        return
    
    stats = localizer.get_stats()
    
    console.print(Panel(
        f"[bold]Vision Learning Statistics[/bold]\n\n"
        f"  Apps Learned: {stats['apps_learned']}\n"
        f"  Patterns Learned: {stats['patterns_learned']}\n"
        f"  Recent Attempts: {stats['recent_attempts']}",
        title="📊 Learning Stats",
        border_style="cyan"
    ))
    
    if stats.get('top_patterns'):
        table = Table(title="Top Learned Patterns")
        table.add_column("Element Type", style="cyan")
        table.add_column("Success Rate", style="green")
        table.add_column("Attempts", style="yellow")
        
        for pattern in stats['top_patterns']:
            table.add_row(
                pattern['type'],
                f"{pattern['success_rate']:.0%}",
                str(pattern['attempts'])
            )
        
        console.print(table)


def interactive_mode(localizer, use_adaptive: bool = True):
    """Run interactive element finding."""
    is_adaptive = hasattr(localizer, 'record_click_result')
    mode_str = "[green]Adaptive[/green]" if is_adaptive else "[yellow]Basic[/yellow]"
    
    console.print(f"\n[bold cyan]🎮 Interactive Mode ({mode_str})[/bold cyan]")
    console.print("  Type element descriptions to find them on screen.")
    console.print("  Prefix with 'click:' to also click the element.")
    if is_adaptive:
        console.print("  Type 'stats' to see learning statistics.")
    console.print("  Type 'quit' to exit.\n")
    
    while True:
        try:
            query = Prompt.ask("[bold blue]Find element[/bold blue]")
            
            if query.lower() in ['quit', 'exit', 'q']:
                console.print("👋 Goodbye!")
                break
            
            if query.lower() == 'stats':
                show_learning_stats(localizer)
                continue
            
            if not query.strip():
                continue
            
            # Check for click prefix
            click = False
            if query.lower().startswith('click:'):
                click = True
                query = query[6:].strip()
            
            find_element(localizer, query, click=click, use_adaptive=use_adaptive)
            
        except KeyboardInterrupt:
            console.print("\n👋 Goodbye!")
            break


def main():
    parser = argparse.ArgumentParser(
        description="Test UI-TARS element localization with adaptive learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_ui_tars.py                          # Interactive mode (adaptive)
  python test_ui_tars.py "search button"          # Find element
  python test_ui_tars.py --click "send button"    # Find and click
  python test_ui_tars.py --stats                  # Show learning stats
  python test_ui_tars.py --basic "close icon"     # Use basic mode (no learning)
  python test_ui_tars.py "the blue submit button at the bottom"
        """
    )
    parser.add_argument(
        "element",
        nargs="?",
        help="Element description to find"
    )
    parser.add_argument(
        "--click", "-c",
        action="store_true",
        help="Click the element after finding it"
    )
    parser.add_argument(
        "--basic", "-b",
        action="store_true",
        help="Use basic mode without adaptive learning"
    )
    parser.add_argument(
        "--stats", "-s",
        action="store_true",
        help="Show learning statistics"
    )
    
    args = parser.parse_args()
    
    use_adaptive = not args.basic
    mode_text = "Adaptive Learning" if use_adaptive else "Basic"
    
    console.print(Panel(
        f"[bold]UI-TARS MLX Tester[/bold]\n"
        f"Local semantic UI element localization on Apple Silicon\n"
        f"Mode: [{'green' if use_adaptive else 'yellow'}]{mode_text}[/{'green' if use_adaptive else 'yellow'}]",
        title="🎯 Test UI-TARS",
        border_style="cyan"
    ))
    
    # Check dependencies
    if not check_dependencies():
        console.print("\n[red]❌ Missing dependencies. Please install them first.[/red]")
        sys.exit(1)
    
    # Load model
    localizer = load_ui_tars(use_adaptive=use_adaptive)
    if not localizer:
        console.print("\n[red]❌ Failed to load UI-TARS model.[/red]")
        sys.exit(1)
    
    # Stats only mode
    if args.stats:
        show_learning_stats(localizer)
        sys.exit(0)
    
    # Run mode
    if args.element:
        # Single element mode
        find_element(localizer, args.element, click=args.click, use_adaptive=use_adaptive)
    else:
        # Interactive mode
        interactive_mode(localizer, use_adaptive=use_adaptive)


if __name__ == "__main__":
    main()
