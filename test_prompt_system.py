#!/usr/bin/env python3
"""
Test script to verify the prompt evolution system is working correctly.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from src.utils.prompt_loader import prompt_loader, get_planner_prompt
        from src.utils.prompt_evolution import prompt_evolution
        from src.utils.prompt_config import get_config
        print("  ✅ All modules imported successfully")
        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_prompt_files():
    """Test that prompt files exist and can be loaded."""
    print("\nTesting prompt files...")
    from src.utils.prompt_loader import prompt_loader
    
    all_good = True
    for component in ["planner", "executor", "supervisor"]:
        try:
            prompt = prompt_loader.load_prompt(component)
            if len(prompt) > 100:
                print(f"  ✅ {component}_prompt.md loaded ({len(prompt)} chars)")
            else:
                print(f"  ⚠️ {component}_prompt.md seems too short")
                all_good = False
        except Exception as e:
            print(f"  ❌ {component}_prompt.md failed: {e}")
            all_good = False
    
    return all_good


def test_feedback_system():
    """Test that feedback can be recorded."""
    print("\nTesting feedback system...")
    from src.utils.prompt_evolution import prompt_evolution
    
    try:
        # Record test feedback
        prompt_evolution.record_feedback(
            component="planner",
            task="Test task",
            success=True,
            execution_time=1.0
        )
        print("  ✅ Feedback recorded successfully")
        return True
    except Exception as e:
        print(f"  ❌ Feedback recording failed: {e}")
        return False


def test_statistics():
    """Test that statistics can be retrieved."""
    print("\nTesting statistics...")
    from src.utils.prompt_evolution import prompt_evolution
    
    try:
        stats = prompt_evolution.get_statistics()
        print(f"  ✅ Statistics retrieved")
        print(f"     Total executions: {stats['total_executions']}")
        print(f"     Total evolutions: {stats['total_evolutions']}")
        return True
    except Exception as e:
        print(f"  ❌ Statistics failed: {e}")
        return False


def test_prompt_info():
    """Test that prompt info can be retrieved."""
    print("\nTesting prompt info...")
    from src.utils.prompt_loader import prompt_loader
    
    try:
        info = prompt_loader.get_all_prompts_info()
        all_exist = all(i['exists'] for i in info.values())
        
        if all_exist:
            print("  ✅ All prompt files exist")
            for component, data in info.items():
                print(f"     {component}: {data['size_kb']} KB")
        else:
            print("  ⚠️ Some prompt files missing")
            for component, data in info.items():
                if not data['exists']:
                    print(f"     ❌ {component} not found")
        
        return all_exist
    except Exception as e:
        print(f"  ❌ Prompt info failed: {e}")
        return False


def test_config():
    """Test that configuration can be accessed."""
    print("\nTesting configuration...")
    from src.utils.prompt_config import get_config, is_evolution_enabled
    
    try:
        config = get_config("evolution")
        enabled = is_evolution_enabled()
        
        print(f"  ✅ Configuration loaded")
        print(f"     Evolution enabled: {enabled}")
        print(f"     Failure threshold: {config['failure_rate_threshold']}")
        return True
    except Exception as e:
        print(f"  ❌ Configuration failed: {e}")
        return False


def test_evolution_trigger():
    """Test evolution trigger logic (without actually evolving)."""
    print("\nTesting evolution trigger logic...")
    from src.utils.prompt_evolution import prompt_evolution
    
    try:
        # Check if evolution would trigger
        success_rate = prompt_evolution.get_success_rate("planner")
        print(f"  ✅ Evolution trigger logic working")
        print(f"     Planner success rate: {success_rate:.1%}")
        
        if success_rate < 0.8:
            print(f"     ⚠️ Success rate below 80%, evolution may trigger soon")
        
        return True
    except Exception as e:
        print(f"  ❌ Evolution trigger test failed: {e}")
        return False


def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("  Houdini Agent - Prompt System Tests")
    print("="*60)
    
    tests = [
        test_imports,
        test_prompt_files,
        test_feedback_system,
        test_statistics,
        test_prompt_info,
        test_config,
        test_evolution_trigger,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "="*60)
    print("  Test Summary")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed! System is ready to use.")
        print("\nNext steps:")
        print("  1. Run a task: python -m src.main --task 'open safari'")
        print("  2. View stats: python -m src.utils.prompt_stats")
        print("  3. Check docs: PROMPT_SYSTEM.md")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check errors above.")
        print("\nTroubleshooting:")
        print("  1. Ensure all dependencies installed: pip install -r requirements.txt")
        print("  2. Check that prompt files exist in prompts/")
        print("  3. Review error messages above")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
