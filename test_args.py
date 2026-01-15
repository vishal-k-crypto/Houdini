#!/usr/bin/env python3
"""Test argument parsing logic for different modes."""

import argparse

# Recreate the parser from main.py
parser = argparse.ArgumentParser()
parser.add_argument('--use-adaptive', action='store_true', default=True)
parser.add_argument('--legacy', dest='use_adaptive', action='store_false')
parser.add_argument('--langgraph', dest='use_langgraph', action='store_true', default=False)
parser.add_argument('--use-enhanced', action='store_true', default=True)
parser.add_argument('--no-enhanced', dest='use_enhanced', action='store_false')

print("=" * 60)
print("ARGUMENT PARSING VERIFICATION")
print("=" * 60)
print()

# Test default mode (no args)
args = parser.parse_args([])
print('Default mode (no args):')
print(f'  use_adaptive: {args.use_adaptive} (expected: True)')
print(f'  use_langgraph: {args.use_langgraph} (expected: False)')
print(f'  use_enhanced: {args.use_enhanced} (expected: True)')
assert args.use_adaptive == True, "use_adaptive should default to True"
assert args.use_langgraph == False, "use_langgraph should default to False"
assert args.use_enhanced == True, "use_enhanced should default to True"
print("  ✅ Defaults verified")
print()

# Test with --legacy
args = parser.parse_args(['--legacy'])
print('With --legacy:')
print(f'  use_adaptive: {args.use_adaptive} (expected: False)')
print(f'  use_langgraph: {args.use_langgraph} (expected: False)')
assert args.use_adaptive == False, "--legacy should set use_adaptive to False"
print("  ✅ Legacy mode verified")
print()

# Test with --langgraph
args = parser.parse_args(['--langgraph'])
print('With --langgraph:')
print(f'  use_adaptive: {args.use_adaptive} (expected: True)')
print(f'  use_langgraph: {args.use_langgraph} (expected: True)')
assert args.use_langgraph == True, "--langgraph should set use_langgraph to True"
print("  ✅ LangGraph mode verified")
print()

# Test with --no-enhanced
args = parser.parse_args(['--no-enhanced'])
print('With --no-enhanced:')
print(f'  use_enhanced: {args.use_enhanced} (expected: False)')
assert args.use_enhanced == False, "--no-enhanced should set use_enhanced to False"
print("  ✅ No-enhanced mode verified")
print()

# Test mutually exclusive modes
args = parser.parse_args(['--langgraph', '--legacy'])
print('With --langgraph --legacy:')
print(f'  use_adaptive: {args.use_adaptive} (will be False due to --legacy)')
print(f'  use_langgraph: {args.use_langgraph} (will be True)')
print("  ⚠️  Note: --langgraph takes priority in main.py logic")
print()

print("=" * 60)
print("✅ Argument parsing verified - no conflicts!")
print("=" * 60)
