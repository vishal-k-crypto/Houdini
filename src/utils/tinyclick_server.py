#!/usr/bin/env python3
"""
TinyClick Server Script - Runs in the .tinyclick-venv environment

This script is called via subprocess by the main agent to leverage
the separate virtual environment with compatible transformers version.

Usage:
    python3 tinyclick_server.py "click on search button" [screenshot_path]
    
Output (JSON):
    {"success": true, "x": 120, "y": 350, "confidence": 0.85, "inference_ms": 450}
"""

# CRITICAL: Clean sys.path to prevent project's logging.py from shadowing stdlib
import sys
# Remove only the project's src/utils directory (not the venv packages)
sys.path = [p for p in sys.path if not (p.endswith('/src/utils') or p.endswith('/src') or '/houdini-agent/src' in p)]

import os
import json
import time
import subprocess
import tempfile
from pathlib import Path

# Model configuration
MODEL_ID = "Krystianz/TinyClick"
CACHE_DIR = Path.home() / ".cache" / "houdini" / "tinyclick"

# Lazy-loaded globals
_model = None
_processor = None
_device = None


def get_device():
    """Get PyTorch device."""
    global _device
    if _device is None:
        import torch
        if torch.backends.mps.is_available():
            _device = "mps"
        elif torch.cuda.is_available():
            _device = "cuda"
        else:
            _device = "cpu"
    return _device


def load_model():
    """Load TinyClick model (cached after first call)."""
    global _model, _processor
    
    if _model is not None and _processor is not None:
        return _model, _processor
    
    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM
    
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    device = get_device()
    
    _processor = AutoProcessor.from_pretrained(
        MODEL_ID, cache_dir=str(CACHE_DIR), trust_remote_code=True
    )
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, cache_dir=str(CACHE_DIR), trust_remote_code=True
    )
    _model = _model.to(device).eval()
    
    return _model, _processor


def capture_screenshot():
    """Capture screen to temp file (cross-platform)."""
    import platform
    
    system = platform.system()
    if system == "Darwin":  # macOS
        fd, path = tempfile.mkstemp(suffix=".png", prefix="tinyclick_")
        os.close(fd)
        subprocess.run(["screencapture", "-x", path], check=True, capture_output=True)
        return path
    elif system == "Linux":
        # For scrot, let it create its own file
        path = tempfile.mktemp(suffix=".png", prefix="tinyclick_")
        try:
            # scrot needs DISPLAY set and creates file itself
            env = os.environ.copy()
            if "DISPLAY" not in env:
                env["DISPLAY"] = ":99"
            result = subprocess.run(
                ["scrot", path], 
                check=True, 
                capture_output=True,
                env=env
            )
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return path
            else:
                raise RuntimeError(f"scrot created empty file: {path}")
        except (FileNotFoundError, subprocess.CalledProcessError, RuntimeError) as e:
            # Fallback to pyautogui
            try:
                import pyautogui
                # Ensure pyautogui can access the display
                os.environ.setdefault("DISPLAY", ":99")
                screenshot = pyautogui.screenshot()
                fd, path = tempfile.mkstemp(suffix=".png", prefix="tinyclick_")
                os.close(fd)
                screenshot.save(path)
                return path
            except Exception as e2:
                raise RuntimeError(f"No screenshot tool available. scrot: {e}, pyautogui: {e2}")
    else:
        # Fallback for Windows or other
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            fd, path = tempfile.mkstemp(suffix=".png", prefix="tinyclick_")
            os.close(fd)
            screenshot.save(path)
            return path
        except Exception:
            raise RuntimeError("No screenshot tool available")


def parse_coordinates(output_text: str, width: int, height: int):
    """Parse <loc_X><loc_Y> format to pixel coordinates."""
    import re
    match = re.search(r"<loc_(\d+)><loc_(\d+)>", output_text)
    if match:
        norm_x, norm_y = int(match.group(1)), int(match.group(2))
        x = int((norm_x / 1000) * width)
        y = int((norm_y / 1000) * height)
        return x, y
    return None


def predict(command: str, screenshot_path: str = None):
    """Run TinyClick prediction."""
    import torch
    from PIL import Image
    
    start_time = time.time()
    
    try:
        model, processor = load_model()
        device = get_device()
        
        # Screenshot
        temp_screenshot = False
        if screenshot_path is None:
            screenshot_path = capture_screenshot()
            temp_screenshot = True
        
        img = Image.open(screenshot_path).convert("RGB")
        width, height = img.size
        
        # Prepare prompt
        prompt = f"what to do to execute the command? {command}".lower()
        
        inputs = processor(images=img, text=prompt, return_tensors="pt", do_resize=True)
        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
        
        # Inference
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=128, do_sample=False)
        
        result_text = processor.batch_decode(outputs, skip_special_tokens=False)[0]
        inference_ms = (time.time() - start_time) * 1000
        
        # Clean up
        if temp_screenshot and os.path.exists(screenshot_path):
            os.remove(screenshot_path)
        
        # Parse coordinates
        coords = parse_coordinates(result_text, width, height)
        
        if coords:
            return {
                "success": True,
                "x": coords[0],
                "y": coords[1],
                "confidence": 0.85,
                "inference_ms": inference_ms,
                "raw_output": result_text
            }
        else:
            return {
                "success": False,
                "x": 0,
                "y": 0,
                "confidence": 0.0,
                "inference_ms": inference_ms,
                "error": f"Could not parse coordinates from: {result_text}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "x": 0,
            "y": 0,
            "confidence": 0.0,
            "inference_ms": (time.time() - start_time) * 1000,
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: tinyclick_server.py command [screenshot_path]"}))
        sys.exit(1)
    
    command = sys.argv[1]
    screenshot_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    result = predict(command, screenshot_path)
    print(json.dumps(result))
