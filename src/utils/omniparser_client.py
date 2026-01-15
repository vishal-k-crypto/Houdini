"""
OmniParser Client - Wrapper for Microsoft OmniParser V2.

Uses YOLOv8 for UI element detection and Florence-2 for icon captioning.
Provides superior UI parsing for non-accessible applications like:
- Adobe Creative Cloud
- Electron apps (Slack, Discord, VS Code)
- Custom Qt/GTK interfaces
- Games and media players

Model weights are lazy-loaded from HuggingFace on first use.
"""

import os
import io
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from PIL import Image

logger = logging.getLogger(__name__)

# Lazy imports for heavy dependencies
_torch = None
_ultralytics = None
_transformers = None

def _lazy_import_torch():
    global _torch
    if _torch is None:
        import torch
        _torch = torch
    return _torch

def _lazy_import_ultralytics():
    global _ultralytics
    if _ultralytics is None:
        from ultralytics import YOLO
        _ultralytics = YOLO
    return _ultralytics

def _lazy_import_transformers():
    global _transformers
    if _transformers is None:
        from transformers import AutoProcessor, AutoModelForCausalLM
        _transformers = (AutoProcessor, AutoModelForCausalLM)
    return _transformers


@dataclass
class BoundingBox:
    """Bounding box for detected UI element."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 1.0
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of bounding box."""
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
    
    @property
    def width(self) -> int:
        return self.x2 - self.x1
    
    @property
    def height(self) -> int:
        return self.y2 - self.y1
    
    @property
    def area(self) -> int:
        return self.width * self.height
    
    def __str__(self) -> str:
        return f"Box({self.x1}, {self.y1}, {self.x2}, {self.y2}) conf={self.confidence:.2f}"


@dataclass
class DetectedElement:
    """A UI element detected by OmniParser."""
    id: int
    bounding_box: BoundingBox
    caption: str = ""
    element_type: str = "unknown"  # button, icon, text, input, etc.
    is_interactable: bool = True
    ocr_text: str = ""
    
    @property
    def center(self) -> Tuple[int, int]:
        return self.bounding_box.center
    
    @property
    def confidence(self) -> float:
        return self.bounding_box.confidence
    
    def __str__(self) -> str:
        label = self.caption or self.ocr_text or f"element_{self.id}"
        return f"[{self.id}] {label} at {self.bounding_box}"


@dataclass
class ParsedScreen:
    """Result of OmniParser screen analysis."""
    elements: List[DetectedElement] = field(default_factory=list)
    screen_width: int = 0
    screen_height: int = 0
    parse_time_ms: float = 0.0
    annotated_image: Optional[bytes] = None
    
    def get_element_by_id(self, element_id: int) -> Optional[DetectedElement]:
        """Get element by its ID."""
        for elem in self.elements:
            if elem.id == element_id:
                return elem
        return None
    
    def find_by_caption(self, query: str, threshold: float = 0.5) -> List[DetectedElement]:
        """Find elements with captions matching query."""
        query_lower = query.lower()
        matches = []
        for elem in self.elements:
            caption_lower = (elem.caption or "").lower()
            ocr_lower = (elem.ocr_text or "").lower()
            
            # Simple substring match - could use fuzzy matching
            if query_lower in caption_lower or query_lower in ocr_lower:
                matches.append(elem)
        
        return sorted(matches, key=lambda e: e.confidence, reverse=True)


