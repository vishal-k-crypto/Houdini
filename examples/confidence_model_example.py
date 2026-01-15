"""
Example: Using the Execution Confidence Model with Agents

This example shows how to integrate the confidence model with the executor
to make smart decisions about when to execute, verify, or retry actions.
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.execution_confidence import (
    ExecutionConfidenceModel,
    ConfidenceLevel,
    ActionDecision,
    rate_action,
    should_execute_action,
    record_action_outcome,
)


def example_confidence_aware_executor():
    """
    Example of a confidence-aware action executor.
    
    The confidence model helps decide:
    1. Should we execute this action?
    2. What verification level do we need?
    3. What retry strategy should we use if it fails?
    """
    
    print("=" * 60)
    print("Confidence-Aware Action Execution Example")
    print("=" * 60)
    
    # Initialize model
    model = ExecutionConfidenceModel()
    
    # Example actions to evaluate
    actions = [
        {
            "type": "click",
            "params": {"target": "Submit button", "coordinates_only": False},
            "context": {"current_app": "Safari", "screen_active": True},
            "element": {"found": True, "confidence": 0.9, "num_matches": 1, "type": "button"},
        },
        {
            "type": "type",
            "params": {"text": "Hello World", "field": "Search box"},
            "context": {"current_app": "Chrome", "screen_active": True},
            "element": {"found": True, "confidence": 0.7, "num_matches": 2},
        },
        {
            "type": "hotkey",
            "params": {"keys": ["command", "shift", "s"]},
            "context": {"current_app": "Finder"},
            "element": None,
        },
        {
            "type": "click",
            "params": {"target": "Some random element"},
            "context": {"screen_active": False, "has_dialog": True},
            "element": {"found": False, "confidence": 0.2, "num_matches": 5},
        },
    ]
    
    for i, action in enumerate(actions, 1):
        print(f"\n{'='*50}")
        print(f"Action {i}: {action['type']} - {action['params']}")
        print(f"{'='*50}")
        
        # Step 1: Rate the action
        rating = model.rate_action(
            action["type"],
            action["params"],
            action.get("context"),
            action.get("element"),
        )
        
        print(f"\n📊 Confidence Rating:")
        print(f"   Score: {rating.score:.1f}/10")
        print(f"   Level: {rating.level.value.upper()}")
        print(f"   Calibrated: {rating.calibrated}")
        
        # Show component breakdown
        print(f"\n📈 Component Scores:")
        print(f"   Historical:  {'█' * int(rating.historical_confidence * 10):<10} {rating.historical_confidence:.0%}")
        print(f"   Context Fit: {'█' * int(rating.context_fit * 10):<10} {rating.context_fit:.0%}")
        print(f"   Simplicity:  {'█' * int(rating.action_complexity * 10):<10} {rating.action_complexity:.0%}")
        print(f"   Element:     {'█' * int(rating.element_certainty * 10):<10} {rating.element_certainty:.0%}")
        
        # Step 2: Make decision
        print(f"\n🎯 Decision: {rating.decision.value}")
        
        if rating.decision == ActionDecision.EXECUTE:
            print("   ✅ Execute immediately - high confidence!")
            
        elif rating.decision == ActionDecision.EXECUTE_VERIFY:
            print("   ✅ Execute with verification afterwards")
            
        elif rating.decision == ActionDecision.EXECUTE_CHECKPOINT:
            print("   ⚠️ Execute with checkpoint (can rollback)")
            if rating.alternative_actions:
                print(f"   📋 Fallback alternatives: {rating.alternative_actions}")
                
        elif rating.decision == ActionDecision.DEFER_CONFIRM:
            print("   ⏸️ Defer - needs confirmation before proceeding")
            print(f"   💡 Strategy: {rating.retry_strategy}")
            
        elif rating.decision == ActionDecision.RETRY_CONTEXT:
            print("   🔄 Gather more context before attempting")
            print(f"   💡 Strategy: {rating.retry_strategy}")
            
        elif rating.decision == ActionDecision.ALTERNATIVE:
            print("   🔀 Try alternative approach first")
            if rating.alternative_actions:
                print(f"   📋 Try: {rating.alternative_actions[0]}")
                
        elif rating.decision == ActionDecision.ABORT:
            print("   ❌ Abort - confidence too low, need human input")
        
        print(f"\n💭 Reasoning: {rating.reasoning}")


def example_retry_strategies():
    """
    Example showing different retry strategies based on confidence levels.
    """
    print("\n" + "=" * 60)
    print("Retry Strategies by Confidence Level")
    print("=" * 60)
    
    model = ExecutionConfidenceModel()
    
    # Simulate different confidence scenarios
    scenarios = [
        ("click", {"target": "OK"}, 0.95),  # High confidence
        ("type", {"text": "test"}, 0.65),   # Moderate confidence  
        ("drag", {"from": "A", "to": "B"}, 0.3),  # Low confidence
    ]
    
    for action_type, params, mock_confidence in scenarios:
        rating = model.rate_action(action_type, params, None, 
                                   {"found": True, "confidence": mock_confidence})
        
        print(f"\n📊 {action_type.upper()} (confidence ~{mock_confidence:.0%}):")
        print(f"   Actual score: {rating.score:.1f}/10 ({rating.level.value})")
        
        # Check retry strategy for different attempt numbers
        for attempt in range(4):
            retry = model.get_retry_strategy(rating, attempt)
            
            if retry["should_retry"]:
                print(f"   Attempt {attempt}: ✅ Retry with '{retry['strategy']}' "
                      f"(wait {retry['wait_time']:.1f}s)")
                if retry["modifications"]:
                    print(f"             Mods: {retry['modifications']}")
            else:
                print(f"   Attempt {attempt}: ❌ No retry - {retry['strategy']}")
                break


def example_learning_from_outcomes():
    """
    Example showing how the model learns from action outcomes.
    """
    print("\n" + "=" * 60)
    print("Learning from Outcomes")
    print("=" * 60)
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        model = ExecutionConfidenceModel(Path(tmpdir))
        
        # Initial confidence for 'click'
        initial_rating = model.rate_action("click", {"target": "test"}, None,
                                           {"found": True, "confidence": 0.7})
        print(f"\n📊 Initial click confidence: {initial_rating.score:.1f}/10")
        
        # Simulate many successful click actions
        print("\n⏳ Recording 50 successful clicks...")
        import numpy as np
        for _ in range(50):
            rating = model.rate_action("click", {"target": "test"}, None,
                                       {"found": True, "confidence": 0.7})
            model.record_outcome("click", {"target": "test"}, rating, 
                               success=True, execution_time=0.1)
        
        # Check updated confidence
        updated_rating = model.rate_action("click", {"target": "test"}, None,
                                           {"found": True, "confidence": 0.7})
        print(f"📊 After 50 successes: {updated_rating.score:.1f}/10")
        
        # Now simulate some failures
        print("\n⏳ Recording 20 failed type actions...")
        for _ in range(20):
            rating = model.rate_action("type", {"text": "test"}, None,
                                       {"found": True, "confidence": 0.7})
            model.record_outcome("type", {"text": "test"}, rating,
                               success=False, execution_time=0.5,
                               error_type="element_not_found")
        
        # Check type confidence (should be lower)
        type_rating = model.rate_action("type", {"text": "test"}, None,
                                        {"found": True, "confidence": 0.7})
        print(f"📊 Type after 20 failures: {type_rating.score:.1f}/10")
        
        # Show stats
        stats = model.get_stats()
        print(f"\n📈 Model Statistics:")
        print(f"   Total actions: {stats['total_actions']}")
        print(f"   Recent success rate: {stats['recent_success_rate']:.0%}")
        
        if "by_action_type" in stats:
            print(f"   By type:")
            for atype, data in stats["by_action_type"].items():
                print(f"     - {atype}: {data['success_rate']:.0%} "
                      f"({data['count']} samples)")


def example_quick_check():
    """
    Example of using the quick should_execute_action helper.
    """
    print("\n" + "=" * 60)
    print("Quick Execution Check")
    print("=" * 60)
    
    # Quick check with minimum confidence threshold
    should_exec, rating = should_execute_action(
        action_type="click",
        action_params={"target": "Login"},
        context={"current_app": "Safari"},
        element_info={"found": True, "confidence": 0.8},
        min_confidence=5.0,  # Require at least 5/10
    )
    
    print(f"\n{'✅' if should_exec else '❌'} Should execute: {should_exec}")
    print(f"   Score: {rating.score:.1f}/10")
    print(f"   Min required: 5.0/10")
    
    if not should_exec:
        print(f"   Reason: {rating.reasoning}")


if __name__ == "__main__":
    example_confidence_aware_executor()
    example_retry_strategies()
    example_learning_from_outcomes()
    example_quick_check()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)
