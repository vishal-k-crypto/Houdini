"""
Screen Understanding Module
Converts screenshots to text descriptions for LLM consumption.
Uses OCR and accessibility APIs.
"""

import io
import subprocess
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from .logging import logger

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("pytesseract/PIL not available. OCR disabled.")


def get_accessibility_tree() -> str:
    """
    Get macOS accessibility tree using AppleScript.
    Returns a text description of visible UI elements.
    """
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        set appName to name of frontApp
        set windowInfo to ""
        
        try
            set frontWindow to first window of frontApp
            set windowTitle to name of frontWindow
            set windowInfo to "Window: " & windowTitle
        end try
        
        return "Active App: " & appName & "\n" & windowInfo
    end tell
    '''
    
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Accessibility tree failed: {e}")
    
    return "Could not get accessibility info"


def ocr_screenshot(screenshot_bytes: bytes) -> Dict[str, any]:
    """
    Extract text and positions from screenshot using Tesseract OCR.
    
    Returns:
        Dict with 'text' (full text), 'elements' (list of positioned text)
    """
    if not OCR_AVAILABLE:
        return {"text": "", "elements": []}
    
    try:
        image = Image.open(io.BytesIO(screenshot_bytes))
        
        # Get full text
        full_text = pytesseract.image_to_string(image)
        
        # Get positioned elements
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        elements = []
        for i, text in enumerate(data["text"]):
            if text.strip():
                elements.append({
                    "text": text,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                    "confidence": data["conf"][i]
                })
        
        return {
            "text": full_text.strip(),
            "elements": elements
        }
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return {"text": "", "elements": []}


def format_screen_description(
    ocr_result: Dict,
    accessibility_info: str = "",
    include_coordinates: bool = True
) -> str:
    """
    Format screen information as a text description for the LLM.
    """
    lines = []
    
    # Add accessibility info
    if accessibility_info:
        lines.append("=== SYSTEM INFO ===")
        lines.append(accessibility_info)
        lines.append("")
    
    # Add OCR text
    if ocr_result.get("text"):
        lines.append("=== SCREEN TEXT (OCR) ===")
        lines.append(ocr_result["text"])
        lines.append("")
    
    # Add positioned elements for grounding
    if include_coordinates and ocr_result.get("elements"):
        lines.append("=== TEXT ELEMENTS WITH POSITIONS ===")
        lines.append("Format: [text] at (x, y)")
        
        # Group by approximate vertical position (lines)
        sorted_elements = sorted(ocr_result["elements"], key=lambda e: (e["y"] // 20, e["x"]))
        
        for elem in sorted_elements[:50]:  # Limit to avoid token overflow
            if elem["confidence"] > 30:  # Filter low confidence
                cx = elem["x"] + elem["width"] // 2
                cy = elem["y"] + elem["height"] // 2
                lines.append(f'  "{elem["text"]}" at ({cx}, {cy})')
    
    return "\n".join(lines)


def screenshot_to_context(screenshot_bytes: bytes) -> str:
    """
    Main function: Convert screenshot to LLM-readable context.
    
    This replaces the need for vision models by providing
    a text-based representation of the screen.
    """
    # Get accessibility info
    accessibility_info = get_accessibility_tree()
    
    # Run OCR
    ocr_result = ocr_screenshot(screenshot_bytes)
    
    # Format for LLM
    context = format_screen_description(
        ocr_result=ocr_result,
        accessibility_info=accessibility_info,
        include_coordinates=True
    )
    
    return context


def find_element_coordinates(
    screenshot_bytes: bytes,
    element_description: str
) -> Optional[Tuple[int, int]]:
    """
    Find approximate coordinates of an element by matching OCR text.
    
    Args:
        screenshot_bytes: Screenshot as bytes
        element_description: Text to search for (e.g., "Submit button")
        
    Returns:
        (x, y) center coordinates or None if not found
    """
    ocr_result = ocr_screenshot(screenshot_bytes)
    
    search_terms = element_description.lower().split()
    
    best_match = None
    best_score = 0
    
    for elem in ocr_result.get("elements", []):
        elem_text = elem["text"].lower()
        
        # Score based on matching words
        score = sum(1 for term in search_terms if term in elem_text)
        
        if score > best_score:
            best_score = score
            best_match = elem
    
    if best_match:
        cx = best_match["x"] + best_match["width"] // 2
        cy = best_match["y"] + best_match["height"] // 2
        return (cx, cy)
    
    return None
