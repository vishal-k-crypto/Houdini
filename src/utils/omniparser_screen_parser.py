"""
OmniParser Screen Parser - UI Element Detection with Retina Scaling

Integrates OmniParser V2 into the Houdini Agent's vision system.
Handles macOS Retina display scaling for accurate click coordinates.

CRITICAL: Retina Scaling
    OmniParser returns pixel coordinates from the screenshot.
    On macOS Retina displays (2x scaling), you MUST divide by the
    backing scale factor before passing to PyAutoGUI:
    
    pyautogui_x = omniparser_x / 2.0
    pyautogui_y = omniparser_y / 2.0

Usage:
    parser = OmniParserScreenParser()
    result = parser.find_element("search button")
    if result.found:
        # Coordinates are already scaled for PyAutoGUI
        pyautogui.click(result.x, result.y)
"""

import os
import time
import tempfile
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Check for dependencies
PYAUTOGUI_AVAILABLE = False
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    logger.warning("pyautogui not available")

try:
    from .omniparser_client import (
        OmniParserClient,
        DetectedElement,
        get_omniparser_client,
        omniparser_available,
        OMNIPARSER_AVAILABLE
    )
except ImportError:
    OMNIPARSER_AVAILABLE = False
    logger.info("OmniParser client not available")


@dataclass
class OmniParserResult:
    """Result from OmniParser screen parsing."""
    found: bool
    x: int = 0  # PyAutoGUI-ready X coordinate (Retina scaled)
    y: int = 0  # PyAutoGUI-ready Y coordinate (Retina scaled)
    confidence: float = 0.0
    label: str = ""
    caption: str = ""
    bbox: Optional[Tuple[int, int, int, int]] = None  # Scaled bbox
    raw_bbox: Optional[Tuple[int, int, int, int]] = None  # Original pixel bbox
    method: str = "omniparser"
    reasoning: str = ""
    latency_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found,
            "x": self.x,
            "y": self.y,
            "confidence": self.confidence,
            "label": self.label,
            "caption": self.caption,
            "bbox": self.bbox,
            "method": self.method,
            "reasoning": self.reasoning,
            "latency_ms": self.latency_ms
        }


