import re
import math
import platform
import subprocess
import time
import tempfile
from typing import List, Dict, Tuple, Optional, Any
from pathlib import Path

# Optional imports for local execution
try:
    import pyautogui
    # Fail-safe mode
    pyautogui.FAILSAFE = True
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from ..utils.logging import logger
from ..utils.gemini_client import GeminiCLI

def agent_action(func):
    """Decorator to mark methods as available agent actions."""
    func.is_agent_action = True
    return func

class ACI:
    """
    Agent-Computer Interface (ACI).
    Translates high-level actions/descriptions to low-level execution (PyAutoGUI).
    Based on Agent-S OSWorldACI.
    """
    def __init__(self, grounding_model: GeminiCLI, platform_name: str = platform.system().lower()):
        self.grounding_model = grounding_model
        self.platform = platform_name
        self.obs = None  # Current observation (dict with 'screenshot')
        self.notes = []  # Knowledge/notes buffer

        # Screen dimensions (default, update per obs if possible)
        self.width = 1920
        self.height = 1080 
        
        if PYAUTOGUI_AVAILABLE:
            try:
                self.width, self.height = pyautogui.size()
            except Exception:
                pass

    def assign_screenshot(self, obs: Dict[str, Any]):
        """Update current observation."""
        self.obs = obs

    def generate_coords(self, description: str) -> List[int]:
        """
        Ground a natural language description to (x, y) coordinates using the VLM.
        """
        if not self.obs or "screenshot" not in self.obs:
            raise ValueError("No screenshot available for grounding.")

        # Save screenshot to temp file for CLI
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(self.obs["screenshot"])
            img_path = f.name
        
        try:
            # Agent-S Prompt Style
            prompt = (
                f"Query: {description}\n"
                f"Output only the coordinate of one point in your response. "
                f"Format: [x, y] or similar."
            )
            
            response = self.grounding_model.generate(prompt, image_path=img_path)
            
            # Simple parsing of numbers
            numericals = re.findall(r"\d+", response)
            if len(numericals) >= 2:
                x, y = int(numericals[0]), int(numericals[1])
                # Scale if needed? Assuming model returns absolute coords for now if trained on them,
                # or we might need to normalize. Gemini usually handles this well if prompted.
                return [x, y]
            else:
                logger.warning(f"Could not parse coords from: {response}")
                return [self.width // 2, self.height // 2] # Fallback center
        finally:
            Path(img_path).unlink(missing_ok=True)

    def get_ocr_results(self) -> str:
        """Get text elements from screenshot using Tesseract (Agent-S style)."""
        if not TESSERACT_AVAILABLE or not self.obs:
            return ""
        
        image = Image.open(tempfile.BytesIO(self.obs["screenshot"]))
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        # Format as a table for the LLM
        lines = ["Text Table:", "id\ttext\tbox"]
        for i, text in enumerate(data["text"]):
            if text.strip():
                box = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
                lines.append(f"{i}\t{text}\t{box}")
        
        return "\n".join(lines)

    @agent_action
    def click(self, description: str, num_clicks: int = 1, button: str = "left"):
        """Click on an element described by 'description'."""
        coords = self.generate_coords(description)
        x, y = coords[0], coords[1]
        
        code = f"pyautogui.click({x}, {y}, clicks={num_clicks}, button='{button}')"
        logger.info(f"ACTION: Click on '{description}' at ({x}, {y})")
        return code

    @agent_action
    def type_text(self, text: str, submit: bool = False):
        """Type text."""
        code = f"pyautogui.write({repr(text)}, interval=0.05)"
        if submit:
            code += "; pyautogui.press('enter')"
        logger.info(f"ACTION: Type '{text}'")
        return code

    @agent_action
    def hotkey(self, *keys):
        """Press a hotkey combination."""
        k_str = ", ".join(repr(k) for k in keys)
        code = f"pyautogui.hotkey({k_str})"
        logger.info(f"ACTION: Hotkey {keys}")
        return code

    @agent_action
    def scroll(self, amount: int):
        """Scroll execution."""
        code = f"pyautogui.scroll({amount})"
        logger.info(f"ACTION: Scroll {amount}")
        return code

    @agent_action
    def wait(self, seconds: float):
        code = f"time.sleep({seconds})"
        return code

    @agent_action
    def done(self, summary: str = ""):
        """Mark task as done."""
        logger.info(f"ACTION: DONE - {summary}")
        return "# DONE"

    @agent_action
    def save_to_knowledge(self, info: str):
        """Save info to procedural memory."""
        self.notes.append(info)
        logger.info(f"ACTION: Memory saved - {info}")
        return "# MEMORY UPDATED"

    @agent_action
    def open_application(self, app_name: str):
        """Open an application via Spotlight (macOS) or Search (Windows)."""
        logger.info(f"ACTION: Open app '{app_name}'")
        if self.platform == "darwin":
            return (
                "pyautogui.hotkey('command', 'space'); "
                "time.sleep(0.5); "
                f"pyautogui.write({repr(app_name)}); "
                "pyautogui.press('enter')"
            )
        else:
            return (
                "pyautogui.hotkey('win'); "
                "time.sleep(0.5); "
                f"pyautogui.write({repr(app_name)}); "
                "pyautogui.press('enter')"
            )

    @agent_action
    def run_code(self, code: str):
        """
        Execute arbitrary Python code (The 'Code Agent' pattern).
        WARNING: Potentially unsafe.
        """
        logger.info("ACTION: Run Code")
        return code
