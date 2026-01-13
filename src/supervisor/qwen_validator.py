from pathlib import Path
from typing import Dict, Any, Optional, List
from ..utils.logging import logger
from ..utils.prompt_loader import get_supervisor_prompt
from ..utils.prompt_evolution import prompt_evolution

# Lazy load llama_cpp
try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

class Supervisor:
    """
    The 'Supervisor' component (Qwen 7B).
    Validates execution and provides corrections.
    """
    def __init__(self, model_path: str = "./models/qwen2.5-7b-instruct-q5_k_m.gguf"):
        self.model_path = model_path
        self.model = None
        self._loaded = False

    def _load_model(self):
        if self._loaded:
            return
            
        if not LLAMA_CPP_AVAILABLE:
            logger.warning("llama-cpp-python not available. Supervisor will be disabled.")
            return

        if not Path(self.model_path).exists():
            logger.warning(f"Model not found at {self.model_path}. Supervisor disabled.")
            return

        logger.info(f"Loading Supervisor model from {self.model_path}...")
        try:
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=4096,
                n_gpu_layers=-1, # Use GPU
                verbose=False
            )
            self._loaded = True
            logger.info("Supervisor loaded.")
        except Exception as e:
            logger.error(f"Failed to load Supervisor: {e}")

    def validate_step(self, task: str, last_action: str, screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if the last action was correct (Real-time supervision).
        Uses evolved system prompt for validation logic.
        """
        self._load_model()
        if not self.model:
            return {"approved": True, "reason": "Supervisor disabled"}

        # Load evolved system prompt
        system_prompt = get_supervisor_prompt()
        
        prompt = f"""{system_prompt}

## Validation Request
Task: {task}
Action Taken: {last_action}

Analyze if this action is logically correct for the task.
Output format:
{{
  "approved": true/false,
  "confidence": 0.0-1.0,
  "reason": "brief explanation",
  "suggestion": "corrective action if needed"
}}
"""
        
        try:
            output = self.model(prompt, max_tokens=128, temperature=0.1)
            text = output["choices"][0]["text"].strip()
            
            # Try to parse JSON response
            import json
            if "{" in text:
                json_str = text[text.find("{"):text.rfind("}")+1]
                result = json.loads(json_str)
                approved = result.get("approved", True)
            else:
                # Fallback to simple text parsing
                approved = "yes" in text.lower() or "approved" in text.lower()
                result = {"approved": approved, "reason": text}
            
            # Record validation feedback
            prompt_evolution.record_feedback(
                component="supervisor",
                task=task,
                success=approved,
                actions_taken=[last_action],
                suggestion=result.get("suggestion", None) if not approved else None
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {"approved": True, "reason": f"Validation error: {e}"}

    def validate_task_completion(self, task: str, history: List[str]) -> bool:
        """Validate if the task is actually finished."""
        self._load_model()
        if not self.model:
            return True

        # Load evolved system prompt
        system_prompt = get_supervisor_prompt()
        
        history_text = "\n".join(history[-10:]) # last 10 steps
        prompt = f"""{system_prompt}

## Task Completion Validation
Task: {task}
Action History:
{history_text}

Determine if the task has been completed successfully.
Output: {{"completed": true/false, "reason": "brief explanation"}}
"""
        
        try:
            output = self.model(prompt, max_tokens=64, temperature=0.1)
            text = output["choices"][0]["text"].strip()
            
            # Parse response
            import json
            if "{" in text:
                json_str = text[text.find("{"):text.rfind("}")+1]
                result = json.loads(json_str)
                completed = result.get("completed", False)
            else:
                completed = "yes" in text.lower() or "completed" in text.lower()
            
            # Record completion validation
            prompt_evolution.record_feedback(
                component="supervisor",
                task=f"Validate completion: {task}",
                success=True,
                actions_taken=history[-5:]
            )
            
            return completed
            
        except Exception as e:
            logger.error(f"Completion validation failed: {e}")
            return True  # Assume completed on error
