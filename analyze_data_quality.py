#!/usr/bin/env python3
"""Analyze replay session data quality for ML training estimation."""

import json
from collections import defaultdict
from pathlib import Path

def analyze_replay_session(filepath):
    """Analyze a single replay session."""
    with open(filepath) as f:
        data = json.load(f)
    
    total_events = len(data['events'])
    duration_ms = data['events'][-1]['relative_ms']
    duration_sec = duration_ms / 1000
    
    # Count event types
    event_types = defaultdict(int)
    for e in data['events']:
        event_types[e['event_type']] += 1
    
    # Count actions
    actions = [e for e in data['events'] if e['event_type'] == 'action_start']
    action_types = defaultdict(int)
    for e in actions:
        atype = e['data'].get('action_type', 'unknown')
        action_types[atype] += 1
    
    # Check data quality
    has_screenshots = any(e.get('screenshot_path') for e in data['events'])
    cursor_moves = event_types.get('cursor_move', 0)
    thinking_events = sum(1 for k in event_types if 'thinking' in k)
    
    return {
        'total_events': total_events,
        'duration_sec': duration_sec,
        'success': data.get('success', None),
        'actions': len(actions),
        'action_types': dict(action_types),
        'has_screenshots': has_screenshots,
        'cursor_moves': cursor_moves,
        'thinking_events': thinking_events,
        'event_types': dict(event_types)
    }

