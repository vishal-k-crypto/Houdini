"""
Vision-Language Model Screen Parser
Uses Gemini 2.0 for semantic UI understanding from screenshots.

Features:
- Semantic element detection ("Find the submit button")
- UI layout understanding
- Element grounding (text description → bounding box)
- Screen summarization for LLM context
"""

import io
import base64
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
from ..utils.logging import logger

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.error("google-generativeai not available")


@dataclass
class BoundingBox:
    """Represents a bounding box for a UI element."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 1.0
    
    @property
    def center(self) -> Tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
    
    @property
    def size(self) -> Tuple[int, int]:
        return (self.x2 - self.x1, self.y2 - self.y1)
    
    def __str__(self):
        return f"BBox({self.x1}, {self.y1}, {self.x2}, {self.y2})"


@dataclass
class SemanticElement:
    """Represents a semantically understood UI element."""
    description: str
    role: str  # "button", "textfield", "link", etc.
    bounding_box: Optional[BoundingBox] = None
    text_content: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ParsedScreen:
    """Result of VLM screen parsing."""
    summary: str
    elements: List[SemanticElement]
    layout_description: str
    confidence: float


class VLMScreenParser:
    """
    Vision-Language Model based screen understanding.
    Uses Gemini 2.0 for semantic UI parsing.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash-exp"):
        if not GENAI_AVAILABLE:
            raise RuntimeError("google-generativeai not available. Install: pip install google-generativeai")
        
        # Import existing gemini_client for API key
        try:
            from .gemini_client import GeminiClient
            client = GeminiClient()
            # Use existing configured client
            self.model_name = model
        except Exception as e:
            logger.warning(f"Could not import GeminiClient: {e}. Using direct API.")
            if api_key:
                genai.configure(api_key=api_key)
            self.model_name = model
        
        # Cache for repeated queries
        self._cache = {}
    
    def _image_to_pil(self, image_bytes: bytes) -> Image.Image:
        """Convert image bytes to PIL Image."""
        return Image.open(io.BytesIO(image_bytes))
    
    def _call_gemini_vision(self, image_bytes: bytes, prompt: str) -> str:
        """
        Call Gemini vision model with image and prompt.
        
        Args:
            image_bytes: Screenshot as bytes
            prompt: Text prompt for analysis
            
        Returns:
            Model response as string
        """
        try:
            model = genai.GenerativeModel(self.model_name)
            
            # Convert to PIL for Gemini
            pil_image = self._image_to_pil(image_bytes)
            
            # Generate content
            response = model.generate_content([prompt, pil_image])
            
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini vision call failed: {e}")
            return ""
    
    def parse_screen(self, screenshot: bytes, task_context: str = "") -> ParsedScreen:
        """
        Parse screenshot to understand UI structure and elements.
        
        Args:
            screenshot: Screenshot as bytes
            task_context: Optional context about what task we're trying to do
            
        Returns:
            ParsedScreen with semantic understanding
        """
        prompt = f"""You are analyzing a screenshot of a user interface.

Task context: {task_context if task_context else "General UI understanding"}

Please analyze this screenshot and provide:
1. A brief summary of what application/page this is
2. The main UI elements visible (buttons, text fields, links, etc.)
3. The overall layout structure

Format your response as JSON:
{{
    "summary": "Brief description of the screen",
    "layout": "Description of the layout (header, sidebar, main content, etc.)",
    "elements": [
        {{
            "description": "Element description",
            "role": "button|textfield|link|image|menu|etc",
            "text": "visible text on element (if any)",
            "approximate_position": "top-left|top-right|center|bottom-left|etc"
        }}
    ]
}}

Be precise and focus on interactive elements."""

        response_text = self._call_gemini_vision(screenshot, prompt)
        
        if not response_text:
            return ParsedScreen(
                summary="Failed to parse screen",
                elements=[],
                layout_description="",
                confidence=0.0
            )
        
        # Parse JSON response
        try:
            # Extract JSON from markdown code blocks if present
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            
            data = json.loads(json_str)
            
            # Convert to SemanticElements
            elements = []
            for elem_data in data.get("elements", []):
                elements.append(SemanticElement(
                    description=elem_data.get("description", ""),
                    role=elem_data.get("role", "unknown"),
                    text_content=elem_data.get("text"),
                    confidence=0.8  # VLM detection confidence
                ))
            
            return ParsedScreen(
                summary=data.get("summary", ""),
                elements=elements,
                layout_description=data.get("layout", ""),
                confidence=0.8
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse VLM JSON response: {e}")
            # Fallback: return text-based understanding
            return ParsedScreen(
                summary=response_text[:200],
                elements=[],
                layout_description=response_text,
                confidence=0.5
            )
    
    def find_element_semantically(
        self,
        screenshot: bytes,
        element_description: str
    ) -> Optional[BoundingBox]:
        """
        Find element by semantic description and return bounding box.
        
        Args:
            screenshot: Screenshot as bytes
            element_description: Natural language description 
                                 (e.g., "the blue submit button", "email input field")
            
        Returns:
            BoundingBox if found, None otherwise
        """
        prompt = f"""In this screenshot, find the UI element described as: "{element_description}"

If you can identify this element, provide its approximate bounding box coordinates.

Respond ONLY with JSON in this exact format:
{{
    "found": true/false,
    "bounding_box": {{
        "x1": left_x,
        "y1": top_y,
        "x2": right_x,
        "y2": bottom_y
    }},
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

Coordinates should be in pixels from top-left corner (0,0).
If element not found, set found=false."""

        response_text = self._call_gemini_vision(screenshot, prompt)
        
        if not response_text:
            return None
        
        try:
            # Extract JSON
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            
            data = json.loads(json_str)
            
            if data.get("found"):
                bbox_data = data.get("bounding_box", {})
                return BoundingBox(
                    x1=bbox_data["x1"],
                    y1=bbox_data["y1"],
                    x2=bbox_data["x2"],
                    y2=bbox_data["y2"],
                    confidence=data.get("confidence", 0.7)
                )
            
            return None
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse element grounding response: {e}")
            return None
    
    def generate_screen_summary(self, screenshot: bytes, max_length: int = 500) -> str:
        """
        Generate a concise text summary of the screen for LLM context.
        
        Args:
            screenshot: Screenshot as bytes
            max_length: Maximum summary length
            
        Returns:
            Text summary
        """
        # Check cache
        cache_key = f"summary_{hash(screenshot)}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        prompt = f"""Provide a concise summary of this screen in {max_length} characters or less.

Focus on:
1. What application/webpage this is
2. Main visible content
3. Key interactive elements (buttons, forms, etc.)
4. Current state (e.g., "login page", "search results", "settings menu")

Be direct and factual. No introductions like "This is..." """

        summary = self._call_gemini_vision(screenshot, prompt)
        
        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length-3] + "..."
        
        # Cache it
        self._cache[cache_key] = summary
        
        return summary
    
    def detect_ui_changes(
        self,
        screenshot_before: bytes,
        screenshot_after: bytes
    ) -> List[str]:
        """
        Detect what changed between two screenshots.
        
        Args:
            screenshot_before: Screenshot before action
            screenshot_after: Screenshot after action
            
        Returns:
            List of change descriptions
        """
        prompt = """Compare these two screenshots (before and after an action).

List what changed between them. Focus on:
- New or removed UI elements
- Content changes
- State changes (button disabled/enabled, checkbox checked, etc.)
- Navigation changes

Respond with a JSON array of change descriptions:
["change 1", "change 2", ...]

Be specific and concise."""

        # Note: Gemini can handle multiple images
        try:
            model = genai.GenerativeModel(self.model_name)
            
            img_before = self._image_to_pil(screenshot_before)
            img_after = self._image_to_pil(screenshot_after)
            
            response = model.generate_content([prompt, img_before, img_after])
            
            # Parse response
            json_match = re.search(r'\[(.*?)\]', response.text, re.DOTALL)
            if json_match:
                changes = json.loads(json_match.group(0))
                return changes
            
            return []
            
        except Exception as e:
            logger.error(f"UI change detection failed: {e}")
            return []
    
    def understand_complex_ui(self, screenshot: bytes, element_type: str) -> str:
        """
        Understand complex UI elements like charts, infographics, tables.
        
        Args:
            screenshot: Screenshot as bytes
            element_type: Type of element ("chart", "table", "infographic", etc.)
            
        Returns:
            Structured text description
        """
        prompt = f"""Analyze this {element_type} in the screenshot.

Provide a structured description including:
- Main data/information shown
- Key values or trends
- Visual structure (rows, columns, axes, etc.)
- Any notable patterns or outliers

Format as clear, structured text suitable for an AI agent to understand."""

        return self._call_gemini_vision(screenshot, prompt)


# Convenience functions
_global_parser = None

def get_vlm_parser() -> VLMScreenParser:
    """Get global VLM parser instance."""
    global _global_parser
    if _global_parser is None:
        _global_parser = VLMScreenParser()
    return _global_parser


def find_element_by_description(screenshot: bytes, description: str) -> Optional[BoundingBox]:
    """Quick function to find element semantically."""
    parser = get_vlm_parser()
    return parser.find_element_semantically(screenshot, description)
