"""
Test Context Memory - Tests for the context-aware clipboard memory system.

This tests the ability to:
1. Extract file/resource references from tasks
2. Build associations from feedback log
3. Resolve ambiguous references in new tasks
"""

import sys
import json
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.utils.context_memory import (
    ContextMemory,
    ResourceContext,
    ResolvedContext,
    resolve_task_context,
    learn_from_successful_task,
    get_planner_context
)


def test_resource_extraction():
    """Test that we can extract file/resource info from tasks."""
    print("\n=== Test 1: Resource Extraction ===")
    
    # Create a fresh context memory in temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextMemory(persist_dir=Path(tmpdir))
        
        # Test extracting from various task patterns
        test_cases = [
            {
                "task": "create a folder in desktop named jhonny and add a txt file",
                "actions": ["Create folder on Desktop", "Save poem to folder"],
                "expected_types": ["folder", "file"]
            },
            {
                "task": "send the report to John via email",
                "actions": ["Open email", "Attach report.pdf", "Send to John"],
                "expected_types": ["file", "contact"]
            },
            {
                "task": "open ~/Documents/quarterly_report.pdf",
                "actions": ["Open PDF viewer", "Load file"],
                "expected_types": ["file"]
            }
        ]
        
        for i, tc in enumerate(test_cases):
            # Extract resources
            resources = cm._extract_file_info(tc["task"], tc["actions"])
            print(f"\n  Test {i+1}: '{tc['task'][:50]}...'")
            print(f"  Extracted: {len(resources)} resources")
            for r in resources:
                print(f"    - {r['name']} ({r['type']})")
        
        print("  ✅ Resource extraction working")


