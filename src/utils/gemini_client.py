import subprocess
import tempfile
import os
import time
import base64
from pathlib import Path
from typing import Optional
from .logging import logger

# For vision tasks, we'll use the Python SDK since CLI doesn't support images
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai_old
        GENAI_AVAILABLE = "old"
    except ImportError:
        GENAI_AVAILABLE = False

class GeminiCLI:
    """
    Wrapper for the Gemini CLI tool (text-only) and Python API (for vision).
    """
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        self.model_name = model_name
        self._verify_installation()

    def _verify_installation(self):
        """Check if gemini CLI is available."""
        try:
            result = subprocess.run(["gemini", "--version"], check=True, capture_output=True, text=True)
            logger.info(f"Gemini CLI version: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError(
                "Gemini CLI not found. Install it with:\n"
                "  npm install -g @google/gemini-cli\n"
                "Then authenticate with:\n"
                "  gemini auth"
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Gemini CLI check returned error: {e.stderr}")

    def generate(self, prompt: str, image_path: Optional[str] = None, retry_count: int = 3) -> str:
        """
        Generate text using the Gemini CLI (text-only prompts).
        Images are NOT supported by the CLI, so we ignore them for now.
        """
        # Note: Gemini CLI doesn't support image input
        # For vision grounding, consider using google-genai Python package instead
        if image_path:
            logger.warning("Gemini CLI does not support image input. Ignoring image.")
        
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                
                # Pass prompt via stdin, use -o text for plain output
                result = subprocess.run(
                    ["gemini", "-o", "text"],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                duration = time.time() - start_time
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    if output:
                        return output
                    else:
                        logger.warning("Empty response from Gemini CLI")
                else:
                    logger.error(f"Gemini CLI error (attempt {attempt+1}/{retry_count}): {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Gemini CLI timed out (attempt {attempt+1}/{retry_count})")
            except Exception as e:
                logger.error(f"Gemini CLI error (attempt {attempt+1}/{retry_count}): {e}")
            
            time.sleep(2)
        
        raise RuntimeError("Failed to generate response from Gemini CLI after retries.")
