"""
OmniParser Screen Parser - High-level screen understanding using OmniParser.

Provides semantic element finding and screen parsing that matches
the VLMScreenParser interface but uses OmniParser's YOLOv8 + Florence-2
pipeline for superior accuracy on non-accessible applications.

Key advantages over VLM-based parsing:
- Faster inference (~0.6s vs 2-3s for VLM)
- Better accuracy on icon-heavy interfaces
- Consistent bounding boxes (vs VLM's approximate coordinates)
- Works offline after model download
"""

import io
import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
from PIL import Image

from .omniparser_client import (
    OmniParserClient,
    get_omniparser_client,
    is_omniparser_available,
    DetectedElement,
    ParsedScreen,
    BoundingBox,
)

logger = logging.getLogger(__name__)


@dataclass
class SemanticMatch:
    """A semantic match between query and detected element."""
    element: DetectedElement
    score: float  # 0.0 to 1.0
    match_reason: str
    
    @property
    def center(self) -> Tuple[int, int]:
        return self.element.center
    
    @property
    def bounding_box(self) -> BoundingBox:
        return self.element.bounding_box


class OmniParserScreenParser:
    """
    Screen parser using OmniParser for UI element detection.
    
    Provides an interface similar to VLMScreenParser but uses
    the faster and more accurate OmniParser pipeline.
    """
    
    def __init__(
        self,
        client: Optional[OmniParserClient] = None,
        min_match_score: float = 0.4,
    ):
        """
        Initialize screen parser.
        
        Args:
            client: OmniParser client instance (or uses global)
            min_match_score: Minimum score for semantic matching
        """
        self._client = client
        self.min_match_score = min_match_score
    
    @property
    def client(self) -> OmniParserClient:
        """Get OmniParser client (lazy init)."""
        if self._client is None:
            self._client = get_omniparser_client()
        return self._client
    
    def parse_screen(self, screenshot: bytes, with_captions: bool = True) -> ParsedScreen:
        """
        Parse screenshot to detect all UI elements.
        
        Args:
            screenshot: Screenshot as bytes
            with_captions: Whether to generate semantic captions
            
        Returns:
            ParsedScreen with detected elements
        """
        return self.client.parse_screen(screenshot, with_captions=with_captions)
    
    def get_all_interactable_elements(self, screenshot: bytes) -> List[DetectedElement]:
        """
        Get all interactable elements on screen.
        
        Args:
            screenshot: Screenshot as bytes
            
        Returns:
            List of detected elements
        """
        parsed = self.parse_screen(screenshot, with_captions=True)
        return [e for e in parsed.elements if e.is_interactable]
    
    def find_element_by_description(
        self,
        screenshot: bytes,
        description: str,
        return_all: bool = False
    ) -> Optional[SemanticMatch]:
        """
        Find UI element matching natural language description.
        
        Args:
            screenshot: Screenshot as bytes
            description: Natural language description (e.g., "the blue submit button")
            return_all: If True, returns list of all matches
            
        Returns:
            Best matching element or None
        """
        # Parse screen to get elements with captions
        parsed = self.parse_screen(screenshot, with_captions=True)
        
        if not parsed.elements:
            logger.warning("No elements detected in screenshot")
            return None
        
        # Find best matches
        matches = self._semantic_match(description, parsed.elements)
        
        if not matches:
            logger.warning(f"No element matching '{description}'")
            return None
        
        if return_all:
            return matches
        
        return matches[0]
    
    def _semantic_match(
        self,
        query: str,
        elements: List[DetectedElement]
    ) -> List[SemanticMatch]:
        """
        Find elements semantically matching the query.
        
        Uses multiple matching strategies:
        1. Exact substring match
        2. Fuzzy string matching
        3. Keyword extraction
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\w+', query_lower))
        
        matches = []
        
        for elem in elements:
            score = 0.0
            reason = ""
            
            # Get text to match against
            text = (elem.caption or "") + " " + (elem.ocr_text or "")
            text_lower = text.lower()
            text_words = set(re.findall(r'\w+', text_lower))
            
            # Strategy 1: Exact substring match
            if query_lower in text_lower:
                score = 0.95
                reason = "exact_match"
            
            # Strategy 2: Word overlap
            elif query_words and text_words:
                overlap = len(query_words & text_words)
                if overlap > 0:
                    score = 0.5 + (0.4 * overlap / len(query_words))
                    reason = f"word_overlap({overlap})"
            
            # Strategy 3: Fuzzy string matching
            if score < 0.5 and text:
                fuzzy_score = SequenceMatcher(None, query_lower, text_lower).ratio()
                if fuzzy_score > score:
                    score = fuzzy_score
                    reason = f"fuzzy({fuzzy_score:.2f})"
            
            # Strategy 4: Element type matching
            type_keywords = {
                "button": ["button", "btn", "click", "submit", "send", "ok", "cancel"],
                "input": ["input", "text", "field", "search", "type", "enter"],
                "icon": ["icon", "image", "logo", "picture"],
                "link": ["link", "url", "href", "navigate"],
                "menu": ["menu", "dropdown", "select", "option"],
            }
            
            for elem_type, keywords in type_keywords.items():
                if any(kw in query_lower for kw in keywords):
                    if elem.element_type == elem_type:
                        score += 0.1
                        reason += f"+type({elem_type})"
            
            # Apply confidence weighting
            score *= (0.5 + 0.5 * elem.confidence)
            
            if score >= self.min_match_score:
                matches.append(SemanticMatch(
                    element=elem,
                    score=score,
                    match_reason=reason,
                ))
        
        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)
        
        if matches:
            logger.info(f"Found {len(matches)} matches for '{query}', best: {matches[0].score:.2f}")
        
        return matches
    
    def get_annotated_screenshot(self, screenshot: bytes) -> bytes:
        """
        Get screenshot with detected elements annotated.
        
        Args:
            screenshot: Original screenshot
            
        Returns:
            Annotated screenshot as PNG bytes
        """
        parsed = self.parse_screen(screenshot, with_captions=True)
        return self.client.get_annotated_image(screenshot, parsed.elements)
    
    def save_annotated_screenshot(self, output_path: str, screenshot: Optional[bytes] = None):
        """
        Save annotated screenshot to file.
        
        Args:
            output_path: Path to save annotated image
            screenshot: Screenshot bytes (or captures current screen)
        """
        if screenshot is None:
            # Capture current screen
            import pyautogui
            img = pyautogui.screenshot()
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            screenshot = buffer.getvalue()
        
        annotated = self.get_annotated_screenshot(screenshot)
        
        with open(output_path, 'wb') as f:
            f.write(annotated)
        
        logger.info(f"Saved annotated screenshot to {output_path}")
    
    def format_elements_for_llm(
        self,
        screenshot: bytes,
        max_elements: int = 50
    ) -> str:
        """
        Format detected elements as text for LLM context.
        
        Args:
            screenshot: Screenshot bytes
            max_elements: Maximum elements to include
            
        Returns:
            Formatted string for LLM consumption
        """
        parsed = self.parse_screen(screenshot, with_captions=True)
        
        lines = [
            f"Screen: {parsed.screen_width}x{parsed.screen_height}",
            f"Detected {len(parsed.elements)} UI elements:",
            ""
        ]
        
        for elem in parsed.elements[:max_elements]:
            bbox = elem.bounding_box
            label = elem.caption or elem.ocr_text or "unknown"
            line = f"  [{elem.id}] {label} @ ({bbox.center[0]}, {bbox.center[1]}) [{bbox.width}x{bbox.height}]"
            lines.append(line)
        
        if len(parsed.elements) > max_elements:
            lines.append(f"  ... and {len(parsed.elements) - max_elements} more")
        
        return "\n".join(lines)


# Global parser instance
_global_parser: Optional[OmniParserScreenParser] = None


def get_omniparser() -> OmniParserScreenParser:
    """Get or create global OmniParser screen parser."""
    global _global_parser
    if _global_parser is None:
        _global_parser = OmniParserScreenParser()
    return _global_parser


def find_element_omniparser(
    screenshot: bytes,
    description: str
) -> Optional[Tuple[int, int]]:
    """
    Quick function to find element center by description.
    
    Args:
        screenshot: Screenshot bytes
        description: Natural language description
        
    Returns:
        (x, y) center coordinates or None
    """
    parser = get_omniparser()
    match = parser.find_element_by_description(screenshot, description)
    
    if match:
        return match.center
    return None
