"""
OmniParser V2 Client - YOLOv8 + Florence-2 Vision Model

Microsoft OmniParser V2 integration for UI element detection and captioning.
Optimized for Apple Silicon with Metal/MPS acceleration.

Features:
- YOLOv8-based icon detection (fast, precise bounding boxes)
- Florence-2 captioning (semantic understanding of detected elements)
- 60% latency reduction vs V1
- Improves GPT-4V action accuracy: 70% → 93%

Usage:
    client = OmniParserClient()
    elements = client.detect_elements(screenshot_path)
    for elem in elements:
        print(f"{elem.label} at {elem.bbox}")
"""

import os
import time
import logging
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Check for required dependencies
ULTRALYTICS_AVAILABLE = False
TRANSFORMERS_AVAILABLE = False
TORCH_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
    # Check for MPS (Metal Performance Shaders) on Apple Silicon
    MPS_AVAILABLE = torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False
except ImportError:
    MPS_AVAILABLE = False
    logger.warning("PyTorch not available - OmniParser will not work")

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    logger.info("ultralytics not available - install: pip install ultralytics")

try:
    from transformers import AutoProcessor, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.info("transformers not available - install: pip install transformers")

# OmniParser is available if we have the core deps
OMNIPARSER_AVAILABLE = ULTRALYTICS_AVAILABLE and TORCH_AVAILABLE


@dataclass
class DetectedElement:
    """Represents a detected UI element from OmniParser."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in pixels
    label: str  # Element type (button, icon, text, etc.)
    caption: str  # Semantic description from Florence-2
    confidence: float  # Detection confidence 0-1
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of element."""
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)
    
    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]
    
    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]
    
    @property
    def area(self) -> int:
        return self.width * self.height
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": self.bbox,
            "center": self.center,
            "label": self.label,
            "caption": self.caption,
            "confidence": self.confidence,
            "width": self.width,
            "height": self.height
        }


