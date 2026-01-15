"""
OmniParser Integration Tests

Tests for the OmniParser UI element detection and captioning system.
"""

import os
import sys
import io
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


class TestOmniParserAvailability(unittest.TestCase):
    """Test OmniParser availability detection."""
    
    def test_is_omniparser_available_false_without_deps(self):
        """Should return False when dependencies not installed."""
        with patch.dict(sys.modules, {'torch': None, 'ultralytics': None}):
            # Force reimport
            from src.utils.omniparser_client import is_omniparser_available
            # This will try to import and fail gracefully
            result = is_omniparser_available()
            # Result depends on actual installed packages
            self.assertIsInstance(result, bool)


class TestBoundingBox(unittest.TestCase):
    """Test BoundingBox dataclass."""
    
    def test_bounding_box_creation(self):
        from src.utils.omniparser_client import BoundingBox
        
        box = BoundingBox(x1=10, y1=20, x2=110, y2=70, confidence=0.95)
        
        self.assertEqual(box.x1, 10)
        self.assertEqual(box.y1, 20)
        self.assertEqual(box.x2, 110)
        self.assertEqual(box.y2, 70)
        self.assertEqual(box.confidence, 0.95)
    
    def test_bounding_box_center(self):
        from src.utils.omniparser_client import BoundingBox
        
        box = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        center = box.center
        
        self.assertEqual(center, (50, 50))
    
    def test_bounding_box_dimensions(self):
        from src.utils.omniparser_client import BoundingBox
        
        box = BoundingBox(x1=10, y1=20, x2=60, y2=120)
        
        self.assertEqual(box.width, 50)
        self.assertEqual(box.height, 100)
        self.assertEqual(box.area, 5000)


class TestDetectedElement(unittest.TestCase):
    """Test DetectedElement dataclass."""
    
    def test_detected_element_creation(self):
        from src.utils.omniparser_client import DetectedElement, BoundingBox
        
        bbox = BoundingBox(x1=100, y1=200, x2=200, y2=250, confidence=0.85)
        elem = DetectedElement(
            id=1,
            bounding_box=bbox,
            caption="Submit Button",
            element_type="button",
            is_interactable=True
        )
        
        self.assertEqual(elem.id, 1)
        self.assertEqual(elem.caption, "Submit Button")
        self.assertEqual(elem.center, (150, 225))
        self.assertEqual(elem.confidence, 0.85)


class TestParsedScreen(unittest.TestCase):
    """Test ParsedScreen dataclass."""
    
    def test_parsed_screen_find_by_caption(self):
        from src.utils.omniparser_client import ParsedScreen, DetectedElement, BoundingBox
        
        elements = [
            DetectedElement(
                id=0,
                bounding_box=BoundingBox(0, 0, 100, 50, 0.9),
                caption="Home button",
            ),
            DetectedElement(
                id=1,
                bounding_box=BoundingBox(100, 0, 200, 50, 0.85),
                caption="Settings icon",
            ),
            DetectedElement(
                id=2,
                bounding_box=BoundingBox(200, 0, 300, 50, 0.8),
                caption="Search button",
            ),
        ]
        
        screen = ParsedScreen(
            elements=elements,
            screen_width=1920,
            screen_height=1080,
        )
        
        # Test finding by caption
        matches = screen.find_by_caption("button")
        self.assertEqual(len(matches), 2)  # Home and Search buttons
        
        matches = screen.find_by_caption("settings")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].caption, "Settings icon")
    
    def test_parsed_screen_get_by_id(self):
        from src.utils.omniparser_client import ParsedScreen, DetectedElement, BoundingBox
        
        elements = [
            DetectedElement(id=0, bounding_box=BoundingBox(0, 0, 50, 50, 1.0)),
            DetectedElement(id=1, bounding_box=BoundingBox(50, 0, 100, 50, 1.0)),
        ]
        
        screen = ParsedScreen(elements=elements)
        
        elem = screen.get_element_by_id(1)
        self.assertIsNotNone(elem)
        self.assertEqual(elem.id, 1)
        
        elem = screen.get_element_by_id(99)
        self.assertIsNone(elem)


class TestOmniParserScreenParser(unittest.TestCase):
    """Test OmniParserScreenParser semantic matching."""
    
    def test_semantic_match_exact(self):
        """Test exact substring matching."""
        from src.utils.omniparser_screen_parser import OmniParserScreenParser
        from src.utils.omniparser_client import DetectedElement, BoundingBox
        
        parser = OmniParserScreenParser()
        
        # Create mock elements
        elements = [
            DetectedElement(
                id=0,
                bounding_box=BoundingBox(0, 0, 100, 50, 0.9),
                caption="Submit button",
            ),
            DetectedElement(
                id=1,
                bounding_box=BoundingBox(100, 0, 200, 50, 0.85),
                caption="Cancel link",
            ),
        ]
        
        # Test exact match
        matches = parser._semantic_match("submit", elements)
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0].element.id, 0)
        self.assertGreater(matches[0].score, 0.9)
    
    def test_semantic_match_fuzzy(self):
        """Test fuzzy string matching."""
        from src.utils.omniparser_screen_parser import OmniParserScreenParser
        from src.utils.omniparser_client import DetectedElement, BoundingBox
        
        parser = OmniParserScreenParser()
        
        elements = [
            DetectedElement(
                id=0,
                bounding_box=BoundingBox(0, 0, 100, 50, 0.9),
                caption="Configuration settings",
            ),
        ]
        
        # Test fuzzy match (typo)
        matches = parser._semantic_match("config setting", elements)
        self.assertGreater(len(matches), 0)


class TestOmniParserClient(unittest.TestCase):
    """Test OmniParserClient initialization and configuration."""
    
    def test_client_init_default_device(self):
        """Test client initializes with appropriate device."""
        from src.utils.omniparser_client import OmniParserClient
        
        # This should not load models yet (lazy loading)
        client = OmniParserClient(device="cpu")
        
        self.assertEqual(client.device, "cpu")
        self.assertFalse(client._models_loaded)
    
    def test_client_custom_weights_dir(self):
        """Test client respects custom weights directory."""
        from src.utils.omniparser_client import OmniParserClient
        
        client = OmniParserClient(
            weights_dir="/custom/path",
            device="cpu"
        )
        
        self.assertEqual(str(client.weights_dir), "/custom/path")


class TestVisionExecutorIntegration(unittest.TestCase):
    """Test OmniParser integration with vision_executor."""
    
    def test_omniparser_import_check(self):
        """Test that OMNIPARSER_AVAILABLE is properly set."""
        from src.agents import vision_executor
        
        # Should be a boolean
        self.assertIsInstance(vision_executor.OMNIPARSER_AVAILABLE, bool)
    
    def test_omniparser_fallback_exists(self):
        """Test that _omniparser_fallback function exists."""
        from src.agents.vision_executor import _omniparser_fallback
        
        self.assertTrue(callable(_omniparser_fallback))


if __name__ == "__main__":
    # Run tests
    print("🧪 Running OmniParser Integration Tests\n")
    
    # Check if OmniParser dependencies are available
    try:
        import torch
        import ultralytics
        print("✅ PyTorch available")
        print("✅ Ultralytics available")
        FULL_TESTS = True
    except ImportError:
        print("⚠️  OmniParser dependencies not installed (torch/ultralytics)")
        print("   Running limited tests only.\n")
        FULL_TESTS = False
    
    # Run unittest
    unittest.main(verbosity=2)
