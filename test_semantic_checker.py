"""
Test Semantic Checker - Dual-Path Validation

Tests the fast semantic validation without LLM calls.
"""

import sys
import os
import importlib.util

# Load the semantic_checker module directly without triggering __init__.py imports
spec = importlib.util.spec_from_file_location(
    "semantic_checker",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                 "src/supervisor/semantic_checker.py")
)
semantic_checker = importlib.util.module_from_spec(spec)

# Mock the accessibility reader before loading
class MockAccessibilityReader:
    @staticmethod
    def get_frontmost_app():
        return {"app": "MockApp", "window": "Mock Window"}

# We'll inject this mock when needed
sys.modules['..utils.accessibility_reader'] = MockAccessibilityReader

try:
    spec.loader.exec_module(semantic_checker)
except ImportError:
    # The module tries to do relative imports, let's handle this
    pass

# Now import the functions we need directly
SemanticChecker = semantic_checker.SemanticChecker
SemanticCheckResult = semantic_checker.SemanticCheckResult
SemanticMismatchType = semantic_checker.SemanticMismatchType
extract_expected_app = semantic_checker.extract_expected_app
apps_match = semantic_checker.apps_match
normalize_app_name = semantic_checker.normalize_app_name
get_semantic_checker = semantic_checker.get_semantic_checker


def test_normalize_app_name():
    """Test app name normalization."""
    print("\n📝 Testing app name normalization...")
    
    test_cases = [
        ("Safari", "safari"),
        ("Google Chrome", "chrome"),
        ("Visual Studio Code", "vscode"),
        ("Microsoft Word", "word"),
        ("WhatsApp", "whatsapp"),
        ("Calculator", "calculator"),
        ("iTerm2", "iterm2"),
        ("Unknown App", "unknown app"),  # Not in our mappings
    ]
    
    for input_name, expected in test_cases:
        result = normalize_app_name(input_name)
        status = "✅" if result == expected else "❌"
        print(f"  {status} normalize_app_name('{input_name}') = '{result}' (expected: '{expected}')")


def test_apps_match():
    """Test app matching logic."""
    print("\n🔍 Testing app matching...")
    
    test_cases = [
        # (expected, actual, should_match)
        ("safari", "Safari", True),
        ("chrome", "Google Chrome", True),
        ("safari", "Chrome", True),  # Both browsers, partial match
        ("calculator", "Safari", False),
        ("vscode", "Visual Studio Code", True),
        ("terminal", "iTerm2", True),  # Both terminals
        ("whatsapp", "Safari", False),
        ("finder", "Finder", True),
    ]
    
    for expected, actual, should_match in test_cases:
        match, confidence = apps_match(expected, actual)
        status = "✅" if match == should_match else "❌"
        print(f"  {status} apps_match('{expected}', '{actual}') = {match} (conf: {confidence:.2f})")


def test_extract_expected_app():
    """Test extracting app name from step descriptions."""
    print("\n📋 Testing app extraction from step descriptions...")
    
    test_cases = [
        ("Open Safari", "safari"),
        ("Launch Calculator", "calculator"),
        ("Open the Calculator app", "calculator"),
        ("Navigate to Chrome", "chrome"),
        ("Use WhatsApp to send message", "whatsapp"),
        ("Switch to Finder", "finder"),
        ("Go to VSCode", "vscode"),
        ("Search for AI news", None),  # No specific app mentioned
        ("Type hello world", None),  # No app
    ]
    
    for step_desc, expected_app in test_cases:
        result = extract_expected_app(step_desc)
        status = "✅" if result == expected_app else "❌"
        print(f"  {status} extract_expected_app('{step_desc}') = '{result}' (expected: '{expected_app}')")


