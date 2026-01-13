"""
Prompt Statistics and Monitoring Utility

View statistics about prompt evolution, success rates, and system performance.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.prompt_evolution import prompt_evolution
from src.utils.prompt_loader import prompt_loader
from datetime import datetime


def print_header(text):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_overall_stats():
    """Display overall system statistics."""
    print_header("Houdini Agent - Prompt Evolution Statistics")
    
    stats = prompt_evolution.get_statistics()
    
    print(f"\n📊 Overall Statistics:")
    print(f"  Total Executions: {stats['total_executions']}")
    print(f"  Total Prompt Evolutions: {stats['total_evolutions']}")
    
    if stats['total_executions'] > 0:
        overall_success = sum(
            s['executions'] - s['failures'] 
            for s in stats['components'].values()
        )
        overall_rate = overall_success / stats['total_executions']
        print(f"  Overall Success Rate: {overall_rate:.1%}")


def print_component_stats():
    """Display statistics for each component."""
    print_header("Component Performance")
    
    stats = prompt_evolution.get_statistics()
    
    for component, data in stats['components'].items():
        print(f"\n🔧 {component.upper()}")
        print(f"  Executions: {data['executions']}")
        print(f"  Success Rate: {data['success_rate']:.1%}")
        print(f"  Failures: {data['failures']}")
        print(f"  Prompt Version: v{data['prompt_version']}")
        
        # Show success indicator
        if data['success_rate'] >= 0.9:
            print(f"  Status: ✅ Excellent")
        elif data['success_rate'] >= 0.7:
            print(f"  Status: ⚠️ Good")
        else:
            print(f"  Status: ❌ Needs Improvement")


def print_recent_evolutions():
    """Display recent prompt evolutions."""
    print_header("Recent Prompt Evolutions")
    
    for component in ["planner", "executor", "supervisor"]:
        learnings = prompt_evolution.get_recent_learnings(component, count=3)
        
        if learnings:
            print(f"\n📝 {component.upper()} - Recent Learnings:")
            for i, learning in enumerate(learnings, 1):
                timestamp = learning.get('timestamp', 'unknown')
                if timestamp != 'unknown':
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    time_str = timestamp
                
                failure_count = learning.get('failure_count', 0)
                patterns = learning.get('analysis', {}).get('patterns', [])
                
                print(f"  {i}. {time_str}")
                print(f"     Triggered by: {failure_count} failures")
                if patterns:
                    print(f"     Patterns: {', '.join(patterns)}")
        else:
            print(f"\n📝 {component.upper()}: No evolutions yet")


def print_prompt_info():
    """Display information about prompt files."""
    print_header("Prompt Files Information")
    
    for component in ["planner", "executor", "supervisor"]:
        info = prompt_loader.get_prompt_info(component)
        
        print(f"\n📄 {component.upper()}_prompt.md")
        if info['exists']:
            print(f"  Size: {info['size_kb']} KB")
            print(f"  Cached: {'Yes' if info['cached'] else 'No'}")
            print(f"  Path: {info['path']}")
        else:
            print(f"  Status: ⚠️ Not found")
            print(f"  Expected at: {info['path']}")


def print_recent_feedback():
    """Display recent execution feedback."""
    print_header("Recent Execution Feedback")
    
    feedback_data = prompt_evolution.feedback_data[-10:]  # Last 10
    
    if not feedback_data:
        print("\n  No feedback data yet. Run some tasks first!")
        return
    
    print(f"\n  Showing last {len(feedback_data)} executions:\n")
    
    for entry in feedback_data:
        timestamp = entry.get('timestamp', 'unknown')
        if timestamp != 'unknown':
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%H:%M:%S")
        else:
            time_str = timestamp
        
        component = entry.get('component', 'unknown')
        success = entry.get('success', False)
        task = entry.get('task', '')[:40]  # Truncate
        
        status_icon = "✅" if success else "❌"
        print(f"  {status_icon} [{time_str}] {component:10} | {task}")
        
        if not success and entry.get('error_type'):
            print(f"      Error: {entry['error_type']}")


def print_recommendations():
    """Provide recommendations based on statistics."""
    print_header("Recommendations")
    
    stats = prompt_evolution.get_statistics()
    
    recommendations = []
    
    for component, data in stats['components'].items():
        if data['success_rate'] < 0.7 and data['executions'] > 5:
            recommendations.append(
                f"⚠️ {component.upper()} has low success rate ({data['success_rate']:.1%}). "
                f"System will auto-evolve prompts after more failures."
            )
        
        if data['executions'] < 10:
            recommendations.append(
                f"💡 {component.upper()} needs more test data ({data['executions']} executions). "
                f"Run more tasks for better evolution."
            )
    
    if not recommendations:
        recommendations.append("✅ All components performing well! Keep testing.")
    
    for rec in recommendations:
        print(f"\n  {rec}")


def main():
    """Main statistics display."""
    print_overall_stats()
    print_component_stats()
    print_prompt_info()
    print_recent_evolutions()
    print_recent_feedback()
    print_recommendations()
    
    print("\n" + "="*60)
    print("  Use this tool regularly to monitor system performance")
    print("  Prompts automatically evolve based on failure patterns")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
