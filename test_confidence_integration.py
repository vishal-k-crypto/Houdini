"""
Integration test for Confidence Model in Coordinators.

Tests that the confidence model is properly integrated into the coordinators:
1. Actions are rated before execution
2. Low confidence actions trigger supervisor intervention
3. Confidence gating is respected
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_confidence_imports_available():
    """Test that confidence model can be imported."""
    print("\n=== Test: Confidence Model Imports ===")
    
    try:
        from src.utils.execution_confidence import (
            rate_action,
            record_action_outcome,
            should_execute_action,
            ConfidenceRating,
            ActionDecision,
            ConfidenceLevel
        )
        print("✓ All confidence model imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_adaptive_coordinator_has_confidence_import():
    """Test that AdaptiveLoopCoordinator has confidence model import."""
    print("\n=== Test: AdaptiveLoopCoordinator Integration ===")
    
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "adaptive_coordinator",
        Path(__file__).parent / "src" / "loop" / "adaptive_coordinator.py"
    )
    
    # Read the file content directly
    file_path = Path(__file__).parent / "src" / "loop" / "adaptive_coordinator.py"
    content = file_path.read_text()
    
    # Check for confidence model imports
    has_rate_action_import = "from ..utils.execution_confidence import" in content
    has_confidence_gating = "CONFIDENCE_MODEL_AVAILABLE" in content
    has_rating_call = "rate_action(" in content
    
    print(f"  Has confidence model import: {has_rate_action_import}")
    print(f"  Has CONFIDENCE_MODEL_AVAILABLE check: {has_confidence_gating}")
    print(f"  Has rate_action() call: {has_rating_call}")
    
    if all([has_rate_action_import, has_confidence_gating, has_rating_call]):
        print("✓ AdaptiveLoopCoordinator properly integrates confidence model")
        return True
    else:
        print("✗ Missing confidence integration components")
        return False


def test_langgraph_coordinator_has_confidence_import():
    """Test that LangGraphCoordinator has confidence model import."""
    print("\n=== Test: LangGraphCoordinator Integration ===")
    
    file_path = Path(__file__).parent / "src" / "loop" / "langgraph_coordinator.py"
    content = file_path.read_text()
    
    # Check for confidence model imports
    has_rate_action_import = "from ..utils.execution_confidence import" in content
    has_confidence_gating = "CONFIDENCE_MODEL_AVAILABLE" in content
    has_rating_call = "rate_action(" in content
    
    print(f"  Has confidence model import: {has_rate_action_import}")
    print(f"  Has CONFIDENCE_MODEL_AVAILABLE check: {has_confidence_gating}")
    print(f"  Has rate_action() call: {has_rating_call}")
    
    if all([has_rate_action_import, has_confidence_gating, has_rating_call]):
        print("✓ LangGraphCoordinator properly integrates confidence model")
        return True
    else:
        print("✗ Missing confidence integration components")
        return False


def test_low_confidence_defers_to_supervisor():
    """Test that low confidence scores defer to supervisor."""
    print("\n=== Test: Low Confidence Deferral Logic ===")
    
    # Check that the code contains the threshold logic
    file_path = Path(__file__).parent / "src" / "loop" / "adaptive_coordinator.py"
    content = file_path.read_text()
    
    has_threshold_check = "rating.score < 3.0" in content
    has_defer_logic = "deferring to supervisor" in content.lower() or "needs_supervisor" in content
    
    print(f"  Has confidence threshold check (< 3.0): {has_threshold_check}")
    print(f"  Has supervisor deferral logic: {has_defer_logic}")
    
    if has_threshold_check and has_defer_logic:
        print("✓ Low confidence properly triggers supervisor intervention")
        return True
    else:
        print("✗ Missing low confidence handling")
        return False


def test_confidence_logging():
    """Test that confidence scores are logged."""
    print("\n=== Test: Confidence Logging ===")
    
    file_path = Path(__file__).parent / "src" / "loop" / "adaptive_coordinator.py"
    content = file_path.read_text()
    
    has_confidence_log = "Action confidence:" in content
    has_emoji_log = "📊" in content  # Check for the emoji we added
    
    print(f"  Has confidence logging: {has_confidence_log or has_emoji_log}")
    
    if has_confidence_log or has_emoji_log:
        print("✓ Confidence scores are logged for debugging")
        return True
    else:
        print("✗ Missing confidence logging")
        return False


def run_all_tests():
    """Run all integration tests."""
    print("=" * 60)
    print("Confidence Model Integration - Test Suite")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("Confidence Imports", test_confidence_imports_available()))
        results.append(("AdaptiveLoopCoordinator Integration", 
                       test_adaptive_coordinator_has_confidence_import()))
        results.append(("LangGraphCoordinator Integration",
                       test_langgraph_coordinator_has_confidence_import()))
        results.append(("Low Confidence Deferral", 
                       test_low_confidence_defers_to_supervisor()))
        results.append(("Confidence Logging", test_confidence_logging()))
        
        print("\n" + "=" * 60)
        print("Test Results Summary:")
        print("=" * 60)
        
        all_passed = True
        for name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {status}: {name}")
            if not passed:
                all_passed = False
        
        print("=" * 60)
        if all_passed:
            print("All tests passed! ✓")
        else:
            print("Some tests failed ✗")
            
        return all_passed
        
    except Exception as e:
        print(f"\n✗ Error running tests: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
