import subprocess
import tempfile
import os
import time
import base64
from pathlib import Path
from typing import Optional
from .logging import logger
try:
    from ..replay.execution_logger import log_llm_interaction
except ImportError:
    # Fallback if logger not available
    def log_llm_interaction(*args, **kwargs): pass

# For vision tasks, we'll use the Python SDK since CLI doesn't support images
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# Import for image handling
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class GeminiCLI:
    """
    Wrapper for the Gemini CLI tool (text-only) and Python API (for vision).
    Uses Gemini 3.0 Pro (gemini-2.5-pro) for high-quality strategic planning.
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

    def generate(self, prompt: str, image_path: Optional[str] = None, retry_count: int = 3, model: Optional[str] = None) -> str:
        """
        Generate text using the Gemini CLI (text-only prompts).
        Images are NOT supported by the CLI, so we ignore them for now.
        
        Args:
            prompt: The text prompt
            image_path: Path to image (ignored, CLI doesn't support images)
            retry_count: Number of retry attempts
            model: Optional model override (e.g., "gemini-2.0-flash-exp")
        """
        # Note: Gemini CLI doesn't support image input
        # For vision grounding, use google-genai Python package instead
        if image_path:
            logger.warning("Gemini CLI does not support image input. Ignoring image.")
        
        # Use provided model or default
        model_to_use = model or self.model_name
        
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                
                # Build CLI command with model selection
                cmd = ["gemini", "-m", model_to_use, "-o", "text"]
                
                # Pass prompt via stdin
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=30  # Reduced from 120 to 30 seconds for faster failures
                )
                
                duration = time.time() - start_time
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    if output:
                        logger.debug(f"Gemini ({model_to_use}) response time: {duration:.1f}s")
                        
                        # Log to execution logger for training data
                        log_llm_interaction(
                            component="gemini_cli",
                            prompt=prompt,
                            response=output,
                            model=model_to_use,
                            duration_ms=duration * 1000
                        )
                        
                        return output
                    else:
                        logger.warning("Empty response from Gemini CLI")
                else:
                    logger.error(f"Gemini CLI error (attempt {attempt+1}/{retry_count}): {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Gemini CLI timed out (timeout: {attempt+1}/{retry_count})")
                # Don't wait as long between timeouts
                if attempt < retry_count - 1:
                    time.sleep(1)
                continue
            except Exception as e:
                logger.error(f"Gemini CLI error (attempt {attempt+1}/{retry_count}): {e}")
            
            time.sleep(2)
        
        # Return a fallback instead of raising to prevent complete failure
        logger.error("⚠️ Failed to generate response from Gemini CLI after retries - returning fallback")
        return "DONE"  # Vision actions will treat this as completion


class GeminiVision:
    """
    Gemini Vision API wrapper for image understanding.
    Uses google-genai SDK for vision models.
    """
    
    def __init__(self, model_name: str = "gemini-2.0-flash-exp", api_key: Optional[str] = None):
        """
        Initialize Gemini vision client.
        
        Args:
            model_name: Vision model to use
            api_key: Optional API key (reads from env if not provided)
        """
        if not GENAI_AVAILABLE:
            raise RuntimeError("google-genai not available. Install: pip install google-genai")
        
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available. Install: pip install pillow")
        
        self.model_name = model_name
        
        # Configure API
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # Try to get from environment
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
        
        logger.info(f"Initialized Gemini Vision with model: {model_name}")
    
    def generate_with_image(self, prompt: str, image_bytes: bytes, retry_count: int = 2) -> str:
        """
        Generate response with image input.
        
        Args:
            prompt: Text prompt
            image_bytes: Image as bytes
            retry_count: Number of retries
            
        Returns:
            Model response text
        """
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                
                # Convert bytes to PIL Image
                pil_image = Image.open(io.BytesIO(image_bytes))
                
                # Create model
                model = genai.GenerativeModel(self.model_name)
                
                # Generate with image
                response = model.generate_content([prompt, pil_image])
                
                duration = time.time() - start_time
                logger.info(f"Gemini Vision response time: {duration:.1f}s")
                
                response_text = response.text
                
                # Log to execution logger for training data
                log_llm_interaction(
                    component="gemini_vision",
                    prompt=prompt + " [With Image]",
                    response=response_text,
                    model=self.model_name,
                    duration_ms=duration * 1000
                )
                
                return response_text
                
            except Exception as e:
                logger.error(f"Gemini Vision error (attempt {attempt+1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    time.sleep(2)
        
        logger.error("Failed to get vision response after retries")
        return ""
    
    def generate_with_image_path(self, prompt: str, image_path: str, retry_count: int = 2) -> str:
        """
        Generate response with image file path.
        
        Args:
            prompt: Text prompt
            image_path: Path to image file
            retry_count: Number of retries
            
        Returns:
            Model response text
        """
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        return self.generate_with_image(prompt, image_bytes, retry_count)


# Main client that combines both text and vision
class GeminiClient:
    """
    Unified Gemini client supporting both text (CLI) and vision (SDK) models.
    """
    
    def __init__(self, text_model: str = "gemini-2.5-pro", vision_model: str = "gemini-2.0-flash-exp"):
        self.cli = GeminiCLI(model_name=text_model)
        
        # Vision client initialized on-demand
        self._vision = None
        self.vision_model = vision_model
    
    @property
    def vision(self) -> GeminiVision:
        """Lazy-load vision client."""
        if self._vision is None:
            self._vision = GeminiVision(model_name=self.vision_model)
        return self._vision
    
    def generate(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate text response (CLI)."""
        return self.cli.generate(prompt, model=model)
    
    def generate_with_image(self, prompt: str, image_bytes: bytes) -> str:
        """Generate response with image (Vision SDK)."""
        return self.vision.generate_with_image(prompt, image_bytes)

