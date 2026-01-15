#!/usr/bin/env python3
"""
Test script for the Probability Model.

Tests:
1. Task completeness analysis
2. Macro-micro spectrum positioning
3. Intent prediction
4. Flexible execution parameters
"""

import sys
sys.path.insert(0, 'src')

from src.utils.probability_model import (
    TaskProbabilityModel,
    analyze_task_flexibility,
    get_flexible_execution_params,
    FuzzyMacroMicroAnalyzer,
    BayesianTaskAnalyzer,
    IntentPredictor
)


def test_task_completeness():
    """Test task completeness analysis."""
    print("\n" + "="*60)
    print("TASK COMPLETENESS ANALYSIS")
    print("="*60)
    
    analyzer = BayesianTaskAnalyzer()
    
    test_cases = [
        # (task, expected_score_range)
        ("open the latest mrbeast video on youtube", (0.7, 1.0)),  # Good spec
        ("click the button", (0.3, 0.6)),  # Vague - missing location, target
        ("send message saying hi to kushal on whatsapp", (0.8, 1.0)),  # Complete
        ("search for something", (0.2, 0.5)),  # Very vague
        ("press cmd+space, type Safari, press enter", (0.7, 1.0)),  # Micro-level, complete
        ("do the thing", (0.0, 0.3)),  # Extremely vague
    ]
    
    for task, (min_score, max_score) in test_cases:
        result = analyzer.analyze_completeness(task)
        status = "✅" if min_score <= result.overall_score <= max_score else "❌"
        print(f"\n{status} Task: '{task}'")
        print(f"   Score: {result.overall_score:.0%}")
        print(f"   Has: target={result.has_target}, action={result.has_action}, location={result.has_location}")
        print(f"   Missing: {result.missing_info}")
        if result.predicted_info:
            print(f"   Predicted: {result.predicted_info}")


def test_macro_micro_spectrum():
    """Test macro-micro spectrum positioning."""
    print("\n" + "="*60)
    print("MACRO-MICRO SPECTRUM ANALYSIS")
    print("="*60)
    
    analyzer = FuzzyMacroMicroAnalyzer()
    
    test_cases = [
        # (task, expected_strategy)
        ("search for AI news", "macro_plan"),  # High-level goal
        ("open YouTube and watch latest video", "macro_plan"),  # High-level goal
        ("press command+space", "micro_direct"),  # Direct micro action
        ("type 'hello world' in the text field", "micro_direct"),  # Direct micro action
        ("send a message to kushal", "hybrid"),  # Mix of both
        ("click the first search result", "hybrid"),  # Depends on context
        ("hotkey:cmd+l, type:google.com, key:return", "micro_direct"),  # Pure micro
    ]
    
    for task, expected_strategy in test_cases:
        result = analyzer.analyze(task)
        status = "✅" if result.execution_strategy == expected_strategy else "⚠️"
        print(f"\n{status} Task: '{task}'")
        print(f"   Position: {result.position:.2f} (0=macro, 1=micro)")
        print(f"   Strategy: {result.execution_strategy} (expected: {expected_strategy})")
        print(f"   Decomposition needed: {result.decomposition_needed}")


def test_intent_prediction():
    """Test intent prediction."""
    print("\n" + "="*60)
    print("INTENT PREDICTION")
    print("="*60)
    
    predictor = IntentPredictor()
    
    test_cases = [
        ("open safari and go to google.com", "navigation"),
        ("click the submit button", "interaction"),
        ("send a message to john on whatsapp", "communication"),
        ("play the latest mrbeast video", "media"),
        ("create a new folder called projects", "file_management"),
        ("download the pdf", "media"),  # Could also be file_management
    ]
    
    for task, expected_intent in test_cases:
        result = predictor.predict(task)
        status = "✅" if result.primary_intent == expected_intent else "⚠️"
        print(f"\n{status} Task: '{task}'")
        print(f"   Primary: {result.primary_intent} (expected: {expected_intent})")
        print(f"   Confidence: {result.confidence:.0%}")
        print(f"   Ambiguity: {result.ambiguity_score:.0%}")
        if result.alternative_intents:
            alts = ", ".join(f"{i}:{p:.0%}" for i, p in result.alternative_intents)
            print(f"   Alternatives: {alts}")


def test_unified_model():
    """Test the unified probability model."""
    print("\n" + "="*60)
    print("UNIFIED PROBABILITY MODEL")
    print("="*60)
    
    model = TaskProbabilityModel()
    
    test_tasks = [
        "open the latest mrbeast video on youtube",
        "click something",
        "send hi to kushal on whatsapp",
        "type hello",
        "do that thing we discussed",
        "search for quantum physics news and open the first result from arxiv",
    ]
    
    for task in test_tasks:
        flexibility = model.analyze(task)
        params = model.get_execution_params(task)
        
        print(f"\n📊 Task: '{task}'")
        print(f"   Completeness: {flexibility.task_completeness.overall_score:.0%}")
        print(f"   Intent: {flexibility.intent.primary_intent} ({flexibility.intent.confidence:.0%})")
        print(f"   Macro-Micro: {flexibility.macro_micro.position:.2f} → {flexibility.macro_micro.execution_strategy}")
        print(f"   Uncertainty: {flexibility.overall_uncertainty:.0%}")
        print(f"   Recommended: {flexibility.recommended_approach}")
        print(f"   Execution params:")
        print(f"      Min match probability: {params['min_match_probability']:.0%}")
        print(f"      Verification: {params['verification_strictness']}")
        print(f"      Exploration: {params['exploration_enabled']}")


def test_edge_cases():
    """Test edge cases and unusual inputs."""
    print("\n" + "="*60)
    print("EDGE CASES")
    print("="*60)
    
    model = TaskProbabilityModel()
    
    edge_cases = [
        "",  # Empty
        "   ",  # Whitespace
        "x",  # Single character
        "a" * 1000,  # Very long
        "🎯 click 📱 button",  # Emojis
        "SEARCH FOR NEWS!!!",  # All caps with punctuation
        "click button1 then button2 then button3",  # Multiple targets
    ]
    
    for task in edge_cases:
        try:
            flexibility = model.analyze(task)
            print(f"\n✅ Task: '{task[:50]}...' → uncertainty: {flexibility.overall_uncertainty:.0%}")
        except Exception as e:
            print(f"\n❌ Task: '{task[:50]}...' → ERROR: {e}")


def main():
    """Run all tests."""
    print("="*60)
    print("PROBABILITY MODEL TEST SUITE")
    print("="*60)
    
    test_task_completeness()
    test_macro_micro_spectrum()
    test_intent_prediction()
    test_unified_model()
    test_edge_cases()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main()