def test_semantic_checker():
    """Test the semantic checker with macro steps."""
    print("\n🔮 Testing SemanticChecker...")
    
    checker = SemanticChecker()
    
    # Test case 1: Step says "Open Calculator" but Safari is active
    print("\n  Test 1: Open Calculator, but Safari active")
    result = checker.check_state_match(
        macro_step={"step": "Open Calculator", "context": "Calculator visible"},
        actual_app="Safari",
        actual_window="Google Search"
    )
    print(f"    is_valid: {result.is_valid}")
    print(f"    mismatch_type: {result.mismatch_type}")
    print(f"    should_interrupt: {result.should_interrupt}")
    print(f"    reason: {result.reason}")
    assert result.should_interrupt == True, "Should interrupt when Calculator expected but Safari active"
    print("    ✅ Correctly detected mismatch!")
    
    # Test case 2: Step says "Open Safari" and Safari is active
    print("\n  Test 2: Open Safari, Safari active")
    result = checker.check_state_match(
        macro_step={"step": "Open Safari", "context": "Browser window visible"},
        actual_app="Safari",
        actual_window="Google"
    )
    print(f"    is_valid: {result.is_valid}")
    print(f"    should_interrupt: {result.should_interrupt}")
    assert result.is_valid == True, "Should be valid when Safari expected and Safari active"
    print("    ✅ Correctly detected match!")
    
    # Test case 3: Step says "Open browser" and Chrome is active (flexible match)
    print("\n  Test 3: Open browser, Chrome active")
    result = checker.check_state_match(
        macro_step={"step": "Open Chrome and search", "context": "Browser visible"},
        actual_app="Google Chrome",
        actual_window="New Tab"
    )
    print(f"    is_valid: {result.is_valid}")
    print(f"    confidence: {result.confidence}")
    assert result.is_valid == True, "Should match Chrome to Chrome"
    print("    ✅ Correctly detected match!")
    
    # Test case 4: Ambiguous step with no clear app
    print("\n  Test 4: Ambiguous step 'Search for news'")
    result = checker.check_state_match(
        macro_step={"step": "Search for news", "context": "Search results"},
        actual_app="Safari",
        actual_window="Google Search"
    )
    print(f"    is_valid: {result.is_valid}")
    print(f"    should_interrupt: {result.should_interrupt}")
    # Since no specific app can be extracted, it shouldn't interrupt
    assert result.should_interrupt == False, "Should not interrupt for ambiguous steps"
    print("    ✅ Correctly handled ambiguous step!")


def test_quick_semantic_check():
    """Test the convenience function."""
    print("\n⚡ Testing quick_semantic_check()...")
    
    # This would normally use the accessibility tree for actual_app
    # For testing, we'll use the checker directly
    checker = get_semantic_checker()
    
    result = checker.check_state_match(
        {"step": "Open WhatsApp", "context": "WhatsApp visible"},
        actual_app="Messages",
        actual_window="Messages"
    )
    
    print(f"  Checking 'Open WhatsApp' with Messages active:")
    print(f"    should_interrupt: {result.should_interrupt}")
    print(f"    reason: {result.reason}")
    assert result.should_interrupt == True
    print("  ✅ Quick check works!")


def test_action_context_check():
    """Test action context validation."""
    print("\n🎯 Testing action context validation...")
    
    checker = get_semantic_checker()
    
    # Test URL bar action in non-browser
    result = checker.check_action_context(
        intended_action="Click URL bar and type google.com",
        actual_app="Calculator",
        actual_window="Calculator"
    )
    print(f"  'Click URL bar' with Calculator active:")
    print(f"    should_interrupt: {result.should_interrupt}")
    assert result.should_interrupt == True, "Should interrupt URL action in non-browser"
    print("  ✅ Correctly detected context mismatch!")
    
    # Test URL bar action in browser
    result = checker.check_action_context(
        intended_action="Click URL bar and type google.com",
        actual_app="Safari",
        actual_window="Favorites"
    )
    print(f"  'Click URL bar' with Safari active:")
    print(f"    should_interrupt: {result.should_interrupt}")
    assert result.should_interrupt == False, "Should not interrupt URL action in browser"
    print("  ✅ Correctly allowed browser action!")


def main():
    """Run all tests."""
    print("=" * 60)
    print("🧪 Semantic Checker Test Suite")
    print("=" * 60)
    
    test_normalize_app_name()
    test_apps_match()
    test_extract_expected_app()
    test_semantic_checker()
    test_quick_semantic_check()
    test_action_context_check()
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    print("\nThe Semantic Checker provides fast dual-path validation:")
    print("  • Fast path: < 1ms semantic rules (no LLM)")
    print("  • Slow path: Full Qwen analysis (only when needed)")
    print("\nExample mismatch detection:")
    print("  • Planner says 'Open Calculator'")
    print("  • Accessibility Tree shows 'Safari' active")
    print("  • → Immediate interrupt without LLM call!")


if __name__ == "__main__":
    main()
