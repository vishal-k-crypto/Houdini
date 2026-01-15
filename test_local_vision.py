#!/usr/bin/env python3
"""
Test script for LocalVisionLocalizer - Hybrid Apple Vision + UI-TARS MLX.

Run this to verify your local vision setup:
    python test_local_vision.py
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def test_imports():
    """Test that all required imports are available."""
    console.print("\n[bold cyan]1. Testing Imports[/bold cyan]")
    
    results = {}
    
    # Test pyobjc Vision
    try:
        import Vision
        import Quartz
        from Cocoa import NSURL
        results["Apple Vision Framework"] = ("✅", "Available")
    except ImportError as e:
        results["Apple Vision Framework"] = ("❌", f"pip install pyobjc-framework-Vision: {e}")
    
    # Test MLX-VLM
    try:
        from mlx_vlm import load, generate
        results["MLX-VLM"] = ("✅", "Available")
    except ImportError as e:
        results["MLX-VLM"] = ("⚠️", f"Optional - pip install mlx-vlm: {e}")
    
    # Test pyautogui
    try:
        import pyautogui
        size = pyautogui.size()
        results["PyAutoGUI"] = ("✅", f"Screen: {size[0]}x{size[1]}")
    except ImportError as e:
        results["PyAutoGUI"] = ("❌", f"pip install pyautogui: {e}")
    
    # Test PIL
    try:
        from PIL import Image
        results["Pillow"] = ("✅", "Available")
    except ImportError as e:
        results["Pillow"] = ("❌", f"pip install pillow: {e}")
    
    # Display results
    table = Table(title="Import Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")
    
    for name, (status, detail) in results.items():
        table.add_row(name, status, detail)
    
    console.print(table)
    
    all_required = all(
        status == "✅" 
        for name, (status, _) in results.items() 
        if name not in ["MLX-VLM"]  # MLX-VLM is optional
    )
    
    return all_required


def test_localizer_init():
    """Test LocalVisionLocalizer initialization."""
    console.print("\n[bold cyan]2. Testing LocalVisionLocalizer Initialization[/bold cyan]")
    
    try:
        from src.utils.local_vision_localizer import LocalVisionLocalizer
        
        start = time.time()
        localizer = LocalVisionLocalizer(lazy_load_ui_tars=True)
        elapsed = (time.time() - start) * 1000
        
        console.print(f"  ✅ Initialized in {elapsed:.1f}ms")
        console.print(f"  Apple Vision: {'✅' if localizer.enable_apple_vision else '❌'}")
        console.print(f"  UI-TARS: {'✅ (lazy)' if localizer.enable_ui_tars else '❌'}")
        
        return localizer
        
    except Exception as e:
        console.print(f"  [red]❌ Failed to initialize: {e}[/red]")
        import traceback
        traceback.print_exc()
        return None


def test_apple_vision(localizer):
    """Test Apple Vision rectangle and text detection."""
    console.print("\n[bold cyan]3. Testing Apple Vision Detection[/bold cyan]")
    
    if not localizer or not localizer.enable_apple_vision:
        console.print("  [yellow]⚠️ Apple Vision not available, skipping[/yellow]")
        return
    
    try:
        import pyautogui
        import tempfile
        import os
        
        # Take screenshot
        console.print("  📸 Taking screenshot...")
        screenshot = pyautogui.screenshot()
        
        # Save to temp file
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        screenshot.save(path)
        
        console.print(f"  💾 Saved to: {path}")
        
        # Test rectangle detection
        console.print("  🔍 Detecting rectangles...")
        start = time.time()
        rectangles = localizer.vision_detector.detect_rectangles(path)
        elapsed = (time.time() - start) * 1000
        
        console.print(f"  ✅ Found {len(rectangles)} rectangles in {elapsed:.1f}ms")
        
        if rectangles:
            # Show top 5
            table = Table(title="Top 5 Rectangles")
            table.add_column("Pos", style="cyan")
            table.add_column("Size")
            table.add_column("Center")
            table.add_column("Confidence")
            
            for r in rectangles[:5]:
                table.add_row(
                    f"({r.x}, {r.y})",
                    f"{r.width}x{r.height}",
                    f"{r.center}",
                    f"{r.confidence:.2f}"
                )
            
            console.print(table)
        
        # Test text detection
        console.print("\n  📝 Detecting text...")
        start = time.time()
        text_regions = localizer.vision_detector.detect_text_regions(path)
        elapsed = (time.time() - start) * 1000
        
        console.print(f"  ✅ Found {len(text_regions)} text regions in {elapsed:.1f}ms")
        
        if text_regions:
            # Show first 5
            table = Table(title="Sample Text Regions")
            table.add_column("Text", style="cyan", max_width=40)
            table.add_column("Position")
            table.add_column("Confidence")
            
            for t in text_regions[:5]:
                table.add_row(
                    t["text"][:40],
                    f"({t['center'][0]}, {t['center'][1]})",
                    f"{t['confidence']:.2f}"
                )
            
            console.print(table)
        
        # Cleanup
        os.remove(path)
        
    except Exception as e:
        console.print(f"  [red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()


def test_element_finding(localizer):
    """Test finding elements by description."""
    console.print("\n[bold cyan]4. Testing Element Finding[/bold cyan]")
    
    if not localizer:
        console.print("  [yellow]⚠️ Localizer not available, skipping[/yellow]")
        return
    
    test_queries = [
        "search field",
        "close button",
        "menu",
    ]
    
    console.print("  Testing element finding (Apple Vision only, UI-TARS skipped)...")
    
    for query in test_queries:
        try:
            start = time.time()
            # Force skip UI-TARS for quick test
            result = localizer.find_element(
                query, 
                min_confidence=0.3,
                force_ui_tars=False
            )
            elapsed = (time.time() - start) * 1000
            
            if result.found:
                console.print(
                    f"  ✅ '{query}': ({result.x}, {result.y}) "
                    f"[{result.method}] {elapsed:.0f}ms"
                )
            else:
                console.print(
                    f"  ⚠️ '{query}': Not found [{result.method}] {elapsed:.0f}ms"
                )
                
        except Exception as e:
            console.print(f"  [red]❌ '{query}': Error - {e}[/red]")


def test_ui_tars(localizer):
    """Test UI-TARS semantic grounding (optional)."""
    console.print("\n[bold cyan]5. Testing UI-TARS (Optional)[/bold cyan]")
    
    if not localizer or not localizer.enable_ui_tars:
        console.print("  [yellow]⚠️ UI-TARS not available[/yellow]")
        console.print("  To enable: pip install mlx-vlm")
        console.print("  Then download model: mlx-community/UI-TARS-7B-SFT-4bit")
        return
    
    try:
        console.print("  ⏳ Loading UI-TARS model (first time may take a minute)...")
        
        start = time.time()
        result = localizer.find_element(
            "the search input field",
            force_ui_tars=True
        )
        elapsed = time.time() - start
        
        if result.found:
            console.print(
                f"  ✅ Found: ({result.x}, {result.y}) "
                f"confidence={result.confidence:.2f} in {elapsed:.1f}s"
            )
        else:
            console.print(f"  ⚠️ Not found: {result.reasoning}")
            
    except Exception as e:
        console.print(f"  [red]❌ Error: {e}[/red]")


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold green]Local Vision Localizer Test Suite[/bold green]\n"
        "Testing Hybrid Apple Vision + UI-TARS MLX",
        border_style="green"
    ))
    
    # Test imports
    if not test_imports():
        console.print("\n[red]❌ Required imports missing. Install dependencies first.[/red]")
        console.print("Run: pip install pyobjc-framework-Vision")
        return
    
    # Test initialization
    localizer = test_localizer_init()
    
    # Test Apple Vision
    test_apple_vision(localizer)
    
    # Test element finding
    test_element_finding(localizer)
    
    # Test UI-TARS (optional)
    test_ui_tars(localizer)
    
    console.print("\n" + "=" * 60)
    console.print("[bold green]✅ Tests Complete![/bold green]")
    console.print("\n[cyan]Usage example:[/cyan]")
    console.print("""
from src.utils.local_vision_localizer import LocalVisionLocalizer

localizer = LocalVisionLocalizer()
result = localizer.find_element("the search button")

if result.found:
    print(f"Found at ({result.x}, {result.y})")
    # Or click directly:
    localizer.click_element("the search button")
""")


if __name__ == "__main__":
    main()
