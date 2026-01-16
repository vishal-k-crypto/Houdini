"""
Local Vision Localizer - Hybrid Apple Vision + UI-TARS MLX
Provides precise pixel localization using native macOS frameworks and local MLX models.

Architecture:
1. Apple Vision Framework (via pyobjc) - Fast geometric detection of UI rectangles
2. UI-TARS via MLX-VLM - Semantic grounding for complex/non-accessible elements

Benefits:
- Hardware-accelerated on Apple Silicon Neural Engine
- Sub-millisecond detection for standard UI shapes
- No cloud latency - runs entirely on-device
- Semantic precision for niche tools (Adobe, Electron apps)
- Uses unified memory architecture efficiently via MLX
"""

import os
import time
import json
import tempfile
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image

from .logging import logger

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not available for screen size detection")

# Apple Vision Framework imports (macOS native)
try:
    import Quartz
    import Vision
    from Cocoa import NSURL, NSData
    from Foundation import NSDictionary
    APPLE_VISION_AVAILABLE = True
except ImportError:
    APPLE_VISION_AVAILABLE = False
    logger.warning("Apple Vision Framework not available (requires pyobjc)")

# MLX-VLM for UI-TARS (Apple Silicon optimized)
try:
    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    MLX_VLM_AVAILABLE = True
except ImportError:
    MLX_VLM_AVAILABLE = False
    logger.info("MLX-VLM not available (optional - for semantic grounding)")


@dataclass
class DetectedRectangle:
    """Represents a detected UI rectangle from Apple Vision."""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    normalized_bbox: Tuple[float, float, float, float]  # Original Vision coordinates
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of rectangle."""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        """Get (x1, y1, x2, y2) bounds."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)
    
    def contains_point(self, px: int, py: int) -> bool:
        """Check if point is inside rectangle."""
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
    
    def distance_to_point(self, px: int, py: int) -> float:
        """Calculate distance from rectangle center to point."""
        cx, cy = self.center
        return ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
    
    def area(self) -> int:
        """Get rectangle area in pixels."""
        return self.width * self.height


@dataclass
class LocalizationResult:
    """Result of element localization."""
    found: bool
    x: int = 0
    y: int = 0
    confidence: float = 0.0
    method: str = "unknown"  # "apple_vision", "ui_tars", "hybrid", "fallback"
    element_description: str = ""
    bounding_box: Optional[Tuple[int, int, int, int]] = None
    reasoning: str = ""
    latency_ms: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "found": self.found,
            "x": self.x,
            "y": self.y,
            "confidence": self.confidence,
            "method": self.method,
            "element": self.element_description,
            "bounding_box": self.bounding_box,
            "reasoning": self.reasoning,
            "latency_ms": self.latency_ms
        }


@dataclass
class UITARSConfig:
    """Configuration for UI-TARS model."""
    model_path: str = "mlx-community/UI-TARS-7B-SFT-4bit"
    max_tokens: int = 256
    temperature: float = 0.1
    verbose: bool = False


