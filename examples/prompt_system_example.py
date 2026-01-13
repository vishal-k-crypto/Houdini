"""
Example: Using the Prompt Evolution System

This script demonstrates how the internal prompting system works
and how to interact with it programmatically.
"""

from src.utils.prompt_loader import prompt_loader, get_planner_prompt
from src.utils.prompt_evolution import prompt_evolution


def example_1_load_prompts():
    """Example 1: Loading prompts"""
    print("="*60)
    print("Example 1: Loading Prompts")
    print("="*60)
    
    # Load individual prompts
    planner_prompt = get_planner_prompt()
    print(f"\n✓ Loaded planner prompt ({len(planner_prompt)} chars)")
    
    # Get prompt metadata
    info = prompt_loader.get_prompt_info("executor")
    print(f"✓ Executor prompt: {info['size_kb']} KB")
    print(f"  Cached: {info['cached']}")
    print(f"  Path: {info['path']}")


def example_2_record_feedback():
    """Example 2: Recording execution feedback"""
    print("\n" + "="*60)
    print("Example 2: Recording Feedback")
    print("="*60)
    
    # Simulate successful execution
    prompt_evolution.record_feedback(
        component="planner",
        task="Open Safari and search for Python tutorials",
        success=True,
        execution_time=2.5,
        actions_taken=[
            "Open Safari",
            "Focus address bar",
            "Type search query",
            "Press enter"
        ]
    )
    print("\n✓ Recorded successful planning")
    
    # Simulate failed execution
    prompt_evolution.record_feedback(
        component="executor",
        task="Click the login button",
        success=False,
        error_type="element_not_found",
        error_details="Button with label 'login' not found in accessibility tree",
        actions_taken=["Read accessibility tree", "Search for button"]
    )
    print("✓ Recorded failed execution")


def example_3_view_statistics():
    """Example 3: Viewing system statistics"""
    print("\n" + "="*60)
    print("Example 3: System Statistics")
    print("="*60)
    
    stats = prompt_evolution.get_statistics()
    
    print(f"\n📊 Overall:")
    print(f"  Total Executions: {stats['total_executions']}")
    print(f"  Total Evolutions: {stats['total_evolutions']}")
    
    for component, data in stats['components'].items():
        print(f"\n🔧 {component.upper()}:")
        print(f"  Executions: {data['executions']}")
        print(f"  Success Rate: {data['success_rate']:.1%}")
        print(f"  Prompt Version: v{data['prompt_version']}")


def example_4_check_learnings():
    """Example 4: Checking recent learnings"""
    print("\n" + "="*60)
    print("Example 4: Recent Learnings")
    print("="*60)
    
    for component in ["planner", "executor", "supervisor"]:
        learnings = prompt_evolution.get_recent_learnings(component, count=2)
        
        if learnings:
            print(f"\n📝 {component.upper()}:")
            for learning in learnings:
                timestamp = learning.get('timestamp', 'unknown')
                failure_count = learning.get('failure_count', 0)
                patterns = learning.get('analysis', {}).get('patterns', [])
                print(f"  • {timestamp[:19]}: {failure_count} failures")
                if patterns:
                    print(f"    Patterns: {', '.join(patterns)}")
        else:
            print(f"\n📝 {component.upper()}: No evolutions yet")


def example_5_manual_evolution():
    """Example 5: Manually trigger evolution (advanced)"""
    print("\n" + "="*60)
    print("Example 5: Manual Evolution")
    print("="*60)
    
    print("\n⚠️ Evolution is normally automatic!")
    print("This example shows how to manually trigger it (for testing).\n")
    
    # Create some fake failures
    fake_failures = [
        {
            "timestamp": "2026-01-13T15:00:00",
            "component": "executor",
            "task": "Click button",
            "success": False,
            "error_type": "element_not_found",
            "error_details": "Button not found"
        }
        for _ in range(5)
    ]
    
    # Analyze failures
    analysis = prompt_evolution.analyze_failures("executor", fake_failures)
    print(f"📊 Analysis: {analysis}")
    
    # Note: In production, evolution happens automatically
    # when failure threshold is reached
    print("\n💡 In production: evolution triggers at 20% failure rate")


def example_6_reload_prompts():
    """Example 6: Reloading prompts after manual edits"""
    print("\n" + "="*60)
    print("Example 6: Reloading Prompts")
    print("="*60)
    
    print("\n1. Edit a prompt file:")
    print("   vim prompts/planner_prompt.md")
    
    print("\n2. Reload prompts:")
    prompt_loader.reload_all()
    print("   ✓ All prompts reloaded from disk")
    
    print("\n3. Check for updates:")
    updates = prompt_loader.check_for_updates()
    for component, updated in updates.items():
        status = "📝 Updated" if updated else "✓ Current"
        print(f"   {status}: {component}")


def run_all_examples():
    """Run all examples"""
    print("\n" + "🚀" + "="*58 + "🚀")
    print("   Houdini Agent - Prompt Evolution System Examples")
    print("🚀" + "="*58 + "🚀\n")
    
    example_1_load_prompts()
    example_2_record_feedback()
    example_3_view_statistics()
    example_4_check_learnings()
    example_5_manual_evolution()
    example_6_reload_prompts()
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60)
    print("\n💡 Next steps:")
    print("  • Run actual tasks: python -m src.main --task 'your task'")
    print("  • View statistics: python -m src.utils.prompt_stats")
    print("  • Read documentation: PROMPT_SYSTEM.md")
    print()


if __name__ == "__main__":
    run_all_examples()
