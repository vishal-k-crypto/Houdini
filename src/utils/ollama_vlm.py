"""
Ollama VLM (Vision-Language Model) Client for Qwen3-VL
Uses screenshots to find precise click coordinates when accessibility fails.
"""

import subprocess
import json
import base64
import io
import time
from typing import Optional, Tuple, Dict
from pathlib import Path
from .logging import logger

try:
    import pyautogui
    from PIL import Image
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui/PIL not available for screenshots")


class OllamaVLM:
    """
    Vision-Language Model client using Ollama's Qwen3-VL model.
    Takes screenshots and finds precise click coordinates for UI elements.
    """
    
    def __init__(self, model_name: str = "qwen3-vl:235b-cloud"):
        """
        Initialize VLM client.
        
        Args:
            model_name: VLM model to use (default: qwen3-vl:235b-cloud)
        """
        self.model_name = model_name
        self.screen_width, self.screen_height = self._get_screen_size()
        self._last_result = None  # Store last VLM result for detailed access
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)  # Default fallback
    
    def get_last_result(self) -> Optional[Dict]:
        """Get the last VLM analysis result with full details."""
        return self._last_result
    
    def _take_screenshot(self) -> bytes:
        """Take a screenshot and return as bytes."""
        if not PYAUTOGUI_AVAILABLE:
            raise RuntimeError("pyautogui not available for screenshots")
        
        # Take screenshot
        screenshot = pyautogui.screenshot()
        
        # Convert to bytes
        buffer = io.BytesIO()
        screenshot.save(buffer, format='PNG')
        return buffer.getvalue()
    
    def _image_to_base64(self, image_bytes: bytes) -> str:
        """Convert image bytes to base64 string."""
        return base64.b64encode(image_bytes).decode('utf-8')
    
    def find_element_coordinates(
        self,
        element_description: str,
        task_context: str = "",
        retry_count: int = 2
    ) -> Optional[Tuple[int, int]]:
        """
        Find precise coordinates for a UI element using VLM analysis.
        
        Args:
            element_description: What element to find (e.g., "search field", "send button")
            task_context: Additional context about the task
            retry_count: Number of retries
        
        Returns:
            (x, y) coordinates to click, or None if not found
        """
        for attempt in range(retry_count):
            try:
                # Take screenshot
                screenshot_bytes = self._take_screenshot()
                screenshot_b64 = self._image_to_base64(screenshot_bytes)
                
                logger.info(f"🖼️ VLM analyzing screenshot for: {element_description}")
                
                # Build the prompt for precise coordinate detection
                prompt = f"""You are an EXPERT UI automation system that finds PRECISE click coordinates on screen.

## YOUR TASK
Find the element: "{element_description}"
Context: {task_context}
Screen size: {self.screen_width} x {self.screen_height} pixels

## COORDINATE SYSTEM
- Origin (0,0) is TOP-LEFT corner
- X increases going RIGHT (0 to {self.screen_width})
- Y increases going DOWN (0 to {self.screen_height})

## PRECISION REQUIREMENTS
1. Find the EXACT center of the clickable element
2. For INPUT FIELDS: click CENTER of the text input area
3. For BUTTONS: click CENTER of the button
4. For LIST ITEMS: click CENTER of the row
5. For ICONS: click CENTER of the icon

## VISUAL MEASUREMENT
- Look at the element's bounding box
- Calculate center_x = left_edge + (width / 2)
- Calculate center_y = top_edge + (height / 2)
- Double-check your math - precision matters!

## MATCH PROBABILITY RATING
Rate how well the found element matches what was requested:
- 1.0 = EXACT match (e.g., searching "John" found "John")
- 0.9 = Near-exact with minor difference (e.g., "John" found "John Smith")
- 0.8 = Contains the search term (e.g., "john" found "John RU")
- 0.7 = Partial match (e.g., "kush" found "Kushal")
- 0.5 = Weak match (e.g., similar but not same)
- 0.0 = No match

## CONFIDENCE RATING  
Rate how confident you are in the COORDINATES:
- 1.0 = Absolutely certain, clearly visible element
- 0.8 = Very confident, element is clear
- 0.6 = Fairly confident, element visible but small
- 0.4 = Uncertain, element partially obscured
- 0.2 = Guessing, element hard to locate

## RESPONSE FORMAT (JSON only)
{{
    "found": true,
    "element": "exact text or description of element found",
    "x": <integer X coordinate>,
    "y": <integer Y coordinate>,
    "confidence": <float 0.0-1.0>,
    "match_probability": <float 0.0-1.0>,
    "reasoning": "how you found it and calculated coordinates"
}}

If NOT found:
{{
    "found": false,
    "element": null,
    "x": null,
    "y": null,
    "confidence": 0.0,
    "match_probability": 0.0,
    "reasoning": "why element was not found"
}}"""

                # Call Ollama with vision
                result = self._call_ollama_vision(screenshot_b64, prompt)
                
                if result and result.get("found"):
                    x = result.get("x")
                    y = result.get("y")
                    confidence = result.get("confidence", 0.0)
                    
                    # Validate coordinates
                    if x is not None and y is not None:
                        x = int(x)
                        y = int(y)
                        
                        # Ensure within bounds
                        x = max(0, min(x, self.screen_width - 1))
                        y = max(0, min(y, self.screen_height - 1))
                        
                        match_prob = result.get("match_probability", 1.0)
                        element_text = result.get('element', 'unknown')
                        reasoning = result.get('reasoning', 'none')
                        
                        logger.info(f"  ✅ VLM found element at ({x}, {y})")
                        logger.info(f"     Confidence: {confidence:.0%}, Match probability: {match_prob:.0%}")
                        logger.info(f"     Element: {element_text}")
                        logger.debug(f"     Reasoning: {reasoning}")
                        
                        # Store the full result for callers who need it
                        self._last_result = {
                            "x": x,
                            "y": y,
                            "confidence": confidence,
                            "match_probability": match_prob,
                            "element": element_text,
                            "reasoning": reasoning
                        }
                        
                        return (x, y)
                    else:
                        logger.warning(f"  VLM returned invalid coordinates: x={x}, y={y}")
                else:
                    reason = result.get("reasoning", "unknown") if result else "no response"
                    logger.warning(f"  VLM could not find element: {reason}")
                    
            except Exception as e:
                logger.error(f"VLM analysis failed (attempt {attempt+1}): {e}")
            
            # Wait before retry
            if attempt < retry_count - 1:
                time.sleep(0.5)
        
        return None
    
    def find_element_with_details(
        self,
        element_description: str,
        task_context: str = "",
        retry_count: int = 2
    ) -> Dict:
        """
        Find element coordinates with full details including match probability.
        
        Args:
            element_description: What element to find
            task_context: Additional context about the task
            retry_count: Number of retries
        
        Returns:
            Dict with coordinates, confidence, match_probability, element text, etc.
        """
        coords = self.find_element_coordinates(element_description, task_context, retry_count)
        
        if coords and self._last_result:
            return {
                "found": True,
                "coordinates": coords,
                **self._last_result
            }
        else:
            return {
                "found": False,
                "coordinates": None,
                "x": None,
                "y": None,
                "confidence": 0.0,
                "match_probability": 0.0,
                "element": None,
                "reasoning": "Element not found"
            }
    
    def _call_ollama_vision(self, image_b64: str, prompt: str) -> Optional[Dict]:
        """
        Call Ollama with vision capability using CLI approach.
        Works with both local and cloud models.
        
        Args:
            image_b64: Base64 encoded image
            prompt: The prompt to send
        
        Returns:
            Parsed JSON response or None
        """
        import subprocess
        import tempfile
        import os
        
        try:
            start_time = time.time()
            
            # Save image to temp file for CLI usage
            image_bytes = base64.b64decode(image_b64)
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            
            try:
                # Use ollama run with image file
                # Format: ollama run model "prompt" image_path
                cmd = [
                    "ollama", "run", self.model_name,
                    prompt,
                    tmp_path
                ]
                
                logger.debug(f"Running: ollama run {self.model_name} [prompt] {tmp_path}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=180  # Vision can take longer
                )
                
                duration = time.time() - start_time
                
                if result.returncode == 0:
                    response_text = result.stdout.strip()
                    logger.debug(f"VLM response ({duration:.1f}s): {response_text[:300]}")
                    
                    # Extract JSON from response
                    return self._parse_json_response(response_text)
                else:
                    logger.error(f"Ollama vision error: {result.stderr[:200]}")
                    return None
                    
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                    
        except subprocess.TimeoutExpired:
            logger.error("Ollama vision call timed out (180s)")
            return None
        except Exception as e:
            logger.error(f"Ollama vision error: {e}")
            return None
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Extract and parse JSON from VLM response."""
        try:
            # Try to find JSON in response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                # Find JSON object
                start = response.find("{")
                end = response.rfind("}") + 1
                if start != -1 and end != 0:
                    json_str = response[start:end]
                else:
                    json_str = response
            
            return json.loads(json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse VLM JSON: {e}")
            logger.debug(f"Raw response: {response}")
            return None
    
    def click_element(
        self,
        element_description: str,
        task_context: str = "",
        min_match_probability: float = 0.5
    ) -> Dict:
        """
        Find and click an element using VLM-guided coordinates.
        
        Args:
            element_description: What element to find and click
            task_context: Additional context about the task
            min_match_probability: Minimum match probability required to click (0.0-1.0)
        
        Returns:
            {"success": True/False, "coordinates": (x, y), "match_probability": float, ...}
        """
        # Get full details including match probability
        result = self.find_element_with_details(element_description, task_context)
        
        if not result.get("found"):
            return {
                "success": False,
                "coordinates": None,
                "match_probability": 0.0,
                "confidence": 0.0,
                "element": None,
                "error": f"Could not locate element: {element_description}"
            }
        
        coords = result.get("coordinates")
        match_prob = result.get("match_probability", 1.0)
        confidence = result.get("confidence", 0.0)
        element_text = result.get("element", "unknown")
        
        # Check if match probability meets minimum threshold
        if match_prob < min_match_probability:
            logger.warning(f"  ⚠️ Match probability {match_prob:.0%} below threshold {min_match_probability:.0%}")
            logger.warning(f"     Found: '{element_text}' but might not be the right element")
            return {
                "success": False,
                "coordinates": coords,
                "match_probability": match_prob,
                "confidence": confidence,
                "element": element_text,
                "error": f"Match probability too low: {match_prob:.0%} < {min_match_probability:.0%}"
            }
        
        x, y = coords
        
        try:
            # Move cursor with human-like motion
            current_x, current_y = pyautogui.position()
            distance = ((x - current_x)**2 + (y - current_y)**2)**0.5
            
            # Adjust duration based on distance
            duration = min(0.5, max(0.15, distance / 2000))
            
            logger.info(f"  🖱️ Moving cursor to ({x}, {y})")
            pyautogui.moveTo(x, y, duration=duration)
            
            time.sleep(0.05)  # Brief pause before click
            pyautogui.click()
            
            logger.info(f"  ✅ VLM-guided click at ({x}, {y}) [match: {match_prob:.0%}]")
            
            return {
                "success": True,
                "coordinates": (x, y),
                "match_probability": match_prob,
                "confidence": confidence,
                "element": element_text,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return {
                "success": False,
                "coordinates": coords,
                "match_probability": match_prob,
                "confidence": confidence,
                "element": element_text,
                "error": str(e)
            }


# Global instance for easy access
_vlm_instance = None


def get_vlm() -> OllamaVLM:
    """Get or create the global VLM instance."""
    global _vlm_instance
    if _vlm_instance is None:
        _vlm_instance = OllamaVLM()
    return _vlm_instance


def vlm_find_and_click(
    element_description: str,
    task_context: str = "",
    min_match_probability: float = 0.5
) -> Dict:
    """
    Convenience function to find and click an element using VLM.
    
    Args:
        element_description: What to find and click
        task_context: Additional task context
        min_match_probability: Minimum match probability required (0.0-1.0)
    
    Returns:
        {"success": True/False, "coordinates": (x, y), "match_probability": float, ...}
    """
    vlm = get_vlm()
    return vlm.click_element(element_description, task_context, min_match_probability)


def vlm_find_with_probability(element_description: str, task_context: str = "") -> Dict:
    """
    Find an element and return full details including match probability.
    Does NOT click - just returns the analysis.
    
    Args:
        element_description: What to find
        task_context: Additional task context
    
    Returns:
        {
            "found": True/False,
            "coordinates": (x, y) or None,
            "x": int,
            "y": int,
            "confidence": float,
            "match_probability": float,
            "element": "text of element found",
            "reasoning": "explanation"
        }
    """
    vlm = get_vlm()
    return vlm.find_element_with_details(element_description, task_context)