class OmniParserClient:
    """
    Client for Microsoft OmniParser V2.
    
    Uses:
    - YOLOv8 fine-tuned for UI element detection
    - Florence-2 for icon captioning and description
    
    Models are lazy-loaded from HuggingFace on first use.
    """
    
    DEFAULT_WEIGHTS_DIR = "weights/omniparser"
    HUGGINGFACE_REPO = "microsoft/OmniParser-v2.0"
    
    def __init__(
        self,
        weights_dir: Optional[str] = None,
        device: Optional[str] = None,
        enable_captioning: bool = True,
        detection_confidence: float = 0.5,
    ):
        """
        Initialize OmniParser client.
        
        Args:
            weights_dir: Directory containing model weights
            device: Device to run models on ('cuda', 'mps', 'cpu', or None for auto)
            enable_captioning: Whether to use Florence-2 for icon captioning
            detection_confidence: Minimum detection confidence threshold
        """
        self.weights_dir = Path(weights_dir or self.DEFAULT_WEIGHTS_DIR)
        self.enable_captioning = enable_captioning
        self.detection_confidence = detection_confidence
        
        # Auto-detect device
        if device is None:
            torch = _lazy_import_torch()
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device
        
        # Models (lazy loaded)
        self._detection_model = None
        self._caption_processor = None
        self._caption_model = None
        self._models_loaded = False
        
        logger.info(f"OmniParser initialized (device: {self.device}, captioning: {enable_captioning})")
    
    def _ensure_weights_downloaded(self) -> bool:
        """Download model weights if not present."""
        icon_detect_path = self.weights_dir / "icon_detect" / "model.pt"
        icon_caption_path = self.weights_dir / "icon_caption_florence"
        
        if icon_detect_path.exists() and icon_caption_path.exists():
            return True
        
        logger.info(f"Downloading OmniParser weights to {self.weights_dir}...")
        
        try:
            from huggingface_hub import hf_hub_download, snapshot_download
            
            # Download detection model
            self.weights_dir.mkdir(parents=True, exist_ok=True)
            
            # Download specific files for detection
            for filename in ["train_args.yaml", "model.pt", "model.yaml"]:
                hf_hub_download(
                    repo_id=self.HUGGINGFACE_REPO,
                    filename=f"icon_detect/{filename}",
                    local_dir=str(self.weights_dir),
                )
            
            # Download caption model
            for filename in ["config.json", "generation_config.json", "model.safetensors"]:
                hf_hub_download(
                    repo_id=self.HUGGINGFACE_REPO,
                    filename=f"icon_caption/{filename}",
                    local_dir=str(self.weights_dir),
                )
            
            # Rename icon_caption to icon_caption_florence
            icon_caption_src = self.weights_dir / "icon_caption"
            if icon_caption_src.exists() and not icon_caption_path.exists():
                icon_caption_src.rename(icon_caption_path)
            
            logger.info("✅ OmniParser weights downloaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download OmniParser weights: {e}")
            return False
    
    def _load_models(self):
        """Load detection and captioning models."""
        if self._models_loaded:
            return
        
        if not self._ensure_weights_downloaded():
            raise RuntimeError("Failed to download OmniParser weights")
        
        import time
        start_time = time.time()
        
        # Load detection model (YOLOv8)
        YOLO = _lazy_import_ultralytics()
        detection_path = self.weights_dir / "icon_detect" / "model.pt"
        self._detection_model = YOLO(str(detection_path))
        logger.info(f"Loaded YOLOv8 detection model from {detection_path}")
        
        # Load captioning model (Florence-2)
        if self.enable_captioning:
            AutoProcessor, AutoModelForCausalLM = _lazy_import_transformers()
            torch = _lazy_import_torch()
            
            caption_path = self.weights_dir / "icon_caption_florence"
            self._caption_processor = AutoProcessor.from_pretrained(
                str(caption_path), 
                trust_remote_code=True
            )
            self._caption_model = AutoModelForCausalLM.from_pretrained(
                str(caption_path),
                trust_remote_code=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device)
            
            logger.info(f"Loaded Florence-2 caption model from {caption_path}")
        
        load_time = time.time() - start_time
        logger.info(f"OmniParser models loaded in {load_time:.2f}s")
        self._models_loaded = True
    
    def detect_elements(
        self,
        screenshot: bytes,
        confidence_threshold: Optional[float] = None
    ) -> List[DetectedElement]:
        """
        Detect UI elements in screenshot.
        
        Args:
            screenshot: Screenshot as bytes (PNG/JPEG)
            confidence_threshold: Override default confidence threshold
            
        Returns:
            List of detected elements with bounding boxes
        """
        self._load_models()
        
        threshold = confidence_threshold or self.detection_confidence
        
        # Convert bytes to PIL Image
        image = Image.open(io.BytesIO(screenshot))
        
        # Run detection
        results = self._detection_model(image, conf=threshold, verbose=False)
        
        elements = []
        for idx, result in enumerate(results[0].boxes):
            box = result.xyxy[0].cpu().numpy()
            conf = float(result.conf[0].cpu().numpy())
            
            bbox = BoundingBox(
                x1=int(box[0]),
                y1=int(box[1]),
                x2=int(box[2]),
                y2=int(box[3]),
                confidence=conf,
            )
            
            element = DetectedElement(
                id=idx,
                bounding_box=bbox,
                element_type="icon",  # YOLOv8 detects icons
            )
            elements.append(element)
        
        logger.info(f"Detected {len(elements)} UI elements")
        return elements
    
    def caption_elements(
        self,
        screenshot: bytes,
        elements: List[DetectedElement],
        max_caption_length: int = 50
    ) -> List[DetectedElement]:
        """
        Generate captions for detected elements using Florence-2.
        
        Args:
            screenshot: Original screenshot
            elements: Elements with bounding boxes
            max_caption_length: Maximum caption length
            
        Returns:
            Elements with captions filled in
        """
        if not self.enable_captioning or not self._caption_model:
            return elements
        
        self._load_models()
        torch = _lazy_import_torch()
        
        image = Image.open(io.BytesIO(screenshot))
        
        for elem in elements:
            try:
                # Crop element from image
                bbox = elem.bounding_box
                cropped = image.crop((bbox.x1, bbox.y1, bbox.x2, bbox.y2))
                
                # Prepare input
                prompt = "<CAPTION>"
                inputs = self._caption_processor(
                    text=prompt,
                    images=cropped,
                    return_tensors="pt"
                ).to(self.device)
                
                # Generate caption
                with torch.no_grad():
                    generated_ids = self._caption_model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=max_caption_length,
                        num_beams=3,
                    )
                
                # Decode caption
                caption = self._caption_processor.batch_decode(
                    generated_ids,
                    skip_special_tokens=True
                )[0]
                
                # Clean up caption
                caption = caption.replace("<CAPTION>", "").strip()
                elem.caption = caption
                
            except Exception as e:
                logger.warning(f"Failed to caption element {elem.id}: {e}")
                elem.caption = ""
        
        return elements
    
    def parse_screen(
        self,
        screenshot: bytes,
        with_captions: bool = True
    ) -> ParsedScreen:
        """
        Full screen parsing: detect elements and generate captions.
        
        Args:
            screenshot: Screenshot as bytes
            with_captions: Whether to generate captions (slower but more info)
            
        Returns:
            ParsedScreen with all detected elements
        """
        import time
        start_time = time.time()
        
        # Get image dimensions
        image = Image.open(io.BytesIO(screenshot))
        width, height = image.size
        
        # Detect elements
        elements = self.detect_elements(screenshot)
        
        # Generate captions if requested
        if with_captions and self.enable_captioning:
            elements = self.caption_elements(screenshot, elements)
        
        parse_time = (time.time() - start_time) * 1000
        
        result = ParsedScreen(
            elements=elements,
            screen_width=width,
            screen_height=height,
            parse_time_ms=parse_time,
        )
        
        logger.info(f"Parsed screen: {len(elements)} elements in {parse_time:.0f}ms")
        return result
    
    def get_annotated_image(
        self,
        screenshot: bytes,
        elements: Optional[List[DetectedElement]] = None
    ) -> bytes:
        """
        Create annotated screenshot with bounding boxes and IDs.
        
        Args:
            screenshot: Original screenshot
            elements: Elements to annotate (or None to detect)
            
        Returns:
            Annotated image as PNG bytes
        """
        from PIL import ImageDraw, ImageFont
        
        image = Image.open(io.BytesIO(screenshot))
        draw = ImageDraw.Draw(image)
        
        if elements is None:
            elements = self.detect_elements(screenshot)
        
        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Monaco.ttf", 14)
        except:
            font = ImageFont.load_default()
        
        # Draw boxes and labels
        for elem in elements:
            bbox = elem.bounding_box
            
            # Box color based on confidence
            if bbox.confidence > 0.8:
                color = (0, 255, 0)  # Green
            elif bbox.confidence > 0.5:
                color = (255, 165, 0)  # Orange
            else:
                color = (255, 0, 0)  # Red
            
            # Draw rectangle
            draw.rectangle(
                [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                outline=color,
                width=2
            )
            
            # Draw ID label
            label = f"[{elem.id}]"
            if elem.caption:
                label += f" {elem.caption[:20]}"
            
            # Background for text
            text_bbox = draw.textbbox((bbox.x1, bbox.y1 - 16), label, font=font)
            draw.rectangle(text_bbox, fill=(0, 0, 0))
            draw.text((bbox.x1, bbox.y1 - 16), label, fill=color, font=font)
        
        # Convert to bytes
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


# Global client instance (lazy initialized)
_global_client: Optional[OmniParserClient] = None


def get_omniparser_client(**kwargs) -> OmniParserClient:
    """Get or create global OmniParser client instance."""
    global _global_client
    if _global_client is None:
        _global_client = OmniParserClient(**kwargs)
    return _global_client


def is_omniparser_available() -> bool:
    """Check if OmniParser dependencies are available."""
    try:
        import torch
        import ultralytics
        import transformers
        return True
    except ImportError:
        return False