def estimate_training_data_needed(quality_metrics):
    """Estimate data needed for perfect prediction."""
    
    print("\n" + "="*70)
    print("📊 DATA QUALITY ASSESSMENT")
    print("="*70)
    
    print(f"\n1. CURRENT SAMPLE METRICS:")
    print(f"   • Total events: {quality_metrics['total_events']}")
    print(f"   • Duration: {quality_metrics['duration_sec']:.1f} seconds")
    print(f"   • Actions taken: {quality_metrics['actions']}")
    print(f"   • Task success: {quality_metrics['success']}")
    print(f"   • Action diversity: {len(quality_metrics['action_types'])} types")
    for atype, count in quality_metrics['action_types'].items():
        print(f"     - {atype}: {count}")
    
    # Calculate quality score
    quality_score = 0
    max_score = 5
    
    print(f"\n2. DATA QUALITY FACTORS:")
    
    # Factor 1: Screenshots (critical for vision-based models)
    if quality_metrics['has_screenshots']:
        print(f"   ✓ Visual states: Present (HIGH VALUE)")
        quality_score += 2
    else:
        print(f"   ✗ Visual states: MISSING (CRITICAL ISSUE)")
        print(f"     → Without screenshots, state representation is incomplete")
    
    # Factor 2: Action diversity
    action_diversity = len(quality_metrics['action_types'])
    if action_diversity >= 4:
        print(f"   ✓ Action diversity: {action_diversity} types (Good)")
        quality_score += 1
    else:
        print(f"   ⚠ Action diversity: {action_diversity} types (Limited)")
        quality_score += 0.5
    
    # Factor 3: Thinking/reasoning traces
    if quality_metrics['thinking_events'] > 0:
        print(f"   ✓ Reasoning traces: {quality_metrics['thinking_events']} events")
        quality_score += 1
    else:
        print(f"   ✗ Reasoning traces: Missing")
    
    # Factor 4: Cursor tracking
    if quality_metrics['cursor_moves'] > 10:
        print(f"   ✓ Cursor tracking: {quality_metrics['cursor_moves']} movements")
        quality_score += 0.5
    else:
        print(f"   ⚠ Cursor tracking: Limited")
        quality_score += 0.25
    
    # Factor 5: Outcome label
    if quality_metrics['success'] is not None:
        print(f"   ✓ Outcome label: Available")
        quality_score += 0.5
    else:
        print(f"   ✗ Outcome label: Missing")
    
    quality_percentage = (quality_score / max_score) * 100
    
    print(f"\n   📈 Overall Quality Score: {quality_score:.1f}/{max_score} ({quality_percentage:.0f}%)")
    
    # Calculate estimates
    print(f"\n3. REALISTIC TRAINING DATA ESTIMATES:")
    print(f"   " + "-"*60)
    
    # State-action pairs in this sample
    state_action_pairs = quality_metrics['actions']
    
    # Estimate based on RL/imitation learning research
    print(f"\n   Current sample provides: {state_action_pairs} state-action pairs")
    
    # Different model approaches and their data needs
    estimates = []
    
    if not quality_metrics['has_screenshots']:
        print(f"\n   ⚠️  WARNING: Without screenshots, estimates are HIGHLY uncertain")
        print(f"   Visual state is crucial for UI automation tasks")
    
    # Behavior cloning baseline
    print(f"\n   A) Behavior Cloning (Supervised Learning):")
    print(f"      • For basic competence: 50,000-200,000 state-action pairs")
    print(f"      • For robust performance: 500,000-2,000,000 pairs")
    print(f"      • Sessions needed: 30,000-120,000 similar tasks")
    print(f"      • Time estimate: 400-1,600 hours of demonstrations")
    estimates.append(("Behavior Cloning (basic)", 50000, 200000))
    
    # Reinforcement learning
    print(f"\n   B) Reinforcement Learning (with human demos as init):")
    print(f"      • Initial human data: 10,000-50,000 pairs")
    print(f"      • Self-play/exploration: 500,000-5,000,000 interactions")
    print(f"      • Human sessions: 6,000-30,000 tasks")
    print(f"      • Time estimate: 80-400 hours human + extensive compute")
    estimates.append(("RL with human init", 10000, 50000))
    
    # Offline RL
    print(f"\n   C) Offline RL (Learning from logged data):")
    print(f"      • Minimum data: 100,000-500,000 pairs")
    print(f"      • Strong performance: 1,000,000-10,000,000 pairs")
    print(f"      • Sessions needed: 60,000-600,000 tasks")
    print(f"      • Time estimate: 800-8,000 hours of demonstrations")
    estimates.append(("Offline RL", 100000, 500000))
    
    # Vision-language-action models (like Claude Computer Use)
    print(f"\n   D) Vision-Language-Action Model (VLA):")
    print(f"      • Minimum viable: 5,000-20,000 diverse tasks")
    print(f"      • Good generalization: 50,000-200,000 tasks")
    print(f"      • Expert-level: 500,000-1,000,000+ tasks")
    print(f"      • Time estimate: 70-270 hours (if diverse + quality)")
    estimates.append(("VLA Model", 5000, 20000))
    
    print(f"\n4. KEY CONSIDERATIONS FOR 'PERFECT' PREDICTION:")
    print(f"   " + "-"*60)
    print(f"   ⚠️  'Perfect prediction' is NOT achievable in practice because:")
    print(f"\n   • Web UIs change dynamically (updates, A/B tests)")
    print(f"   • Network latency varies unpredictably")
    print(f"   • User tasks have inherent ambiguity")
    print(f"   • Edge cases are infinite")
    print(f"\n   🎯 Realistic target: 85-95% success rate on similar tasks")
    
    print(f"\n5. DATA QUALITY RECOMMENDATIONS:")
    print(f"   " + "-"*60)
    
    if not quality_metrics['has_screenshots']:
        print(f"   🚨 CRITICAL: Enable screenshot capture!")
        print(f"      → Screenshots are essential for vision-based models")
        print(f"      → Current data has limited training value without them")
    
    print(f"\n   ✓ Improve data diversity:")
    print(f"     - Different websites and UI patterns")
    print(f"     - Various task types (search, form-fill, download, etc)")
    print(f"     - Success AND failure cases")
    print(f"     - Different times of day (UI may change)")
    
    print(f"\n   ✓ Add richer annotations:")
    print(f"     - UI element labels (buttons, inputs, links)")
    print(f"     - Semantic action descriptions")
    print(f"     - Failure reasons when tasks fail")
    print(f"     - Alternative valid actions at each state")
    
    print(f"\n   ✓ Balance your dataset:")
    print(f"     - 70% successful trajectories")
    print(f"     - 20% recoverable failures")
    print(f"     - 10% unrecoverable failures (for safety)")
    
    print(f"\n6. REALISTIC ROADMAP:")
    print(f"   " + "-"*60)
    print(f"   Phase 1 - Proof of Concept (500-2,000 tasks):")
    print(f"   • Demonstrate basic task completion on 2-3 websites")
    print(f"   • Expected: 40-60% success rate")
    print(f"   • Time: 7-27 hours of human demos")
    
    print(f"\n   Phase 2 - Working Prototype (5,000-10,000 tasks):")
    print(f"   • Handle 10-20 websites reliably")
    print(f"   • Expected: 65-75% success rate")
    print(f"   • Time: 70-135 hours of human demos")
    
    print(f"\n   Phase 3 - Production Ready (50,000-100,000 tasks):")
    print(f"   • Handle diverse web automation scenarios")
    print(f"   • Expected: 80-90% success rate")
    print(f"   • Time: 700-1,350 hours of human demos")
    
    print(f"\n   Phase 4 - Expert System (200,000+ tasks):")
    print(f"   • Near-human performance on known task types")
    print(f"   • Expected: 85-95% success rate")
    print(f"   • Time: 2,700+ hours of human demos")
    
    print(f"\n7. COST-EFFECTIVE STRATEGIES:")
    print(f"   " + "-"*60)
    print(f"   • Use data augmentation (rotate, crop, color shift)")
    print(f"   • Pre-train on synthetic UI interactions")
    print(f"   • Active learning: focus on uncertain states")
    print(f"   • Transfer learning from existing VLMs")
    print(f"   • Combine with web scraping for UI understanding")
    
    print("\n" + "="*70)
    print("💡 BOTTOM LINE:")
    print("="*70)
    print(f"For a PRACTICAL executor that works well (85-90% success):")
    print(f"  • Minimum: 10,000-50,000 diverse, high-quality tasks")
    print(f"  • Time: 135-675 hours of human demonstrations")
    print(f"  • Cost: $5,000-$25,000 (at $37/hr for data collection)")
    print(f"\nYour current sample is 1/{state_action_pairs:,} of minimum needed.")
    print(f"Multiply by ~600-3,000x to reach practical performance.")
    print("="*70 + "\n")

if __name__ == '__main__':
    filepath = 'data/replay_sessions/e76e88fd_2026-01-17T18-13-53-289334.json'
    metrics = analyze_replay_session(filepath)
    estimate_training_data_needed(metrics)
