"""
Screen Understanding Coordinator
Orchestrates multiple screen understanding methods for comprehensive UI parsing.

Strategy:
1. Primary: Accessibility API (fast, semantic, native)
2. Fallback: VLM parsing (semantic but slower)
3. Last resort: OCR (text extraction only)

Combines outputs for best understanding.
"""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from ..utils.logging import logger

try:
    from .accessibility_api import AccessibilityAPI, AXElement
    from .vlm_screen_parser import VLMScreenParser, SemanticElement
    from .screen_reader import screenshot_to_context, ocr_screenshot
    import pyautogui
    from PIL import Image
    import io
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    logger.error(f"Required modules not available: {e}")


@dataclass
class ScreenUnderstanding:
    """Comprehensive screen understanding result."""
    # Accessibility data (fast, structured)
    accessibility_tree: Optional[AXElement] = None
    accessibility_elements: List[AXElement] = None
    
    # VLM semantic understanding (semantic, slower)
    vlm_summary: str = ""
    vlm_elements: List[SemanticElement] = None
    
    # OCR text extraction (fallback)
    ocr_text: str = ""
    ocr_elements: List[Dict] = None
    
    # Meta information
    app_name: str = ""
    window_title: str = ""
    method_used: str = ""  # "accessibility", "vlm", "hybrid", "ocr"
    confidence: float = 0.0
    processing_time: float = 0.0
    
    def __post_init__(self):
        if self.accessibility_elements is None:
            self.accessibility_elements = []
        if self.vlm_elements is None:
            self.vlm_elements = []
        if self.ocr_elements is None:
            self.ocr_elements = []
    
    def to_llm_context(self, max_length: int = 2000) -> str:
        """
        Format screen understanding as text for LLM consumption.
        
        Args:
            max_length: Maximum text length
            
        Returns:
            Formatted context string
        """
        lines = []
        
        # App info
        if self.app_name:
            lines.append(f"=== ACTIVE APP: {self.app_name} ===")
            if self.window_title:
                lines.append(f"Window: {self.window_title}")
            lines.append("")
        
        # VLM summary (semantic understanding)
        if self.vlm_summary:
            lines.append("=== SCREEN SUMMARY ===")
            lines.append(self.vlm_summary)
            lines.append("")
        
        # Accessibility elements (most reliable)
        if self.accessibility_elements:
            lines.append(f"=== INTERACTIVE ELEMENTS ({len(self.accessibility_elements)}) ===")
            for elem in self.accessibility_elements[:30]:  # Limit to avoid token overflow
                if elem.center:
                    cx, cy = elem.center
                    text = elem.title or elem.value or elem.description or ""
                    lines.append(f"  [{elem.role}] '{text}' → click({cx}, {cy})")
            lines.append("")
        
        # VLM semantic elements (additional context)
        if self.vlm_elements:
            lines.append("=== SEMANTIC ELEMENTS ===")
            for elem in self.vlm_elements[:20]:
                text = elem.text_content or elem.description
                lines.append(f"  {elem.role}: {text}")
            lines.append("")
        
        # OCR text (fallback context)
        if self.ocr_text and not self.accessibility_elements:
            lines.append("=== SCREEN TEXT (OCR) ===")
            lines.append(self.ocr_text[:500])  # Limit OCR text
            lines.append("")
        
        # Meta
        lines.append(f"[Method: {self.method_used}, Confidence: {self.confidence:.2f}, Time: {self.processing_time:.2f}s]")
        
        result = "\n".join(lines)
        
        # Truncate if too long
        if len(result) > max_length:
            result = result[:max_length-50] + "\n\n... (truncated for length)"
        
        return result