class AppleVisionDetector:
    """
    Apple Vision Framework integration for fast geometric detection.
    Uses VNDetectRectanglesRequest for sub-millisecond UI element detection.
    """
    
    def __init__(self):
        if not APPLE_VISION_AVAILABLE:
            raise RuntimeError(
                "Apple Vision Framework not available. "
                "Install: pip install pyobjc-framework-Vision pyobjc-framework-Quartz"
            )
        
        self.screen_width, self.screen_height = self._get_screen_size()
        logger.info(f"✅ Apple Vision initialized ({self.screen_width}x{self.screen_height})")
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        # Fallback using Quartz
        main_display = Quartz.CGMainDisplayID()
        width = Quartz.CGDisplayPixelsWide(main_display)
        height = Quartz.CGDisplayPixelsHigh(main_display)
        return (int(width), int(height))
    
    def detect_rectangles(
        self,
        image_path: str,
        min_size: float = 0.01,
        max_rectangles: int = 50
    ) -> List[DetectedRectangle]:
        """
        Detect all rectangles in image using Apple Vision Framework.
        
        Args:
            image_path: Path to screenshot image
            min_size: Minimum size as fraction of image (0.01 = 1%)
            max_rectangles: Maximum number of rectangles to return
            
        Returns:
            List of DetectedRectangle objects sorted by area (largest first)
        """
        start_time = time.time()
        
        try:
            # Load image using Quartz CIImage
            input_url = NSURL.fileURLWithPath_(image_path)
            ci_image = Quartz.CIImage.imageWithContentsOfURL_(input_url)
            
            if ci_image is None:
                logger.error(f"Failed to load image: {image_path}")
                return []
            
            # Create Vision request handler
            handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(
                ci_image, None
            )
            
            # Configure rectangle detection request
            request = Vision.VNDetectRectanglesRequest.alloc().init()
            request.setMinimumSize_(min_size)
            request.setMaximumObservations_(max_rectangles)
            request.setMinimumConfidence_(0.5)
            request.setMinimumAspectRatio_(0.1)
            request.setMaximumAspectRatio_(10.0)
            
            # Perform detection
            success, error = handler.performRequests_error_([request], None)
            
            if not success or error:
                logger.warning(f"Vision detection failed: {error}")
                return []
            
            # Get image dimensions for coordinate conversion
            img = Image.open(image_path)
            img_width, img_height = img.size
            
            # Process results
            results = []
            observations = request.results() or []
            
            for obs in observations:
                # Vision uses normalized coordinates (0.0-1.0) with origin at bottom-left
                bbox = obs.boundingBox()
                norm_x = bbox.origin.x
                norm_y = bbox.origin.y
                norm_w = bbox.size.width
                norm_h = bbox.size.height
                confidence = obs.confidence()
                
                # Convert to pixel coordinates (flip Y axis - Vision uses bottom-left origin)
                pixel_x = int(norm_x * img_width)
                pixel_y = int((1.0 - norm_y - norm_h) * img_height)  # Flip Y
                pixel_w = int(norm_w * img_width)
                pixel_h = int(norm_h * img_height)
                
                # Scale to screen coordinates if image differs from screen
                scale_x = self.screen_width / img_width
                scale_y = self.screen_height / img_height
                
                screen_x = int(pixel_x * scale_x)
                screen_y = int(pixel_y * scale_y)
                screen_w = int(pixel_w * scale_x)
                screen_h = int(pixel_h * scale_y)
                
                results.append(DetectedRectangle(
                    x=screen_x,
                    y=screen_y,
                    width=screen_w,
                    height=screen_h,
                    confidence=confidence,
                    normalized_bbox=(norm_x, norm_y, norm_w, norm_h)
                ))
            
            # Sort by area (largest first) - usually more important UI elements
            results.sort(key=lambda r: r.area(), reverse=True)
            
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"  🔍 Apple Vision detected {len(results)} rectangles in {elapsed:.1f}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"Apple Vision detection error: {e}")
            return []
    
    def detect_text_regions(self, image_path: str) -> List[Dict]:
        """
        Detect text regions using Vision's text recognition.
        Returns bounding boxes and recognized text.
        """
        start_time = time.time()
        
        try:
            input_url = NSURL.fileURLWithPath_(image_path)
            ci_image = Quartz.CIImage.imageWithContentsOfURL_(input_url)
            
            if ci_image is None:
                return []
            
            handler = Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(
                ci_image, None
            )
            
            # Text recognition request
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)
            
            success, error = handler.performRequests_error_([request], None)
            
            if not success or error:
                return []
            
            img = Image.open(image_path)
            img_width, img_height = img.size
            
            results = []
            for obs in request.results() or []:
                # Get recognized text
                candidates = obs.topCandidates_(1)
                if candidates and len(candidates) > 0:
                    text = candidates[0].string()
                    confidence = candidates[0].confidence()
                    
                    # Get bounding box
                    bbox = obs.boundingBox()
                    
                    # Convert coordinates
                    pixel_x = int(bbox.origin.x * img_width)
                    pixel_y = int((1.0 - bbox.origin.y - bbox.size.height) * img_height)
                    pixel_w = int(bbox.size.width * img_width)
                    pixel_h = int(bbox.size.height * img_height)
                    
                    results.append({
                        "text": text,
                        "x": pixel_x,
                        "y": pixel_y,
                        "width": pixel_w,
                        "height": pixel_h,
                        "center": (pixel_x + pixel_w // 2, pixel_y + pixel_h // 2),
                        "confidence": confidence
                    })
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"  📝 Detected {len(results)} text regions in {elapsed:.1f}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"Text detection error: {e}")
            return []
    
    def find_element_by_text(
        self,
        image_path: str,
        target_text: str,
        fuzzy_match: bool = True
    ) -> Optional[LocalizationResult]:
        """
        Find a UI element by its text content.
        Uses Apple Vision text recognition for fast text matching.
        """
        start_time = time.time()
        
        text_regions = self.detect_text_regions(image_path)
        
        if not text_regions:
            return None
        
        target_lower = target_text.lower()
        best_match = None
        best_score = 0.0
        
        for region in text_regions:
            region_text = region["text"].lower()
            
            # Exact match
            if target_lower == region_text:
                best_match = region
                best_score = 1.0
                break
            
            # Fuzzy matching
            if fuzzy_match:
                # Contains match
                if target_lower in region_text or region_text in target_lower:
                    score = len(target_lower) / max(len(region_text), len(target_lower))
                    if score > best_score:
                        best_match = region
                        best_score = score * 0.9  # Slightly lower than exact match
        
        if best_match:
            elapsed = (time.time() - start_time) * 1000
            return LocalizationResult(
                found=True,
                x=best_match["center"][0],
                y=best_match["center"][1],
                confidence=best_match["confidence"] * best_score,
                method="apple_vision_text",
                element_description=best_match["text"],
                bounding_box=(
                    best_match["x"],
                    best_match["y"],
                    best_match["x"] + best_match["width"],
                    best_match["y"] + best_match["height"]
                ),
                reasoning=f"Found text '{best_match['text']}' matching '{target_text}'",
                latency_ms=elapsed
            )
        
        return None


class UITARSLocalizer:
    """
    UI-TARS via MLX-VLM for semantic UI grounding.
    Specialized model trained for GUI element localization.
    """
    
    def __init__(self, config: Optional[UITARSConfig] = None):
        if not MLX_VLM_AVAILABLE:
            raise RuntimeError(
                "MLX-VLM not available. Install: pip install mlx-vlm"
            )
        
        self.config = config or UITARSConfig()
        self.model = None
        self.processor = None
        self._loaded = False
        
        self.screen_width, self.screen_height = self._get_screen_size()
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)
    
    def _ensure_loaded(self):
        """Lazy-load the model on first use."""
        if not self._loaded:
            logger.info(f"⏳ Loading UI-TARS model: {self.config.model_path}")
            start = time.time()
            
            self.model, self.processor = load(self.config.model_path)
            
            elapsed = time.time() - start
            logger.info(f"✅ UI-TARS loaded in {elapsed:.1f}s")
            self._loaded = True
    
    def find_element(
        self,
        image_path: str,
        element_description: str,
        return_bbox: bool = False
    ) -> LocalizationResult:
        """
        Find UI element using semantic understanding.
        
        Args:
            image_path: Path to screenshot
            element_description: Natural language description (e.g., "the search button")
            return_bbox: If True, also try to get bounding box
            
        Returns:
            LocalizationResult with precise coordinates
        """
        start_time = time.time()
        self._ensure_loaded()
        
        try:
            # Construct grounding prompt for UI-TARS
            if return_bbox:
                prompt = f"Find the bounding box coordinates for: {element_description}"
            else:
                prompt = f"Find the exact pixel coordinates for: {element_description}"
            
            # Generate prediction
            output = generate(
                self.model,
                self.processor,
                prompt,
                [image_path],
                max_tokens=self.config.max_tokens,
                temp=self.config.temperature,
                verbose=self.config.verbose
            )
            
            # Parse the output
            result = self._parse_coordinate_output(output, image_path)
            result.latency_ms = (time.time() - start_time) * 1000
            result.element_description = element_description
            result.method = "ui_tars"
            
            return result
            
        except Exception as e:
            logger.error(f"UI-TARS localization error: {e}")
            return LocalizationResult(
                found=False,
                method="ui_tars",
                element_description=element_description,
                reasoning=f"Error: {str(e)}",
                latency_ms=(time.time() - start_time) * 1000
            )
    
    def _parse_coordinate_output(self, output: str, image_path: str) -> LocalizationResult:
        """Parse UI-TARS output to extract coordinates."""
        try:
            # Get image dimensions for scaling
            img = Image.open(image_path)
            img_width, img_height = img.size
            
            # Try parsing as JSON first
            if "{" in output and "}" in output:
                json_match = output[output.find("{"):output.rfind("}") + 1]
                try:
                    data = json.loads(json_match)
                    
                    # Handle point format: {"point": [x, y]}
                    if "point" in data:
                        point = data["point"]
                        x, y = int(point[0]), int(point[1])
                        
                        # Scale if coordinates are normalized (0-1000 range typical)
                        if x <= 1000 and y <= 1000:
                            x = int(x * img_width / 1000)
                            y = int(y * img_height / 1000)
                        
                        # Scale to screen
                        scale_x = self.screen_width / img_width
                        scale_y = self.screen_height / img_height
                        
                        return LocalizationResult(
                            found=True,
                            x=int(x * scale_x),
                            y=int(y * scale_y),
                            confidence=0.85,
                            reasoning="UI-TARS point prediction"
                        )
                    
                    # Handle bbox format: {"bbox": [x1, y1, x2, y2]}
                    if "bbox" in data:
                        bbox = data["bbox"]
                        x1, y1, x2, y2 = bbox
                        
                        # Scale if normalized
                        if max(bbox) <= 1000:
                            x1 = int(x1 * img_width / 1000)
                            y1 = int(y1 * img_height / 1000)
                            x2 = int(x2 * img_width / 1000)
                            y2 = int(y2 * img_height / 1000)
                        
                        scale_x = self.screen_width / img_width
                        scale_y = self.screen_height / img_height
                        
                        cx = int((x1 + x2) / 2 * scale_x)
                        cy = int((y1 + y2) / 2 * scale_y)
                        
                        return LocalizationResult(
                            found=True,
                            x=cx,
                            y=cy,
                            confidence=0.85,
                            bounding_box=(
                                int(x1 * scale_x),
                                int(y1 * scale_y),
                                int(x2 * scale_x),
                                int(y2 * scale_y)
                            ),
                            reasoning="UI-TARS bbox prediction"
                        )
                except json.JSONDecodeError:
                    pass
            
            # Try regex extraction for coordinate patterns
            import re
            
            # Pattern: (x, y) or [x, y]
            coord_pattern = r'[\(\[]?\s*(\d+)\s*[,\s]\s*(\d+)\s*[\)\]]?'
            matches = re.findall(coord_pattern, output)
            
            if matches:
                x, y = int(matches[0][0]), int(matches[0][1])
                
                # Scale if needed
                if x <= 1000 and y <= 1000:
                    x = int(x * img_width / 1000)
                    y = int(y * img_height / 1000)
                
                scale_x = self.screen_width / img_width
                scale_y = self.screen_height / img_height
                
                return LocalizationResult(
                    found=True,
                    x=int(x * scale_x),
                    y=int(y * scale_y),
                    confidence=0.7,
                    reasoning=f"Parsed from: {output[:100]}"
                )
            
            return LocalizationResult(
                found=False,
                reasoning=f"Could not parse coordinates from: {output[:200]}"
            )
            
        except Exception as e:
            return LocalizationResult(
                found=False,
                reasoning=f"Parse error: {e}"
            )


