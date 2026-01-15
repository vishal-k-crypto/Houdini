#!/usr/bin/env python3
"""
Test script for OmniParser V2 - YOLO + Florence-2 Vision

Run this to verify your OmniParser setup:
    python test_omniparser.py
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
    
    # Test PyTorch
    try:
        import torch
        device = "MPS" if torch.backends.mps.is_available() else "CPU"
        if torch.cuda.is_available():
            device = "CUDA"
        results["PyTorch"] = ("✅", f"Available ({device})")
    except ImportError as e:
        results["PyTorch"] = ("❌", f"pip install torch: {e}")
    
    # Test ultralytics (YOLO)
    try:
        from ultralytics import YOLO
        results["Ultralytics (YOLO)"] = ("✅", "Available")
    except ImportError as e:
        results["Ultralytics (YOLO)"] = ("❌", f"pip install ultralytics: {e}")
    
    # Test transformers (Florence-2)
    try:
        from transformers import AutoProcessor, AutoModelForCausalLM
        results["Transformers (Florence-2)"] = ("✅", "Available")
    except ImportError as e:
        results["Transformers (Florence-2)"] = ("⚠️", f"Optional: pip install transformers: {e}")
    
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
    
    # Check if core deps available
    core_available = all(
        status == "✅"
        for name, (status, _) in results.items()
        if name not in ["Transformers (Florence-2)"]  # Optional
    )
    
    return core_available


def test_client_init():
    """Test OmniParserClient initialization."""
    console.print("\n[bold cyan]2. Testing OmniParserClient Initialization[/bold cyan]")
    
    try:
        from src.utils.omniparser_client import OmniParserClient, OMNIPARSER_AVAILABLE
        
        if not OMNIPARSER_AVAILABLE:
            console.print("  [yellow]⚠️ OmniParser dependencies not available[/yellow]")
            return None
        
        start = time.time()
        client = OmniParserClient(
            enable_captioning=False,  # Skip Florence-2 for quick test
            lazy_load=True
        )
        elapsed = (time.time() - start) * 1000
        
        console.print(f"  ✅ Initialized in {elapsed:.1f}ms")
        console.print(f"  Device: {client.device}")
        console.print(f"  Captioning: {'✅' if client.enable_captioning else '❌ (disabled)'}")
        
        return client
        
    except Exception as e:
        console.print(f"  [red]❌ Failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return None


def test_screen_parser_init():
    """Test OmniParserScreenParser with Retina scaling."""
    console.print("\n[bold cyan]3. Testing OmniParserScreenParser (Retina Scaling)[/bold cyan]")
    
    try:
        from src.utils.omniparser_screen_parser import (
            OmniParserScreenParser,
            OMNIPARSER_AVAILABLE
        )
        
        if not OMNIPARSER_AVAILABLE:
            console.print("  [yellow]⚠️ OmniParser not available[/yellow]")
            return None
        
        start = time.time()
        parser = OmniParserScreenParser(
            enable_captioning=False,
            lazy_load=True
        )
        elapsed = (time.time() - start) * 1000
        
        console.print(f"  ✅ Initialized in {elapsed:.1f}ms")
        console.print(f"  Scale factor: {parser.scale_factor} (Retina: {parser.scale_factor == 2.0})")
        console.print(f"  Screen size: {parser.screen_width}x{parser.screen_height}")
        
        return parser
        
    except Exception as e:
        console.print(f"  [red]❌ Failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return None


def test_retina_scaling(parser):
    """Test Retina coordinate scaling."""
    console.print("\n[bold cyan]4. Testing Retina Coordinate Scaling[/bold cyan]")
    
    if not parser:
        console.print("  [yellow]⚠️ Parser not available, skipping[/yellow]")
        return
    
    # Test cases: (pixel_x, pixel_y) -> expected (scaled_x, scaled_y)
    test_coords = [
        (0, 0),
        (100, 200),
        (1920, 1080),
        (3840, 2160),  # 4K retina
    ]
    
    table = Table(title="Retina Scaling Test")
    table.add_column("Pixel Coords", style="cyan")
    table.add_column("Scaled Coords")
    table.add_column("Scale Factor")
    
    for px, py in test_coords:
        sx, sy = parser._scale_coordinates(px, py)
        table.add_row(
            f"({px}, {py})",
            f"({sx}, {sy})",
            f"÷{parser.scale_factor}"
        )
    
    console.print(table)


def test_element_detection(parser):
    """Test element detection on current screen."""
    console.print("\n[bold cyan]5. Testing Element Detection[/bold cyan]")
    
    if not parser:
        console.print("  [yellow]⚠️ Parser not available, skipping[/yellow]")
        return
    
    console.print("  📸 Taking screenshot...")
    console.print("  ⏳ Running YOLO detection (first run downloads model)...")
    
    try:
        start = time.time()
        elements = parser.detect_all_elements(confidence_threshold=0.3)
        elapsed = time.time() - start
        
        console.print(f"  ✅ Detected {len(elements)} elements in {elapsed:.1f}s")
        
        if elements:
            table = Table(title="Top 5 Detected Elements")
            table.add_column("Label", style="cyan")
            table.add_column("Confidence")
            table.add_column("Position (scaled)")
            table.add_column("Size")
            
            for elem in elements[:5]:
                table.add_row(
                    elem.label[:20],
                    f"{elem.confidence:.0%}",
                    f"({elem.x}, {elem.y})",
                    f"{elem.bbox[2]-elem.bbox[0]}x{elem.bbox[3]-elem.bbox[1]}" if elem.bbox else "N/A"
                )
            
            console.print(table)
        
    except Exception as e:
        console.print(f"  [red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()


def test_find_element(parser):
    """Test finding specific elements."""
    console.print("\n[bold cyan]6. Testing Element Finding[/bold cyan]")
    
    if not parser:
        console.print("  [yellow]⚠️ Parser not available, skipping[/yellow]")
        return
    
    test_queries = [
        "button",
        "icon",
        "text",
    ]
    
    for query in test_queries:
        try:
            start = time.time()
            result = parser.find_element(query, confidence_threshold=0.2)
            elapsed = (time.time() - start) * 1000
            
            if result.found:
                console.print(
                    f"  ✅ '{query}': ({result.x}, {result.y}) "
                    f"[{result.label}] {result.confidence:.0%} {elapsed:.0f}ms"
                )
            else:
                console.print(f"  ⚠️ '{query}': Not found {elapsed:.0f}ms")
                
        except Exception as e:
            console.print(f"  [red]❌ '{query}': {e}[/red]")


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold green]OmniParser V2 Test Suite[/bold green]\n"
        "Testing YOLO + Florence-2 Vision with Retina Scaling",
        border_style="green"
    ))
    
    # Test imports
    if not test_imports():
        console.print("\n[red]❌ Core dependencies missing.[/red]")
        console.print("Install: pip install ultralytics torch")
        return
    
    # Test client initialization
    client = test_client_init()
    
    # Test screen parser
    parser = test_screen_parser_init()
    
    # Test Retina scaling
    test_retina_scaling(parser)
    
    # Test element detection
    test_element_detection(parser)
    
    # Test finding elements
    test_find_element(parser)
    
    console.print("\n" + "=" * 60)
    console.print("[bold green]✅ Tests Complete![/bold green]")
    console.print("\n[cyan]Usage example:[/cyan]")
    console.print("""
from src.utils.omniparser_screen_parser import OmniParserScreenParser

parser = OmniParserScreenParser()
result = parser.find_element("search button")

if result.found:
    print(f"Found at ({result.x}, {result.y})")
    # Coordinates are already Retina-scaled for PyAutoGUI
    import pyautogui
    pyautogui.click(result.x, result.y)
""")


if __name__ == "__main__":
    main()