class ScreenUnderstandingCoordinator:
    """
    Orchestrates multiple screen understanding methods.
    Intelligently routes to the best method based on context.
    """
    
    def __init__(
        self,
        use_accessibility: bool = True,
        use_vlm: bool = True,
        use_ocr: bool = True,
        vlm_threshold: float = 0.7  # Use VLM if accessibility confidence < threshold
    ):
        """
        Initialize coordinator.
        
        Args:
            use_accessibility: Enable accessibility API
            use_vlm: Enable VLM parsing
            use_ocr: Enable OCR fallback
            vlm_threshold: Confidence threshold for triggering VLM
        """
        if not MODULES_AVAILABLE:
            raise RuntimeError("Required modules not available")
        
        self.use_accessibility = use_accessibility
        self.use_vlm = use_vlm
        self.use_ocr = use_ocr
        self.vlm_threshold = vlm_threshold
        
        # Initialize APIs
        self.accessibility_api = AccessibilityAPI() if use_accessibility else None
        self.vlm_parser = VLMScreenParser() if use_vlm else None
        
        # Performance tracking
        self._stats = {
            "accessibility_calls": 0,
            "vlm_calls": 0,
            "ocr_calls": 0,
            "hybrid_calls": 0
        }
    
    def _capture_screenshot(self) -> bytes:
        """Capture current screen as bytes."""
        screenshot = pyautogui.screenshot()
        img_bytes = io.BytesIO()
        screenshot.save(img_bytes, format='PNG')
        return img_bytes.getvalue()
    
    def _assess_accessibility_completeness(self, tree: Optional[AXElement]) -> float:
        """
        Assess how complete the accessibility tree is.
        
        Returns:
            Confidence score 0.0-1.0
        """
        if not tree:
            return 0.0
        
        # Count useful elements
        useful_elements = 0
        total_elements = 0
        
        def count_elements(elem):
            nonlocal useful_elements, total_elements
            total_elements += 1
            
            # Element is "useful" if it has position and text/action
            if elem.position and (elem.title or elem.value or elem.actions):
                useful_elements += 1
            
            for child in elem.children:
                count_elements(child)
        
        count_elements(tree)
        
        if total_elements == 0:
            return 0.0
        
        # Calculate confidence
        usefulness_ratio = useful_elements / total_elements
        
        # Penalize if very few elements
        if total_elements < 5:
            usefulness_ratio *= 0.5
        
        return min(1.0, usefulness_ratio)
    
    def understand_screen(
        self,
        task_context: str = "",
        force_vlm: bool = False,
        screenshot: Optional[bytes] = None
    ) -> ScreenUnderstanding:
        """
        Main function: Understand current screen using best available methods.
        
        Args:
            task_context: Optional context about the task being performed
            force_vlm: Force VLM usage even if accessibility is good
            screenshot: Optional pre-captured screenshot (otherwise captures new)
            
        Returns:
            ScreenUnderstanding with comprehensive data
        """
        start_time = time.time()
        understanding = ScreenUnderstanding()
        
        # Get app info
        if self.accessibility_api:
            app_info = self.accessibility_api.get_frontmost_app_info()
            understanding.app_name = app_info.get("app", "")
            understanding.window_title = app_info.get("window", "")
        
        # Step 1: Try Accessibility API (fast, preferred)
        accessibility_confidence = 0.0
        if self.use_accessibility and self.accessibility_api:
            logger.debug("Attempting accessibility API parsing...")
            tree = self.accessibility_api.get_ui_tree(max_depth=5)
            
            if tree:
                understanding.accessibility_tree = tree
                
                # Flatten tree to list of useful elements
                def collect_elements(elem, results):
                    if elem.position and elem.role != "AXWindow":
                        results.append(elem)
                    for child in elem.children:
                        collect_elements(child, results)
                
                collect_elements(tree, understanding.accessibility_elements)
                
                # Assess completeness
                accessibility_confidence = self._assess_accessibility_completeness(tree)
                
                logger.info(f"Accessibility API: {len(understanding.accessibility_elements)} elements, confidence: {accessibility_confidence:.2f}")
                self._stats["accessibility_calls"] += 1
        
        # Step 2: Use VLM if needed
        use_vlm_parsing = (
            self.use_vlm and 
            (force_vlm or accessibility_confidence < self.vlm_threshold)
        )
        
        if use_vlm_parsing and self.vlm_parser:
            logger.debug("Using VLM for semantic understanding...")
            
            # Capture screenshot if not provided
            if screenshot is None:
                screenshot = self._capture_screenshot()
            
            # Parse with VLM
            parsed = self.vlm_parser.parse_screen(screenshot, task_context)
            understanding.vlm_summary = parsed.summary
            understanding.vlm_elements = parsed.elements
            
            logger.info(f"VLM parsing: {len(parsed.elements)} elements")
            self._stats["vlm_calls"] += 1
        
        # Step 3: OCR fallback if both failed
        if self.use_ocr and not understanding.accessibility_elements and not understanding.vlm_elements:
            logger.debug("Using OCR fallback...")
            
            if screenshot is None:
                screenshot = self._capture_screenshot()
            
            ocr_result = ocr_screenshot(screenshot)
            understanding.ocr_text = ocr_result.get("text", "")
            understanding.ocr_elements = ocr_result.get("elements", [])
            
            logger.info(f"OCR extracted: {len(understanding.ocr_text)} chars")
            self._stats["ocr_calls"] += 1
        
        # Determine method used and confidence
        if understanding.accessibility_elements and understanding.vlm_elements:
            understanding.method_used = "hybrid"
            understanding.confidence = max(accessibility_confidence, 0.8)
            self._stats["hybrid_calls"] += 1
        elif understanding.accessibility_elements:
            understanding.method_used = "accessibility"
            understanding.confidence = accessibility_confidence
        elif understanding.vlm_elements:
            understanding.method_used = "vlm"
            understanding.confidence = 0.75
        elif understanding.ocr_text:
            understanding.method_used = "ocr"
            understanding.confidence = 0.4
        else:
            understanding.method_used = "none"
            understanding.confidence = 0.0
        
        understanding.processing_time = time.time() - start_time
        
        logger.info(f"Screen understanding complete: {understanding.method_used} ({understanding.processing_time:.2f}s)")
        
        return understanding
    
    def find_element(
        self,
        description: str,
        screenshot: Optional[bytes] = None
    ) -> Optional[Tuple[int, int]]:
        """
        Find an element by natural language description.
        
        Args:
            description: Element description (e.g., "submit button", "email field")
            screenshot: Optional screenshot
            
        Returns:
            (x, y) coordinates of element center, or None
        """
        # Try accessibility first
        if self.accessibility_api:
            elements = self.accessibility_api.find_elements_by_text(description)
            if elements:
                elem = elements[0]
                if elem.center:
                    logger.info(f"Found element via accessibility: {elem}")
                    return elem.center
        
        # Try VLM semantic search
        if self.vlm_parser:
            if screenshot is None:
                screenshot = self._capture_screenshot()
            
            bbox = self.vlm_parser.find_element_semantically(screenshot, description)
            if bbox:
                logger.info(f"Found element via VLM: {bbox}")
                return bbox.center
        
        logger.warning(f"Could not find element: '{description}'")
        return None
    
    def get_stats(self) -> Dict:
        """Get performance statistics."""
        return self._stats.copy()


# Convenience functions
_global_coordinator = None

def get_coordinator() -> ScreenUnderstandingCoordinator:
    """Get global coordinator instance."""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = ScreenUnderstandingCoordinator()
    return _global_coordinator


def understand_current_screen(task_context: str = "") -> ScreenUnderstanding:
    """Quick function to understand current screen."""
    return get_coordinator().understand_screen(task_context)


def find_on_screen(description: str) -> Optional[Tuple[int, int]]:
    """Quick function to find element on screen."""
    return get_coordinator().find_element(description)
