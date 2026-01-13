import re
import time
from typing import Dict, List, Any

from ..utils.logging import logger
from ..utils.gemini_client import GeminiCLI
from .grounding import ACI
from .memory import PROCEDURAL_MEMORY


class Worker:
    """
    Fast Worker - Optimized for speed.
    Minimal processing, direct action execution.
    """
    def __init__(self, cli: GeminiCLI, aci: ACI, platform: str, max_trajectory: int = 4, enable_reflection: bool = False):
        self.cli = cli
        self.aci = aci
        self.platform = platform
        self.max_trajectory = max_trajectory
        self.enable_reflection = enable_reflection  # Disabled by default for speed
        
        self.trajectory = []
        self.step_count = 0

    def reset(self):
        self.trajectory = []
        self.step_count = 0
        self.aci.notes = []

    def _get_history_text(self) -> str:
        """Minimal history for context."""
        if not self.trajectory:
            return "First step."
        
        # Only last 2 steps for speed
        steps = self.trajectory[-2:]
        return " -> ".join(s['action'][:50] for s in steps)

    def step(self, instruction: str, obs: Dict) -> Dict:
        """
        Fast execution step.
        Skips OCR and reflection for maximum speed.
        """
        self.aci.assign_screenshot(obs)
        
        # Minimal prompt - no OCR, no reflection
        history = self._get_history_text()
        
        prompt = f"""Task: {instruction}
OS: {self.platform}
History: {history}

Execute ONE action. Respond with just the action call:
- aci.hotkey("command", "space")
- aci.type_text("text", submit=True)
- aci.click(description="element")
- aci.done()

Action:"""

        # Generate action
        try:
            raw_action = self.cli.generate(prompt)
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return {"done": False, "error": str(e)}

        # Parse action
        action_match = re.search(r"(aci\.[a-zA-Z_0-9]+\(.*?\))", raw_action, re.DOTALL)
        
        result_info = {"done": False, "error": None}
        executed_action = raw_action[:100]
        
        if action_match:
            action_code = action_match.group(1)
            executed_action = action_code
            
            if "aci.done" in action_code:
                result_info["done"] = True
            
            try:
                # Execute
                low_level_code = eval(action_code, {"aci": self.aci}, {})
                
                if low_level_code and not low_level_code.startswith("#"):
                    import pyautogui
                    import time as time_mod
                    exec(low_level_code, {"pyautogui": pyautogui, "time": time_mod}, {})
                    logger.info(f"✓ {action_code}")
            except Exception as e:
                logger.error(f"Exec error: {e}")
                result_info["error"] = str(e)
        else:
            logger.warning(f"No action in: {raw_action[:80]}")
            result_info["error"] = "Parse failed"

        # Minimal trajectory
        self.trajectory.append({"action": executed_action, "error": result_info["error"]})
        self.step_count += 1
        
        return result_info