class OmniParserClient:
    """
    OmniParser V2 client for UI element detection.
    
    Uses a two-stage approach:
    1. YOLOv8 - Fast detection of UI element bounding boxes
    2. Florence-2 - Semantic captioning of detected elements (optional)
    
    Optimized for Apple Silicon with MPS acceleration.
    """
    
    # Model paths/IDs
    YOLO_MODEL = "microsoft/OmniParser-v2-icon-detect"  # Or local path
    FLORENCE_MODEL = "microsoft/Florence-2-base"  # For captioning
    
    def __init__(
        self,
        enable_captioning: bool = True,
        lazy_load: bool = True,
        device: Optional[str] = None,
        yolo_model_path: Optional[str] = None,
        florence_model_path: Optional[str] = None
    ):
        """
        Initialize OmniParser client.
        
        Args:
            enable_captioning: Use Florence-2 for semantic captions (slower but more accurate)
            lazy_load: Only load models when first needed (saves memory)
            device: Force device ('mps', 'cuda', 'cpu'). Auto-detects if None.
            yolo_model_path: Custom path to YOLO model weights
            florence_model_path: Custom path to Florence-2 model
        """
        if not OMNIPARSER_AVAILABLE:
            raise RuntimeError(
                "OmniParser dependencies not available. Install:\n"
                "  pip install ultralytics torch\n"
                "  pip install transformers (optional, for captioning)"
            )
        
        self.enable_captioning = enable_captioning and TRANSFORMERS_AVAILABLE
        self.lazy_load = lazy_load
        
        # Custom model paths
        self.yolo_model_path = yolo_model_path or self.YOLO_MODEL
        self.florence_model_path = florence_model_path or self.FLORENCE_MODEL
        
        # Determine device
        if device:
            self.device = device
        elif MPS_AVAILABLE:
            self.device = "mps"
            logger.info("🍎 OmniParser using MPS (Metal) acceleration")
        elif TORCH_AVAILABLE and torch.cuda.is_available():
            self.device = "cuda"
            logger.info("🎮 OmniParser using CUDA acceleration")
        else:
            self.device = "cpu"
            logger.info("💻 OmniParser using CPU")
        
        # Model instances (lazy loaded)
        self._yolo_model = None
        self._florence_model = None
        self._florence_processor = None
        self._loaded = False
        
        # Load immediately if not lazy
        if not lazy_load:
            self._ensure_loaded()
        
        logger.info(f"✅ OmniParserClient initialized (device={self.device}, lazy={lazy_load})")
    
    def _ensure_loaded(self):
        """Ensure models are loaded."""
        if self._loaded:
            return
        
        start = time.time()
        logger.info("⏳ Loading OmniParser models...")
        
        # Load YOLO icon detector
        try:
            self._yolo_model = YOLO(self.yolo_model_path)
            # Move to device if supported
            if self.device != "cpu":
                self._yolo_model.to(self.device)
            logger.info(f"  ✅ YOLO model loaded")
        except Exception as e:
            logger.warning(f"  ⚠️ Failed to load YOLO from {self.yolo_model_path}: {e}")
            # Try fallback to default YOLOv8
            self._yolo_model = YOLO("yolov8n.pt")
            logger.info("  ⚠️ Using fallback YOLOv8n model")
        
        # Load Florence-2 for captioning (optional)
        if self.enable_captioning:
            try:
                self._florence_processor = AutoProcessor.from_pretrained(
                    self.florence_model_path,
                    trust_remote_code=True
                )
                self._florence_model = AutoModelForCausalLM.from_pretrained(
                    self.florence_model_path,
                    trust_remote_code=True,
                    torch_dtype=torch.float16 if self.device != "cpu" else torch.float32
                )
                if self.device != "cpu":
                    self._florence_model.to(self.device)
                logger.info(f"  ✅ Florence-2 model loaded")
            except Exception as e:
                logger.warning(f"  ⚠️ Florence-2 not available: {e}")
                self.enable_captioning = False
        
        elapsed = time.time() - start
        logger.info(f"✅ OmniParser models loaded in {elapsed:.1f}s")
        self._loaded = True
    
    def detect_elements(
        self,
        image_path: str,
        confidence_threshold: float = 0.3,
        max_elements: int = 50
    ) -> List[DetectedElement]:
        """
        Detect UI elements in an image.
        
        Args:
            image_path: Path to screenshot image
            confidence_threshold: Minimum detection confidence (0-1)
            max_elements: Maximum elements to return
            
        Returns:
            List of DetectedElement with bboxes, labels, and captions
        """
        self._ensure_loaded()
        start = time.time()
        
        if not os.path.exists(image_path):
            logger.error(f"Image not found: {image_path}")
            return []
        
        elements = []
        
        try:
            # Stage 1: YOLO detection
            results = self._yolo_model.predict(
                image_path,
                conf=confidence_threshold,
                verbose=False
            )
            
            if not results or len(results) == 0:
                logger.info("  No elements detected by YOLO")
                return []
            
            # Process detections
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                
                for i, box in enumerate(boxes):
                    if i >= max_elements:
                        break
                    
                    # Extract bbox (xyxy format)
                    xyxy = box.xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = map(int, xyxy)
                    
                    # Get class and confidence
                    cls_id = int(box.cls[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    
                    # Get label from class names
                    label = result.names.get(cls_id, f"class_{cls_id}")
                    
                    # Create element (caption will be added in stage 2)
                    elements.append(DetectedElement(
                        bbox=(x1, y1, x2, y2),
                        label=label,
                        caption="",  # Filled in stage 2
                        confidence=conf
                    ))
            
            # Stage 2: Caption with Florence-2 (optional)
            if self.enable_captioning and elements:
                elements = self._add_captions(image_path, elements)
            
            elapsed = (time.time() - start) * 1000
            logger.info(f"  🔍 OmniParser detected {len(elements)} elements in {elapsed:.1f}ms")
            
            return elements
            
        except Exception as e:
            logger.error(f"OmniParser detection error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _add_captions(
        self,
        image_path: str,
        elements: List[DetectedElement]
    ) -> List[DetectedElement]:
        """Add semantic captions using Florence-2."""
        if not self._florence_model or not self._florence_processor:
            return elements
        
        try:
            from PIL import Image
            image = Image.open(image_path).convert("RGB")
            
            for elem in elements:
                # Crop to element bbox
                x1, y1, x2, y2 = elem.bbox
                cropped = image.crop((x1, y1, x2, y2))
                
                # Generate caption
                prompt = "<CAPTION>"
                inputs = self._florence_processor(
                    text=prompt,
                    images=cropped,
                    return_tensors="pt"
                )
                
                if self.device != "cpu":
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}
                
                with torch.no_grad():
                    outputs = self._florence_model.generate(
                        **inputs,
                        max_new_tokens=50,
                        num_beams=3
                    )
                
                caption = self._florence_processor.decode(
                    outputs[0],
                    skip_special_tokens=True
                )
                
                # Update element with caption
                elem.caption = caption.strip()
            
            return elements
            
        except Exception as e:
            logger.warning(f"Florence-2 captioning failed: {e}")
            return elements
    
    def find_element(
        self,
        image_path: str,
        description: str,
        confidence_threshold: float = 0.3
    ) -> Optional[DetectedElement]:
        """
        Find a specific element by description.
        
        Args:
            image_path: Path to screenshot
            description: Element to find (e.g., "search button", "close icon")
            confidence_threshold: Minimum detection confidence
            
        Returns:
            Best matching DetectedElement, or None
        """
        elements = self.detect_elements(image_path, confidence_threshold)
        
        if not elements:
            return None
        
        desc_lower = description.lower()
        
        # Score each element
        scored = []
        for elem in elements:
            score = 0.0
            
            # Match by label
            if elem.label.lower() in desc_lower or desc_lower in elem.label.lower():
                score += 0.5
            
            # Match by caption (if available)
            if elem.caption:
                caption_lower = elem.caption.lower()
                if any(word in caption_lower for word in desc_lower.split()):
                    score += 0.4
            
            # Boost by detection confidence
            score += elem.confidence * 0.3
            
            if score > 0:
                scored.append((score, elem))
        
        if not scored:
            return None
        
        # Return best match
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    
    def is_available(self) -> bool:
        """Check if OmniParser is available and can be used."""
        return OMNIPARSER_AVAILABLE


# Singleton instance
_global_client: Optional[OmniParserClient] = None


def get_omniparser_client() -> OmniParserClient:
    """Get or create global OmniParserClient instance."""
    global _global_client
    if _global_client is None:
        _global_client = OmniParserClient(lazy_load=True)
    return _global_client


def omniparser_available() -> bool:
    """Check if OmniParser dependencies are available."""
    return OMNIPARSER_AVAILABLE
