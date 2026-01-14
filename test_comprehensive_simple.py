#!/usr/bin/env python3
"""
Simple test to verify comprehensive instructions file structure
"""

from pathlib import Path
import re

def test_comprehensive_file():
    # Path to comprehensive instructions
    comp_file = Path(__file__).parent / "prompts" / "comprehensive_agent_instructions.md"
    
    print("=" * 80)
    print("COMPREHENSIVE INSTRUCTIONS FILE TEST")
    print("=" * 80)
    
    print(f"\n📄 File: {comp_file}")
    
    if not comp_file.exists():
        print("❌ ERROR: File does not exist!")
        return
    
    print("✓ File exists")
    
    # Read file
    with open(comp_file, 'r') as f:
        content = f.read()
    
    # Stats
    size_kb = len(content) / 1024
    lines = content.count('\n') + 1
    words = len(content.split())
    
    print(f"\n📊 File Statistics:")
    print(f"   Size: {size_kb:.2f} KB")
    print(f"   Lines: {lines:,}")
    print(f"   Words: {words:,}")
    
    # Find sections
    print(f"\n📖 Section Detection:")
    
    sections = [
        ("PART 1: PLANNER", r"# PART 1: PLANNER AGENT COMPREHENSIVE INSTRUCTIONS"),
        ("PART 2: EXECUTOR", r"# PART 2: EXECUTOR AGENT COMPREHENSIVE INSTRUCTIONS"),
        ("PART 3: SUPERVISOR", r"# PART 3: SUPERVISOR AGENT COMPREHENSIVE INSTRUCTIONS")
    ]
    
    for name, pattern in sections:
        match = re.search(pattern, content)
        if match:
            print(f"   ✓ {name} found at position {match.start()}")
        else:
            print(f"   ❌ {name} NOT FOUND")
    
    # Extract each section
    print(f"\n📦 Section Extraction:")
    
    # Planner section
    planner_start = re.search(r"# PART 1: PLANNER AGENT COMPREHENSIVE INSTRUCTIONS", content)
    planner_end = re.search(r"# PART 2: EXECUTOR AGENT COMPREHENSIVE INSTRUCTIONS", content)
    if planner_start and planner_end:
        planner_section = content[planner_start.start():planner_end.start()]
        planner_lines = planner_section.count('\n')
        print(f"   ✓ Planner: {planner_lines:,} lines")
    
    # Executor section
    executor_start = re.search(r"# PART 2: EXECUTOR AGENT COMPREHENSIVE INSTRUCTIONS", content)
    executor_end = re.search(r"# PART 3: SUPERVISOR AGENT COMPREHENSIVE INSTRUCTIONS", content)
    if executor_start and executor_end:
        executor_section = content[executor_start.start():executor_end.start()]
        executor_lines = executor_section.count('\n')
        print(f"   ✓ Executor: {executor_lines:,} lines")
    
    # Supervisor section
    supervisor_start = re.search(r"# PART 3: SUPERVISOR AGENT COMPREHENSIVE INSTRUCTIONS", content)
    supervisor_end = re.search(r"# COMPREHENSIVE INSTRUCTIONS SUMMARY", content)
    if supervisor_start and supervisor_end:
        supervisor_section = content[supervisor_start.start():supervisor_end.start()]
        supervisor_lines = supervisor_section.count('\n')
        print(f"   ✓ Supervisor: {supervisor_lines:,} lines")
    
    # Check for key content
    print(f"\n🔍 Content Verification:")
    
    checks = [
        ("Nano Banana knowledge", "nano banana"),
        ("Gemini ecosystem", "gemini.google.com"),
        ("Tool ecosystem", "Tool Ecosystem Knowledge"),
        ("macOS shortcuts", "Cmd+Space"),
        ("Vision execution", "accessibility tree"),
        ("User intent respect", "User Intent Respect" or "CRITICAL: Respect User Intent"),
    ]
    
    for name, keyword in checks:
        if keyword.lower() in content.lower():
            print(f"   ✓ {name}")
        else:
            print(f"   ⚠️  {name} - keyword not found")
    
    print(f"\n{'='*80}")
    print("TEST COMPLETE ✓")
    print(f"{'='*80}")

if __name__ == "__main__":
    test_comprehensive_file()
