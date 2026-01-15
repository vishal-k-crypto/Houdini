#!/usr/bin/env python3
"""Test VLM functionality directly using CLI approach"""

import pyautogui
import subprocess
import tempfile
import os

# Take screenshot
print("Taking screenshot...")
screenshot = pyautogui.screenshot()

# Save to temp file
with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
    screenshot.save(tmp, format='PNG')
    tmp_path = tmp.name

print(f"Screenshot saved to: {tmp_path}")

# Simple test prompt  
prompt = """Look at this screenshot and find the search box or input field.
Return ONLY valid JSON (no explanation):
{"found": true, "x": 100, "y": 80, "element": "search field", "confidence": 0.9, "match_probability": 0.9, "reasoning": "found at top left"}"""

print('Calling Ollama VLM with image file...')
try:
    result = subprocess.run(
        ["ollama", "run", "qwen3-vl:235b-cloud", prompt, tmp_path],
        capture_output=True,
        text=True,
        timeout=180
    )
    print(f"Return code: {result.returncode}")
    print(f"Response:\n{result.stdout[:1000]}")
    if result.stderr:
        print(f"Stderr: {result.stderr[:500]}")
except subprocess.TimeoutExpired:
    print("Timeout!")
except Exception as e:
    print(f"Error: {e}")
finally:
    os.unlink(tmp_path)
    print("Cleaned up temp file")