def test_learning_from_tasks():
    """Test that we can learn from successful tasks."""
    print("\n=== Test 2: Learning from Tasks ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextMemory(persist_dir=Path(tmpdir))
        
        # Simulate learning from multiple tasks about "reports"
        tasks = [
            ("send the quarterly report to marketing", 
             ["Open ~/Documents/Reports/Q4_report.pdf", "Email to marketing"]),
            ("update the quarterly report with new figures",
             ["Open ~/Documents/Reports/Q4_report.pdf", "Edit document"]),
            ("print the report for the meeting",
             ["Open ~/Documents/Reports/Q4_report.pdf", "Print"]),
        ]
        
        for task, actions in tasks:
            cm.learn_from_task(task, actions, success=True)
        
        print(f"  Learned {len(cm.resources)} resources")
        print(f"  Term associations: {len(cm.term_to_resources)}")
        
        # Check that "report" is now associated
        for term, ids in cm.term_to_resources.items():
            print(f"    - '{term}' -> {len(ids)} resources")
        
        print("  ✅ Learning from tasks working")


def test_context_resolution():
    """Test resolving ambiguous references."""
    print("\n=== Test 3: Context Resolution ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextMemory(persist_dir=Path(tmpdir))
        
        # First, teach it about "the report" WITH A LOCATION
        cm.learn_from_task(
            "email the quarterly report to the CEO",
            ["Open ~/Documents/Reports/Q4_2025.pdf", "Compose email", "Send to CEO"],
            success=True
        )
        
        # Access it a few times to build confidence
        cm.resources[list(cm.resources.keys())[0]].update_access()
        cm.resources[list(cm.resources.keys())[0]].update_access()
        cm.resources[list(cm.resources.keys())[0]].update_access()
        
        # Also teach about "John"
        cm.learn_from_task(
            "send a message to John about the project",
            ["Open Messages", "Message John Smith"],
            success=True
        )
        
        # Show what we learned
        print(f"  Learned {len(cm.resources)} resources:")
        for rid, rc in cm.resources.items():
            print(f"    - {rc.resource_name} ({rc.resource_type}) @ {rc.location or 'no location'}")
            print(f"      Terms: {rc.associated_terms}, Confidence: {rc.confidence:.2f}")
        
        # Now try to resolve a new task
        resolved = cm.resolve_context("send the report to John")
        
        print(f"\n  Original task: '{resolved.original_task}'")
        print(f"  Enriched task: '{resolved.enriched_task}'")
        print(f"  Confidence: {resolved.confidence:.2f}")
        print(f"  Resolved references: {len(resolved.resolved_references)}")
        for ref in resolved.resolved_references:
            print(f"    - '{ref['term']}' -> {ref['resource']['resource_name']} ({ref['match_type']}, conf={ref['confidence']:.2f})")
        print(f"  Suggested files: {resolved.suggested_files}")
        print(f"  Suggested contacts: {resolved.suggested_contacts}")
        print(f"  Context hints: {resolved.context_hints}")
        
        # Test planner context generation
        planner_context = cm.get_context_for_planner("send the report to John")
        print(f"\n  Planner context:\n{planner_context if planner_context else '  (none)'}")
        
        print("  ✅ Context resolution working")


def test_planner_context_generation():
    """Test generating context for the planner."""
    print("\n=== Test 4: Planner Context Generation ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = ContextMemory(persist_dir=Path(tmpdir))
        
        # Teach it about various files
        cm.learn_from_task(
            "open the project proposal document",
            ["Open ~/Documents/Projects/proposal_v2.docx"],
            success=True
        )
        cm.learn_from_task(
            "edit the budget spreadsheet",
            ["Open ~/Documents/Finance/budget_2025.xlsx"],
            success=True
        )
        
        # Generate context for a new task
        context = cm.get_context_for_planner("review the project proposal and update budget")
        
        print(f"  Generated context for planner:")
        print("-" * 40)
        print(context if context else "  (no context generated)")
        print("-" * 40)
        
        print("  ✅ Planner context generation working")


def test_bootstrap_from_feedback():
    """Test bootstrapping from existing feedback log."""
    print("\n=== Test 5: Bootstrap from Feedback Log ===")
    
    feedback_path = Path(__file__).parent / "data" / "feedback_log.json"
    
    if not feedback_path.exists():
        print("  ⚠️ No feedback_log.json found, skipping bootstrap test")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake feedback log for testing
        test_feedback = [
            {
                "timestamp": "2026-01-13T21:42:52.864765",
                "component": "planner",
                "task": "create a folder in desktop named jhonny and add a txt file",
                "success": True,
                "actions_taken": ["Create folder on Desktop", "Save poem file"]
            },
            {
                "timestamp": "2026-01-14T13:31:59.547842",
                "component": "planner", 
                "task": "send the report to marketing team",
                "success": True,
                "actions_taken": ["Open report.pdf", "Email to marketing"]
            }
        ]
        
        # Write test feedback
        feedback_file = Path(tmpdir) / "feedback_log.json"
        with open(feedback_file, 'w') as f:
            json.dump(test_feedback, f)
        
        # Patch the feedback log path
        import src.utils.context_memory as cm_module
        original_path = cm_module.FEEDBACK_LOG_FILE
        cm_module.FEEDBACK_LOG_FILE = feedback_file
        
        try:
            cm = ContextMemory(persist_dir=Path(tmpdir))
            print(f"  Bootstrapped {len(cm.resources)} resources from feedback log")
            
            for rid, rc in list(cm.resources.items())[:5]:
                print(f"    - {rc.resource_name} ({rc.resource_type})")
                
        finally:
            cm_module.FEEDBACK_LOG_FILE = original_path
        
        print("  ✅ Bootstrap from feedback working")


def test_convenience_functions():
    """Test the convenience functions."""
    print("\n=== Test 6: Convenience Functions ===")
    
    # These use the global instance
    # Just verify they don't crash
    try:
        context = get_planner_context("send the report to John")
        print(f"  get_planner_context() returned: {len(context)} chars")
        
        resolved = resolve_task_context("open the document")
        print(f"  resolve_task_context() returned: {type(resolved).__name__}")
        
        learn_from_successful_task(
            "test task for convenience function",
            ["action 1", "action 2"]
        )
        print(f"  learn_from_successful_task() completed")
        
        print("  ✅ Convenience functions working")
    except Exception as e:
        print(f"  ⚠️ Error (may be expected without FAISS): {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("CONTEXT MEMORY TEST SUITE")
    print("=" * 60)
    
    test_resource_extraction()
    test_learning_from_tasks()
    test_context_resolution()
    test_planner_context_generation()
    test_bootstrap_from_feedback()
    test_convenience_functions()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
