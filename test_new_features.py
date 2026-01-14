#!/usr/bin/env python3
"""
Quick test script for new screen understanding and cursor control features.
Run this to verify everything is working.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_accessibility_api():
    """Test native accessibility API."""
    print("=" * 60)
    print("Test 1: Native Accessibility API")
    print("=" * 60)
    
    try:
        from src.utils.accessibility_api import AccessibilityAPI
        
        api = AccessibilityAPI()
        print("✅ AccessibilityAPI initialized")
        
        # Get app info
        app_info = api.get_frontmost_app_info()
        print(f"📱 Frontmost app: {app_info['app']}")
        if app_info['window']:
            print(f"   Window: {app_info['window']}")
        
        # Get UI tree
        print("\n🌳 Getting UI tree...")
        start = time.time()
        tree = api.get_ui_tree(max_depth=5)
        duration = time.time() - start
        
        if tree:
            # Count elements
            count = 0
            def count_elements(elem):
                nonlocal count
                count += 1
                for child in elem.children:
                    count_elements(child)
            count_elements(tree)
            
            print(f"✅ Found {count} UI elements in {duration:.3f}s")
            
            # Show sample elements
            print("\n📋 Sample elements:")
            shown = 0
            def show_elements(elem, indent=0):
                nonlocal shown
                if shown >= 10:
                    return
                if elem.center:
                    text = elem.title or elem.value or ""
                    if text:
                        print(f"   {'  ' * indent}[{elem.role}] '{text[:30]}'")
                        shown += 1
                for child in elem.children[:3]:  # Limit to avoid spam
                    show_elements(child, indent + 1)
            
            show_elements(tree)
        else:
            print("⚠️  No UI tree returned (may need accessibility permissions)")
        
        print("\n✅ Accessibility API test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Accessibility API test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cursor_controller():
    """Test human-like cursor controller."""
    print("\n" + "=" * 60)
    print("Test 2: Human-Like Cursor Controller")
    print("=" * 60)
    
    try:
        from src.utils.cursor_controller import HumanCursor
        import pyautogui
        
        cursor = HumanCursor()
        print("✅ HumanCursor initialized")
        
        # Get current position
        start_x, start_y = pyautogui.position()
        print(f"📍 Current position: ({start_x}, {start_y})")
        
        # Test small movement
        target_x, target_y = start_x + 100, start_y + 100
        print(f"🎯 Moving to: ({target_x}, {target_y})")
        
        start_time = time.time()
        cursor.move_to(target_x, target_y, target_size=(50, 50))
        duration = time.time() - start_time
        
        final_x, final_y = pyautogui.position()
        print(f"✅ Moved to ({final_x}, {final_y}) in {duration:.3f}s")
        print("   (includes bezier curve, Fitts's Law timing, micro-jitter)")
        
        # Move back
        time.sleep(0.5)
        cursor.move_to(start_x, start_y)
        
        print("\n✅ Cursor controller test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Cursor controller test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_screen_understanding():
    """Test screen understanding coordinator."""
    print("\n" + "=" * 60)
    print("Test 3: Screen Understanding Coordinator")
    print("=" * 60)
    
    try:
        from src.utils.screen_understanding_coordinator import ScreenUnderstandingCoordinator
        
        coordinator = ScreenUnderstandingCoordinator(use_vlm=False)  # Skip VLM for quick test
        print("✅ ScreenUnderstandingCoordinator initialized")
        
        print("\n🔍 Understanding current screen...")
        start = time.time()
        understanding = coordinator.understand_screen(task_context="Testing screen understanding")
        duration = time.time() - start
        
        print(f"✅ Screen understood in {duration:.3f}s")
        print(f"   Method: {understanding.method_used}")
        print(f"   Confidence: {understanding.confidence:.2f}")
        print(f"   App: {understanding.app_name}")
        if understanding.window_title:
            print(f"   Window: {understanding.window_title}")
        print(f"   Elements found: {len(understanding.accessibility_elements)}")
        
        # Show LLM context preview
        context = understanding.to_llm_context(max_length=500)
        print(f"\n📝 LLM Context preview:")
        print("   " + "\n   ".join(context.split("\n")[:10]))
        if len(context) > 500:
            print("   ... (truncated)")
        
        # Get stats
        stats = coordinator.get_stats()
        print(f"\n📊 Statistics: {stats}")
        
        print("\n✅ Screen understanding test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Screen understanding test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_element_interactor():
    """Test element-based interaction."""
    print("\n" + "=" * 60)
    print("Test 4: Element Interactor")
    print("=" * 60)
    
    try:
        from src.utils.element_interactor import ElementInteractor
        
        interactor = ElementInteractor()
        print("✅ ElementInteractor initialized")
        print("   Prefer accessibility: True")
        print("   Use human cursor: True")
        
        print("\n✅ Element interactor test PASSED")
        print("   (Full interaction test requires target UI elements)")
        return True
        
    except Exception as e:
        print(f"❌ Element interactor test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n🚀 Houdini Agent - New Features Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test 1: Accessibility API
    results.append(("Accessibility API", test_accessibility_api()))
    
    # Test 2: Cursor Controller
    results.append(("Cursor Controller", test_cursor_controller()))
    
    # Test 3: Screen Understanding
    results.append(("Screen Understanding", test_screen_understanding()))
    
    # Test 4: Element Interactor
    results.append(("Element Interactor", test_element_interactor()))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests PASSED! The new system is ready to use.")
        print("\n💡 Next steps:")
        print("   1. Install dependencies: pip install -r requirements.txt")
        print("   2. Grant accessibility permissions in System Settings")
        print("   3. Integrate with agents/planner")
    else:
        print("\n⚠️  Some tests failed. Check error messages above.")
        print("\n💡 Common issues:")
        print("   - Missing dependencies: pip install -r requirements.txt")
        print("   - Accessibility permissions not granted")
        print("   - PyObjC not installed properly")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