class LocalVisionLocalizer:
    """
    Hybrid Local Vision Localizer combining Apple Vision + UI-TARS MLX.
    
    Strategy:
    1. Try Apple Vision first (fast geometric detection + text OCR)
    2. Fall back to UI-TARS for semantic understanding
    3. Combine results for maximum accuracy
    
    Usage:
        localizer = LocalVisionLocalizer()
        result = localizer.find_element(screenshot_path, "the search button")
        if result.found:
            pyautogui.click(result.x, result.y)
    """
    
    def __init__(
        self,
        enable_apple_vision: bool = True,
        enable_ui_tars: bool = True,
        ui_tars_config: Optional[UITARSConfig] = None,
        lazy_load_ui_tars: bool = True
    ):
        """
        Initialize the hybrid localizer.
        
        Args:
            enable_apple_vision: Use Apple Vision for geometric detection
            enable_ui_tars: Use UI-TARS for semantic grounding
            ui_tars_config: Configuration for UI-TARS model
            lazy_load_ui_tars: Only load UI-TARS when needed (saves memory)
        """
        self.enable_apple_vision = enable_apple_vision and APPLE_VISION_AVAILABLE
        self.enable_ui_tars = enable_ui_tars and MLX_VLM_AVAILABLE
        self.lazy_load_ui_tars = lazy_load_ui_tars
        
        # Initialize Apple Vision detector
        self.vision_detector = None
        if self.enable_apple_vision:
            try:
                self.vision_detector = AppleVisionDetector()
            except Exception as e:
                logger.warning(f"Failed to initialize Apple Vision: {e}")
                self.enable_apple_vision = False
        
        # Initialize UI-TARS (lazy or eager)
        self.ui_tars = None
        self.ui_tars_config = ui_tars_config or UITARSConfig()
        
        if self.enable_ui_tars and not lazy_load_ui_tars:
            try:
                self.ui_tars = UITARSLocalizer(self.ui_tars_config)
            except Exception as e:
                logger.warning(f"Failed to initialize UI-TARS: {e}")
                self.enable_ui_tars = False
        
        # Screen dimensions
        self.screen_width, self.screen_height = self._get_screen_size()
        
        # Log initialization status
        status = []
        if self.enable_apple_vision:
            status.append("Apple Vision ✅")
        if self.enable_ui_tars:
            status.append(f"UI-TARS ✅ ({'lazy' if lazy_load_ui_tars else 'loaded'})")
        
        if status:
            logger.info(f"🎯 LocalVisionLocalizer: {', '.join(status)}")
        else:
            logger.warning("⚠️ LocalVisionLocalizer: No backends available!")
    
    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)
    
    def _get_ui_tars(self) -> Optional[UITARSLocalizer]:
        """Get or initialize UI-TARS localizer."""
        if not self.enable_ui_tars:
            return None
        
        if self.ui_tars is None and self.lazy_load_ui_tars:
            try:
                self.ui_tars = UITARSLocalizer(self.ui_tars_config)
            except Exception as e:
                logger.warning(f"Failed to load UI-TARS: {e}")
                self.enable_ui_tars = False
                return None
        
        return self.ui_tars
    
    def take_screenshot(self) -> str:
        """Capture current screen and return path to temp file."""
        if not PYAUTOGUI_AVAILABLE:
            raise RuntimeError("pyautogui required for screenshots")
        
        # Create temp file
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        # Capture screen
        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        
        return path
    
    def find_element(
        self,
        element_description: str,
        image_path: Optional[str] = None,
        prefer_text_match: bool = True,
        min_confidence: float = 0.5,
        force_ui_tars: bool = False
    ) -> LocalizationResult:
        """
        Find a UI element using hybrid localization.
        
        Strategy:
        1. If text-like query, try Apple Vision text detection first
        2. Try Apple Vision geometric detection with heuristics
        3. Fall back to UI-TARS semantic understanding
        
        Args:
            element_description: What to find (e.g., "Search button", "Submit")
            image_path: Path to screenshot (auto-captures if None)
            prefer_text_match: Try text matching first for text-like queries
            min_confidence: Minimum confidence threshold
            force_ui_tars: Skip Vision and go directly to UI-TARS
            
        Returns:
            LocalizationResult with found=True/False and coordinates
        """
        start_time = time.time()
        temp_screenshot = None
        
        try:
            # Take screenshot if not provided
            if image_path is None:
                temp_screenshot = self.take_screenshot()
                image_path = temp_screenshot
            
            # Strategy 1: Force UI-TARS if requested
            if force_ui_tars:
                ui_tars = self._get_ui_tars()
                if ui_tars:
                    return ui_tars.find_element(image_path, element_description)
                else:
                    return LocalizationResult(
                        found=False,
                        method="failed",
                        reasoning="UI-TARS not available"
                    )
            
            # Strategy 2: Try Apple Vision text matching first
            if self.enable_apple_vision and prefer_text_match and self.vision_detector:
                result = self.vision_detector.find_element_by_text(
                    image_path, element_description
                )
                if result and result.found and result.confidence >= min_confidence:
                    result.method = "apple_vision_text"
                    logger.info(f"  ✅ Found via Apple Vision text: ({result.x}, {result.y})")
                    return result
            
            # Strategy 3: Analyze rectangles with heuristics
            if self.enable_apple_vision and self.vision_detector:
                rectangles = self.vision_detector.detect_rectangles(image_path)
                
                if rectangles:
                    # Apply heuristics based on element description
                    best_rect = self._select_best_rectangle(
                        rectangles, element_description, image_path
                    )
                    
                    if best_rect:
                        cx, cy = best_rect.center
                        elapsed = (time.time() - start_time) * 1000
                        
                        return LocalizationResult(
                            found=True,
                            x=cx,
                            y=cy,
                            confidence=best_rect.confidence * 0.8,
                            method="apple_vision_geometric",
                            element_description=element_description,
                            bounding_box=best_rect.bounds,
                            reasoning=f"Best matching rectangle of {len(rectangles)} detected",
                            latency_ms=elapsed
                        )
            
            # Strategy 4: Fall back to UI-TARS semantic understanding
            ui_tars = self._get_ui_tars()
            if ui_tars:
                logger.info("  📡 Falling back to UI-TARS semantic grounding...")
                result = ui_tars.find_element(image_path, element_description)
                
                if result.found:
                    result.method = "ui_tars"
                    logger.info(f"  ✅ Found via UI-TARS: ({result.x}, {result.y})")
                    return result
            
            # Nothing found
            elapsed = (time.time() - start_time) * 1000
            return LocalizationResult(
                found=False,
                method="exhausted",
                element_description=element_description,
                reasoning="Could not locate element with any method",
                latency_ms=elapsed
            )
            
        finally:
            # Cleanup temp screenshot
            if temp_screenshot and os.path.exists(temp_screenshot):
                try:
                    os.remove(temp_screenshot)
                except:
                    pass
    
    def _select_best_rectangle(
        self,
        rectangles: List[DetectedRectangle],
        element_description: str,
        image_path: str
    ) -> Optional[DetectedRectangle]:
        """
        Select the best matching rectangle based on element description.
        Uses heuristics about UI element types and positions.
        """
        if not rectangles:
            return None
        
        desc_lower = element_description.lower()
        scored_rects = []
        
        for rect in rectangles:
            score = rect.confidence
            
            # Heuristics based on description keywords
            
            # Search/input fields: usually wider than tall, near top
            if any(kw in desc_lower for kw in ["search", "input", "field", "text"]):
                aspect = rect.width / max(rect.height, 1)
                if 2.0 < aspect < 15.0:  # Wide rectangle
                    score += 0.3
                if rect.y < self.screen_height * 0.3:  # Top third
                    score += 0.2
            
            # Buttons: usually small to medium, squarish
            if any(kw in desc_lower for kw in ["button", "submit", "click", "ok", "cancel"]):
                aspect = rect.width / max(rect.height, 1)
                if 0.5 < aspect < 5.0:  # Relatively squarish
                    score += 0.2
                area_ratio = rect.area() / (self.screen_width * self.screen_height)
                if 0.001 < area_ratio < 0.05:  # Small to medium size
                    score += 0.2
            
            # Icons/tools: small squares
            if any(kw in desc_lower for kw in ["icon", "tool", "menu"]):
                aspect = rect.width / max(rect.height, 1)
                if 0.8 < aspect < 1.2:  # Square-ish
                    score += 0.3
                if rect.area() < (50 * 50):  # Small
                    score += 0.2
            
            # Sidebar elements: left side, narrow
            if any(kw in desc_lower for kw in ["sidebar", "panel", "list"]):
                if rect.x < self.screen_width * 0.3:  # Left third
                    score += 0.3
            
            # Header/nav: top area
            if any(kw in desc_lower for kw in ["header", "nav", "top", "title"]):
                if rect.y < self.screen_height * 0.15:  # Top 15%
                    score += 0.4
            
            scored_rects.append((score, rect))
        
        # Sort by score
        scored_rects.sort(key=lambda x: x[0], reverse=True)
        
        # Return best if score is reasonable
        if scored_rects and scored_rects[0][0] >= 0.5:
            return scored_rects[0][1]
        
        return None
    
    def find_elements(
        self,
        image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect all UI elements in the current screen.
        Returns rectangles and text regions for debugging/visualization.
        """
        temp_screenshot = None
        
        try:
            if image_path is None:
                temp_screenshot = self.take_screenshot()
                image_path = temp_screenshot
            
            result = {
                "rectangles": [],
                "text_regions": [],
                "image_path": image_path
            }
            
            if self.enable_apple_vision and self.vision_detector:
                # Get rectangles
                rectangles = self.vision_detector.detect_rectangles(image_path)
                result["rectangles"] = [
                    {
                        "x": r.x, "y": r.y,
                        "width": r.width, "height": r.height,
                        "center": r.center,
                        "confidence": r.confidence
                    }
                    for r in rectangles
                ]
                
                # Get text regions
                result["text_regions"] = self.vision_detector.detect_text_regions(image_path)
            
            return result
            
        finally:
            if temp_screenshot and os.path.exists(temp_screenshot):
                try:
                    os.remove(temp_screenshot)
                except:
                    pass
    
    def click_element(
        self,
        element_description: str,
        image_path: Optional[str] = None,
        **kwargs
    ) -> LocalizationResult:
        """
        Find and click a UI element.
        
        Args:
            element_description: What to click
            image_path: Optional screenshot path
            **kwargs: Passed to find_element
            
        Returns:
            LocalizationResult with click success
        """
        result = self.find_element(element_description, image_path, **kwargs)
        
        if result.found and PYAUTOGUI_AVAILABLE:
            try:
                pyautogui.click(result.x, result.y)
                result.reasoning += " → clicked"
                logger.info(f"  🖱️ Clicked at ({result.x}, {result.y})")
            except Exception as e:
                result.reasoning += f" → click failed: {e}"
        
        return result


# Convenience function for quick access
_default_localizer: Optional[LocalVisionLocalizer] = None
_adaptive_localizer = None  # Lazy import to avoid circular dependency


def get_local_localizer() -> LocalVisionLocalizer:
    """Get or create the default LocalVisionLocalizer instance."""
    global _default_localizer
    if _default_localizer is None:
        _default_localizer = LocalVisionLocalizer()
    return _default_localizer


def get_adaptive_localizer():
    """
    Get the adaptive vision localizer with feedback loop.
    This is the RECOMMENDED default mode for best accuracy over time.
    """
    global _adaptive_localizer
    if _adaptive_localizer is None:
        try:
            from .vision_feedback_loop import AdaptiveVisionLocalizer
            _adaptive_localizer = AdaptiveVisionLocalizer()
            logger.info("🎯 Using Adaptive Vision Localizer with feedback learning")
        except ImportError as e:
            logger.warning(f"Adaptive localizer not available, using base: {e}")
            _adaptive_localizer = get_local_localizer()
    return _adaptive_localizer


def find_element_locally(
    element_description: str,
    image_path: Optional[str] = None,
    use_adaptive: bool = True,
    app_name: str = "",
    task_context: str = "",
    **kwargs
) -> LocalizationResult:
    """
    Find an element using local vision with optional adaptive learning.
    
    This is the DEFAULT method for finding UI elements. By default,
    uses the adaptive feedback loop which learns from successes/failures.
    
    Args:
        element_description: What to find (e.g., "search button", "close icon")
        image_path: Optional screenshot path (auto-captures if None)
        use_adaptive: Use adaptive mode with learning (default: True)
        app_name: Current app name (helps learning)
        task_context: Context about the task (helps prompting)
        **kwargs: Additional args for localizer
    
    Example:
        result = find_element_locally("the search button")
        if result.found:
            pyautogui.click(result.x, result.y)
            record_click_success(result.element_description, success=True)
    """
    if use_adaptive:
        localizer = get_adaptive_localizer()
        # Adaptive localizer has different signature
        if hasattr(localizer, 'find_element'):
            try:
                return localizer.find_element(
                    element_description=element_description,
                    app_name=app_name,
                    task_context=task_context,
                    image_path=image_path
                )
            except Exception as e:
                logger.warning(f"Adaptive find failed, falling back: {e}")
    
    return get_local_localizer().find_element(element_description, image_path, **kwargs)


def record_click_success(element_description: str, success: bool):
    """
    Record whether a click on an element succeeded.
    This feedback is used to improve future localization.
    
    Args:
        element_description: The element that was clicked
        success: Whether the click achieved the intended result
    
    Example:
        result = find_element_locally("submit button")
        if result.found:
            pyautogui.click(result.x, result.y)
            # Verify the click worked (e.g., check for expected change)
            worked = check_submission_success()
            record_click_success("submit button", success=worked)
    """
    try:
        localizer = get_adaptive_localizer()
        if hasattr(localizer, 'record_click_result'):
            localizer.record_click_result(element_description, success)
            logger.debug(f"📝 Recorded click feedback: {element_description} = {'✅' if success else '❌'}")
    except Exception as e:
        logger.debug(f"Could not record feedback: {e}")
