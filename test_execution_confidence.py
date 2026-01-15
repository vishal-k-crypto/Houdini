"""
Test suite for the Execution Confidence Model.

Tests:
1. Basic confidence rating
2. Calibration system
3. Thompson Sampling
4. Decision making at different confidence levels
5. Retry strategies
"""

import sys
import tempfile
from pathlib import Path
import numpy as np

# Add src to path and mock the logging module
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Create a mock logger before importing the module
class MockLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

# Mock the logging import
import types
mock_utils = types.ModuleType('src.utils.logging')
mock_utils.logger = MockLogger()
sys.modules['src.utils.logging'] = mock_utils

# Now we can import directly
sys.path.insert(0, str(Path(__file__).parent / "src" / "utils"))

# Import the module components directly to avoid other dependencies
exec(open(str(Path(__file__).parent / "src" / "utils" / "execution_confidence.py")).read().replace(
    "from .logging import logger",
    "logger = MockLogger()"
))


def test_basic_rating():
    """Test basic action rating."""
    print("\n=== Test: Basic Rating ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        model = ExecutionConfidenceModel(Path(tmpdir))
        
        # Test simple click action
        rating = model.rate_action(
            action_type="click",
            action_params={"target": "Submit button"},
            context={"current_app": "Safari", "screen_active": True},
            element_info={"found": True, "confidence": 0.8, "num_matches": 1},
        )
        
        print(f"Action: click 'Submit button'")
        print(f"Score: {rating.score:.1f}/10")
        print(f"Level: {rating.level.value}")
        print(f"Decision: {rating.decision.value}")
        print(f"Reasoning: {rating.reasoning}")
        print(f"Component scores:")
        print(f"  - Historical: {rating.historical_confidence:.2f}")
        print(f"  - Context fit: {rating.context_fit:.2f}")
        print(f"  - Complexity: {rating.action_complexity:.2f}")
        print(f"  - Element certainty: {rating.element_certainty:.2f}")
        
        assert 0 <= rating.score <= 10, "Score should be 0-10"
        assert isinstance(rating.level, ConfidenceLevel)
        assert isinstance(rating.decision, ActionDecision)
        
        print("✓ Basic rating test passed")


def test_confidence_levels():
    """Test that different scenarios produce different confidence levels."""
    print("\n=== Test: Confidence Levels ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        model = ExecutionConfidenceModel(Path(tmpdir))
        
        # High confidence scenario
        high_rating = model.rate_action(
            action_type="click",
            action_params={"target": "OK"},
            context={"current_app": "Safari", "screen_active": True},
            element_info={"found": True, "confidence": 0.95, "num_matches": 1, "type": "button"},
        )
        print(f"High confidence scenario: {high_rating.score:.1f} ({high_rating.level.value})")
        
        # Low confidence scenario - element not found
        low_rating = model.rate_action(
            action_type="click",
            action_params={"target": "Some obscure element"},
            context={"current_app": "Unknown", "screen_active": False, "has_dialog": True},
            element_info={"found": False, "confidence": 0.2, "num_matches": 5},
        )
        print(f"Low confidence scenario: {low_rating.score:.1f} ({low_rating.level.value})")
        
        # Complex action scenario
        complex_rating = model.rate_action(
            action_type="code",
            action_params={"code": "some_complex_script()"},
            context=None,
            element_info=None,
        )
        print(f"Complex action scenario: {complex_rating.score:.1f} ({complex_rating.level.value})")
        
        # Verify high confidence > low confidence
        assert high_rating.score > low_rating.score, "High confidence should score higher"
        
        print("✓ Confidence levels test passed")


def test_calibrator():
    """Test the confidence calibrator."""
    print("\n=== Test: Calibrator ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        calibrator = ConfidenceCalibrator(Path(tmpdir) / "calib.json")
        
        # Test with no data - should return regularized score
        raw_score = 0.8
        calibrated, adjustment = calibrator.calibrate(raw_score)
        print(f"No data calibration: {raw_score:.2f} → {calibrated:.2f} (adj: {adjustment:+.3f})")
        
        # Add some calibration data
        import numpy as np
        np.random.seed(42)
        
        # Simulate overconfident model (predicts high but fails often)
        for _ in range(50):
            pred = np.random.uniform(0.6, 0.9)
            # Actual success rate is lower
            success = np.random.random() < (pred * 0.7)
            calibrator.record_outcome(pred, success)
        
        # Now calibrate should adjust down
        calibrated_after, adjustment_after = calibrator.calibrate(0.8)
        print(f"After learning: 0.80 → {calibrated_after:.2f} (adj: {adjustment_after:+.3f})")
        
        stats = calibrator.get_calibration_stats()
        print(f"Calibration ECE: {stats.get('ece', 'N/A'):.3f}")
        
        print("✓ Calibrator test passed")


def test_thompson_sampling():
    """Test Thompson Sampling for action selection."""
    print("\n=== Test: Thompson Sampling ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        ts = ThompsonSamplingSelector(Path(tmpdir) / "ts.json")
        
        # Simulate some outcomes
        # "click" succeeds 80% of the time
        for _ in range(20):
            ts.record_outcome("click", np.random.random() < 0.8)
        
        # "type" succeeds 60% of the time
        for _ in range(20):
            ts.record_outcome("type", np.random.random() < 0.6)
        
        # "code" succeeds 40% of the time
        for _ in range(20):
            ts.record_outcome("code", np.random.random() < 0.4)
        
        # Expected confidence should reflect success rates
        click_conf = ts.get_expected_confidence("click")
        type_conf = ts.get_expected_confidence("type")
        code_conf = ts.get_expected_confidence("code")
        
        print(f"Click expected confidence: {click_conf:.2f}")
        print(f"Type expected confidence: {type_conf:.2f}")
        print(f"Code expected confidence: {code_conf:.2f}")
        
        assert click_conf > type_conf > code_conf, "Confidence should match success rates"
        
        # Test action selection
        actions = ["click", "type", "code"]
        selections = {"click": 0, "type": 0, "code": 0}
        
        for _ in range(100):
            best, score = ts.select_best_action(actions, use_thompson=True)
            selections[best] += 1
        
        print(f"Selection distribution (100 samples): {selections}")
        
        # Click should be selected most often (but not always due to exploration)
        assert selections["click"] > selections["code"], "Click should be selected more often"
        
        print("✓ Thompson Sampling test passed")


def test_decision_strategies():
    """Test decision making at different confidence levels."""
    print("\n=== Test: Decision Strategies ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        model = ExecutionConfidenceModel(Path(tmpdir))
        
        scenarios = [
            {
                "name": "High confidence click",
                "action_type": "click",
                "params": {"target": "OK"},
                "context": {"current_app": "Safari", "screen_active": True},
                "element": {"found": True, "confidence": 0.95, "num_matches": 1},
            },
            {
                "name": "Moderate confidence type",
                "action_type": "type",
                "params": {"text": "Hello world", "field": "Search"},
                "context": {"current_app": "Chrome"},
                "element": {"found": True, "confidence": 0.6, "num_matches": 2},
            },
            {
                "name": "Low confidence action",
                "action_type": "drag",
                "params": {"from": "icon", "to": "folder"},
                "context": {"screen_active": False},
                "element": {"found": False, "confidence": 0.2},
            },
        ]
        
        for scenario in scenarios:
            rating = model.rate_action(
                scenario["action_type"],
                scenario["params"],
                scenario.get("context"),
                scenario.get("element"),
            )
            
            print(f"\n{scenario['name']}:")
            print(f"  Score: {rating.score:.1f}/10 ({rating.level.value})")
            print(f"  Decision: {rating.decision.value}")
            
            if rating.retry_strategy:
                print(f"  Retry strategy: {rating.retry_strategy}")
            if rating.alternative_actions:
                print(f"  Alternatives: {rating.alternative_actions}")
            
            # Test retry strategy
            retry = model.get_retry_strategy(rating, attempt=0)
            print(f"  Should retry: {retry['should_retry']}, strategy: {retry['strategy']}")
        
        print("\n✓ Decision strategies test passed")


def test_outcome_recording():
    """Test recording outcomes and learning."""
    print("\n=== Test: Outcome Recording ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        model = ExecutionConfidenceModel(Path(tmpdir))
        
        # Simulate some action executions
        for i in range(30):
            rating = model.rate_action(
                action_type="click",
                action_params={"target": f"button_{i}"},
                context={"current_app": "Safari"},
                element_info={"found": True, "confidence": 0.7},
            )
            
            # Record outcome (80% success rate)
            success = np.random.random() < 0.8
            model.record_outcome(
                action_type="click",
                action_params={"target": f"button_{i}"},
                predicted_rating=rating,
                success=success,
                execution_time=0.1,
                context={"current_app": "Safari"},
            )
        
        # Check stats
        stats = model.get_stats()
        print(f"Total actions: {stats['total_actions']}")
        print(f"Recent success rate: {stats['recent_success_rate']:.2f}")
        print(f"Avg confidence: {stats['recent_avg_confidence']:.2f}")
        
        if "by_action_type" in stats:
            print(f"By type: {stats['by_action_type']}")
        
        print("✓ Outcome recording test passed")


def test_full_workflow():
    """Test the complete workflow of rating → execute → record."""
    print("\n=== Test: Full Workflow ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        model = ExecutionConfidenceModel(Path(tmpdir))
        
        # Simulate executing an action
        action_type = "click"
        action_params = {"target": "Login button"}
        context = {"current_app": "Safari", "screen_active": True}
        element_info = {"found": True, "confidence": 0.85, "num_matches": 1}
        
        # Step 1: Rate the action
        print("Step 1: Rating action...")
        rating = model.rate_action(action_type, action_params, context, element_info)
        print(f"  Score: {rating.score:.1f}/10")
        print(f"  Decision: {rating.decision.value}")
        
        # Step 2: Check if we should execute
        should_exec = model.should_execute(rating)
        print(f"\nStep 2: Should execute? {should_exec}")
        
        if should_exec:
            # Step 3: Execute (simulated)
            print("\nStep 3: Executing action...")
            import time
            start = time.time()
            success = True  # Simulated success
            exec_time = time.time() - start
            
            # Step 4: Record outcome
            print(f"\nStep 4: Recording outcome (success={success})...")
            model.record_outcome(
                action_type, action_params, rating, success, exec_time, context
            )
            
            # Step 5: Check updated model
            print("\nStep 5: Model stats after recording:")
            stats = model.get_stats()
            print(f"  Total actions: {stats['total_actions']}")
        else:
            # Handle low confidence
            print("\nConfidence too low, checking alternatives...")
            if rating.alternative_actions:
                print(f"  Alternatives: {rating.alternative_actions}")
            
            retry = model.get_retry_strategy(rating, attempt=0)
            print(f"  Retry strategy: {retry['strategy']}")
        
        print("\n✓ Full workflow test passed")


def run_all_tests():
    """Run all tests."""
    import numpy as np
    
    print("=" * 60)
    print("Execution Confidence Model - Test Suite")
    print("=" * 60)
    
    try:
        test_basic_rating()
        test_confidence_levels()
        test_calibrator()
        test_thompson_sampling()
        test_decision_strategies()
        test_outcome_recording()
        test_full_workflow()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise


if __name__ == "__main__":
    import numpy as np
    run_all_tests()