class OmniParserScreenParser:
    """
    Screen parser using OmniParser V2 for UI element detection.
    
    Automatically handles Retina display scaling on macOS:
    - Detects backing scale factor (usually 2.0 on Retina)
    - Divides all coordinates by scale factor
    - Returns PyAutoGUI-ready coordinates
    """
    
    def __init__(
        self,
        enable_captioning: bool = True,
        lazy_load: bool = True
    ):
        """
        Initialize screen parser.
        
        Args:
            enable_captioning: Use Florence-2 for semantic captions
            lazy_load: Only load OmniParser models when needed
        """
        if not OMNIPARSER_AVAILABLE:
            raise RuntimeError(
                "OmniParser not available. Install:\n"
                "  pip install ultralytics torch"
            )
        
        self.enable_captioning = enable_captioning
        self.lazy_load = lazy_load
        
        # Detect Retina scale factor
        self.scale_factor = self._detect_scale_factor()
        logger.info(f"📱 Retina scale factor: {self.scale_factor}")
        
        # Screen dimensions (PyAutoGUI logical pixels)
        self.screen_width, self.screen_height = self._get_screen_size()
        
        # OmniParser client (lazy loaded)
        self._client: Optional[OmniParserClient] = None
        
        if not lazy_load:
            self._ensure_client()
    
    def _detect_scale_factor(self) -> float:
        """
        Detect macOS Retina backing scale factor.
        
        Returns:
            Scale factor (2.0 for Retina, 1.0 for standard)
        """
        try:
            from AppKit import NSScreen
            main_screen = NSScreen.mainScreen()
            if main_screen:
                scale = main_screen.backingScaleFactor()
                return float(scale)
        except ImportError:
            logger.debug("AppKit not available, trying Quartz")
        except Exception as e:
            logger.debug(f"NSScreen scale detection failed: {e}")
        
        try:
            import Quartz
            display_id = Quartz.CGMainDisplayID()
            mode = Quartz.CGDisplayCopyDisplayMode(display_id)
            if mode:
                pixel_width = Quartz.CGDisplayModeGetPixelWidth(mode)
                point_width = Quartz.CGDisplayModeGetWidth(mode)
                if point_width > 0:
                    return pixel_width / point_width
        except ImportError:
            logger.debug("Quartz not available")
        except Exception as e:
            logger.debug(f"Quartz scale detection failed: {e}")
        
        # Default to 2.0 for safety on modern Macs
        logger.info("⚠️ Could not detect scale factor, defaulting to 2.0 (Retina)")
        return 2.0
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions in logical (PyAutoGUI) coordinates."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)
    
    def _ensure_client(self) -> OmniParserClient:
        """Get or create OmniParser client."""
        if self._client is None:
            self._client = OmniParserClient(
                enable_captioning=self.enable_captioning,
                lazy_load=self.lazy_load
            )
        return self._client
    
    def _scale_coordinates(
        self,
        x: int,
        y: int
    ) -> Tuple[int, int]:
        """
        Scale pixel coordinates to PyAutoGUI logical coordinates.
        
        On Retina displays, PyAutoGUI uses logical points (not pixels).
        OmniParser returns raw pixel coordinates from screenshots.
        We must divide by the scale factor.
        
        Args:
            x: Pixel X coordinate
            y: Pixel Y coordinate
            
        Returns:
            (scaled_x, scaled_y) ready for PyAutoGUI
        """
        scaled_x = int(x / self.scale_factor)
        scaled_y = int(y / self.scale_factor)
        
        # Clamp to screen bounds
        scaled_x = max(0, min(scaled_x, self.screen_width - 1))
        scaled_y = max(0, min(scaled_y, self.screen_height - 1))
        
        return scaled_x, scaled_y
    
    def _scale_bbox(
        self,
        bbox: Tuple[int, int, int, int]
    ) -> Tuple[int, int, int, int]:
        """Scale bounding box to logical coordinates."""
        x1, y1, x2, y2 = bbox
        sx1, sy1 = self._scale_coordinates(x1, y1)
        sx2, sy2 = self._scale_coordinates(x2, y2)
        return (sx1, sy1, sx2, sy2)
    
    def take_screenshot(self) -> str:
        """
        Capture current screen and return path to temp file.
        
        Returns:
            Path to PNG screenshot (full Retina resolution)
        """
        if not PYAUTOGUI_AVAILABLE:
            raise RuntimeError("pyautogui required for screenshots")
        
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        
        logger.debug(f"📸 Screenshot saved: {path}")
        return path
    
    def detect_all_elements(
        self,
        image_path: Optional[str] = None,
        confidence_threshold: float = 0.3
    ) -> List[OmniParserResult]:
        """
        Detect all UI elements on screen.
        
        Args:
            image_path: Screenshot path (auto-captures if None)
            confidence_threshold: Minimum confidence
            
        Returns:
            List of OmniParserResult with scaled coordinates
        """
        start_time = time.time()
        temp_screenshot = None
        
        try:
            if image_path is None:
                temp_screenshot = self.take_screenshot()
                image_path = temp_screenshot
            
            client = self._ensure_client()
            elements = client.detect_elements(
                image_path,
                confidence_threshold=confidence_threshold
            )
            
            results = []
            for elem in elements:
                # Scale center coordinates
                raw_cx, raw_cy = elem.center
                scaled_cx, scaled_cy = self._scale_coordinates(raw_cx, raw_cy)
                
                results.append(OmniParserResult(
                    found=True,
                    x=scaled_cx,
                    y=scaled_cy,
                    confidence=elem.confidence,
                    label=elem.label,
                    caption=elem.caption,
                    bbox=self._scale_bbox(elem.bbox),
                    raw_bbox=elem.bbox,
                    method="omniparser",
                    latency_ms=(time.time() - start_time) * 1000
                ))
            
            return results
            
        finally:
            if temp_screenshot and os.path.exists(temp_screenshot):
                try:
                    os.remove(temp_screenshot)
                except:
                    pass
    
    def find_element(
        self,
        description: str,
        image_path: Optional[str] = None,
        confidence_threshold: float = 0.3
    ) -> OmniParserResult:
        """
        Find a specific UI element by description.
        
        Args:
            description: What to find (e.g., "search button", "close icon")
            image_path: Screenshot path (auto-captures if None)
            confidence_threshold: Minimum confidence
            
        Returns:
            OmniParserResult with found=True/False and scaled coordinates
        """
        start_time = time.time()
        temp_screenshot = None
        
        try:
            if image_path is None:
                temp_screenshot = self.take_screenshot()
                image_path = temp_screenshot
            
            client = self._ensure_client()
            element = client.find_element(
                image_path,
                description,
                confidence_threshold
            )
            
            elapsed = (time.time() - start_time) * 1000
            
            if element is None:
                return OmniParserResult(
                    found=False,
                    method="omniparser",
                    reasoning=f"No element matching '{description}'",
                    latency_ms=elapsed
                )
            
            # Scale coordinates
            raw_cx, raw_cy = element.center
            scaled_cx, scaled_cy = self._scale_coordinates(raw_cx, raw_cy)
            
            return OmniParserResult(
                found=True,
                x=scaled_cx,
                y=scaled_cy,
                confidence=element.confidence,
                label=element.label,
                caption=element.caption,
                bbox=self._scale_bbox(element.bbox),
                raw_bbox=element.bbox,
                method="omniparser",
                reasoning=f"Found '{element.label}' matching '{description}'",
                latency_ms=elapsed
            )
            
        finally:
            if temp_screenshot and os.path.exists(temp_screenshot):
                try:
                    os.remove(temp_screenshot)
                except:
                    pass
    
    def click_element(
        self,
        description: str,
        image_path: Optional[str] = None,
        **kwargs
    ) -> OmniParserResult:
        """
        Find and click a UI element.
        
        Args:
            description: What to click
            image_path: Optional screenshot path
            **kwargs: Passed to find_element
            
        Returns:
            OmniParserResult with click result
        """
        result = self.find_element(description, image_path, **kwargs)
        
        if result.found and PYAUTOGUI_AVAILABLE:
            try:
                # Natural movement
                current_x, current_y = pyautogui.position()
                distance = ((result.x - current_x)**2 + (result.y - current_y)**2)**0.5
                duration = min(0.5, max(0.1, distance / 1000))
                
                pyautogui.moveTo(result.x, result.y, duration=duration)
                pyautogui.click()
                
                result.reasoning += " → clicked"
                logger.info(f"  🖱️ OmniParser clicked at ({result.x}, {result.y})")
                
            except Exception as e:
                result.reasoning += f" → click failed: {e}"
        
        return result


# Convenience functions
_global_parser: Optional[OmniParserScreenParser] = None


def get_omniparser_screen_parser() -> OmniParserScreenParser:
    """Get or create global OmniParserScreenParser instance."""
    global _global_parser
    if _global_parser is None:
        _global_parser = OmniParserScreenParser(lazy_load=True)
    return _global_parser


def omniparser_find_element(description: str) -> OmniParserResult:
    """
    Convenience function to find element using OmniParser.
    
    Example:
        result = omniparser_find_element("the search button")
        if result.found:
            pyautogui.click(result.x, result.y)
    """
    return get_omniparser_screen_parser().find_element(description)
