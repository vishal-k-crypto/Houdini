#!/usr/bin/env python3
"""
Test script to verify comprehensive instructions are loaded correctly
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.prompt_loader import prompt_loader

def test_comprehensive_instructions():
    print("=" * 80)
    print("COMPREHENSIVE INSTRUCTIONS TEST")
    print("=" * 80)
    
    # Check if comprehensive file exists
    comp_file = prompt_loader.comprehensive_file
    print(f"\n📄 Comprehensive File: {comp_file}")
    print(f"   Exists: {comp_file.exists()}")
    
    if comp_file.exists():
        size_kb = comp_file.stat().st_size / 1024
        print(f"   Size: {size_kb:.2f} KB")
    
    # Test each component
    components = ["planner", "executor", "supervisor"]
    
    for component in components:
        print(f"\n{'='*80}")
        print(f"TESTING: {component.upper()}")
        print(f"{'='*80}")
        
        # Load prompt
        prompt = prompt_loader.load_prompt(component, force_reload=True, use_comprehensive=True)
        
        # Show stats
        lines = prompt.count('\n') + 1
        chars = len(prompt)
        words = len(prompt.split())
        
        print(f"✓ Loaded successfully")
        print(f"  Lines: {lines:,}")
        print(f"  Characters: {chars:,}")
        print(f"  Words: {words:,}")
        
        # Show first few lines
        first_lines = '\n'.join(prompt.split('\n')[:10])
        print(f"\n  First lines:")
        for line in first_lines.split('\n'):
            print(f"    {line[:77]}")
    
    print(f"\n{'='*80}")
    print("TEST COMPLETE ✓")
    print(f"{'='*80}")

if __name__ == "__main__":
    test_comprehensive_instructions()
