#!/usr/bin/env python3
"""
Quick test to verify Ollama integration is working.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.ollama_client import OllamaClient
from src.planner.ollama_planner import OllamaPlanner
from src.supervisor.ollama_supervisor import OllamaSupervisor

def test_ollama_client():
    """Test basic Ollama client functionality."""
    print("🧪 Testing Ollama Client...")
    
    try:
        client = OllamaClient(model_name="qwen2.5-coder:32b")
        print("  ✅ Client initialized")
        
        response = client.generate(
            "Say 'Hello' in one word only.",
            temperature=0.1
        )
        print(f"  ✅ Generate test: {response[:50]}")
        
        return True
    except Exception as e:
        print(f"  ❌ Client test failed: {e}")
        return False

def test_planner():
    """Test Ollama planner."""
    print("\n🧪 Testing Ollama Planner...")
    
    try:
        client = OllamaClient(model_name="qwen2.5-coder:32b")
        planner = OllamaPlanner(client)
        print("  ✅ Planner initialized")
        
        # Test with executor history
        history = [
            {"task": "test task 1", "success": True, "duration": 2.5},
            {"task": "test task 2", "success": True, "duration": 3.1}
        ]
        
        batches = planner.plan("search for cats", executor_history=history)
        print(f"  ✅ Planning test: Generated {len(batches)} batches")
        
        return True
    except Exception as e:
        print(f"  ❌ Planner test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_supervisor():
    """Test Ollama supervisor."""
    print("\n🧪 Testing Ollama Supervisor...")
    
    try:
        client = OllamaClient(model_name="qwen2.5-coder:32b")
        supervisor = OllamaSupervisor(client)
        print("  ✅ Supervisor initialized")
        
        # Test history tracking
        supervisor.executor_history.add_execution(
            task="test task",
            batches=[],
            success=True,
            duration=2.5
        )
        
        history = supervisor.get_executor_history()
        print(f"  ✅ History test: {len(history)} entries")
        
        stats = supervisor.get_statistics()
        print(f"  ✅ Statistics test: {stats['total']} total executions")
        
        return True
    except Exception as e:
        print(f"  ❌ Supervisor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Ollama Integration Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test client
    results.append(("Client", test_ollama_client()))
    
    # Test planner
    results.append(("Planner", test_planner()))
    
    # Test supervisor
    results.append(("Supervisor", test_supervisor()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
        print("\n📝 Next steps:")
        print("  1. Run setup: ./setup_ollama.sh")
        print("  2. Try a task: python -m src.main --task 'search for AI' --loop")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")
        print("\n💡 Troubleshooting:")
        print("  1. Make sure Ollama is installed: brew install ollama")
        print("  2. Pull the model: ollama pull qwen2.5-coder:32b")
        print("  3. Start Ollama: ollama serve")
        return 1

if __name__ == "__main__":
    sys.exit(main())
