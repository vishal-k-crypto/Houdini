"""
TinyClick Client - Fast Pixel-Precise Click Prediction

Samsung's TinyClick model for GUI automation:
- 0.27B parameters (lightweight)
- ~350-500ms warm inference on MPS
- Fine-tuned Florence-2 for precise click coordinate prediction
- Outperforms GPT-4V on Screenspot (73.8%) and OmniAct (58.3%) benchmarks

This client uses subprocess to call tinyclick_server.py in the separate
.tinyclick-venv environment (required due to transformers version conflicts).

Usage:
    from src.utils.tinyclick_client import predict_click, predict_click_with_result
    
    # Quick usage
    x, y = predict_click("click the search button")
    
    # Full result
    result = predict_click_with_result("click the first video thumbnail")
    # result = {"success": True, "x": 430, "y": 250, "confidence": 0.85, "inference_ms": 450}
"""

import os
import json
import subprocess
import logging
from typing import Optional, Tuple, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from ..replay.execution_logger import log_llm_interaction
except ImportError:
    # Fallback if logger not available
    def log_llm_interaction(*args, **kwargs): pass

# Paths
HOUDINI_ROOT = Path(__file__).parent.parent.parent
TINYCLICK_VENV = HOUDINI_ROOT / ".tinyclick-venv"
TINYCLICK_PYTHON = TINYCLICK_VENV / "bin" / "python3"
TINYCLICK_SERVER = Path(__file__).parent / "tinyclick_server.py"


def is_available() -> bool:
    """Check if TinyClick venv and server are available."""
    return TINYCLICK_PYTHON.exists() and TINYCLICK_SERVER.exists()


TINYCLICK_AVAILABLE = is_available()


def predict_click_with_result(
    element_description: str,
    screenshot_path: Optional[str] = None,
    task_context: str = "",
    timeout: float = 60.0
) -> Dict:
    """
    Predict click coordinates using TinyClick in separate venv.
    
    Args:
        element_description: What to click, e.g., "search button"
        screenshot_path: Optional path to screenshot (captures if None)
        task_context: Optional additional context (unused for now)
        timeout: Max time to wait for prediction
    
    Returns:
        {
            "success": bool,
            "x": int,
            "y": int,
            "confidence": float,
            "inference_ms": float,
            "error": str or None
        }
    """
    if not TINYCLICK_AVAILABLE:
        return {
            "success": False,
            "x": 0,
            "y": 0,
            "confidence": 0.0,
            "inference_ms": 0,
            "error": "TinyClick venv not found. Run: python3 -m venv .tinyclick-venv && .tinyclick-venv/bin/pip install transformers==4.48.0 torch accelerate pillow einops timm rich"
        }
    
    try:
        # Build command
        cmd = [str(TINYCLICK_PYTHON), str(TINYCLICK_SERVER), element_description]
        if screenshot_path:
            cmd.append(screenshot_path)
        
        logger.info(f"TinyClick: Predicting '{element_description}'...")
        
        # Call server in separate venv
        # Use home directory as cwd to avoid project's logging.py shadowing stdlib
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path.home())
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "x": 0,
                "y": 0,
                "confidence": 0.0,
                "inference_ms": 0,
                "error": f"TinyClick server error: {result.stderr}"
            }
        
        # Parse JSON output
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                logger.info(f"TinyClick: Found at ({output['x']}, {output['y']}) in {output.get('inference_ms', 0):.0f}ms")
                
            # Log to execution logger for training data
            log_llm_interaction(
                component="tinyclick",
                prompt=f"Element: {element_description} | Context: {task_context}",
                response=json.dumps(output),
                model="tinyclick-florence2",
                duration_ms=output.get("inference_ms", 0)
            )
            
            return output
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "x": 0,
                "y": 0,
                "confidence": 0.0,
                "inference_ms": 0,
                "error": f"Invalid JSON from TinyClick: {result.stdout[:200]}"
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "x": 0,
            "y": 0,
            "confidence": 0.0,
            "inference_ms": timeout * 1000,
            "error": f"TinyClick timed out after {timeout}s"
        }
    except Exception as e:
        return {
            "success": False,
            "x": 0,
            "y": 0,
            "confidence": 0.0,
            "inference_ms": 0,
            "error": str(e)
        }


def predict_click(
    element_description: str,
    screenshot_path: Optional[str] = None
) -> Tuple[int, int]:
    """
    Quick function to predict click coordinates.
    
    Args:
        element_description: What to click, e.g., "search button"
        screenshot_path: Optional path to screenshot
    
    Returns:
        (x, y) tuple of pixel coordinates
    
    Raises:
        RuntimeError if prediction fails
    """
    result = predict_click_with_result(element_description, screenshot_path)
    
    if result["success"]:
        return (result["x"], result["y"])
    else:
        raise RuntimeError(f"TinyClick prediction failed: {result['error']}")
