#!/usr/bin/env python3
"""
Comprehensive test showing the screenshot capture improvements.
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_all_sessions():
    """Analyze all replay sessions for screenshot coverage."""
    
    replay_dir = Path("data/replay_sessions")
    if not replay_dir.exists():
        print("❌ No replay sessions directory found")
        return
    
    replay_files = sorted(replay_dir.glob("*.json"), key=lambda x: x.stat().st_mtime)
    
    print("\n" + "="*80)
    print("📊 COMPLETE REPLAY SESSION ANALYSIS")
    print("="*80)
    
    stats = {
        'total_sessions': 0,
        'sessions_with_screenshots': 0,
        'total_actions': 0,
        'actions_with_screenshots': 0,
        'total_events': 0,
        'events_with_screenshots': 0,
    }
    
    sessions_by_quality = defaultdict(list)
    
    for replay_file in replay_files:
        try:
            with open(replay_file) as f:
                data = json.load(f)
            
            stats['total_sessions'] += 1
            
            total_events = len(data['events'])
            action_events = [e for e in data['events'] if e['event_type'] == 'action_start']
            events_with_ss = sum(1 for e in data['events'] if e.get('screenshot_path'))
            actions_with_ss = sum(1 for e in action_events if e.get('screenshot_path'))
            
            stats['total_events'] += total_events
            stats['total_actions'] += len(action_events)
            stats['events_with_screenshots'] += events_with_ss
            stats['actions_with_screenshots'] += actions_with_ss
            
            if events_with_ss > 0:
                stats['sessions_with_screenshots'] += 1
            
            # Categorize by quality
            if len(action_events) > 0:
                action_coverage = actions_with_ss / len(action_events)
                if action_coverage >= 0.9:
                    quality = 'excellent'
                elif action_coverage >= 0.5:
                    quality = 'good'
                elif action_coverage > 0:
                    quality = 'partial'
                else:
                    quality = 'none'
            else:
                quality = 'no_actions'
            
            sessions_by_quality[quality].append({
                'file': replay_file.name,
                'timestamp': data.get('started_at', 'unknown'),
                'actions': len(action_events),
                'actions_with_ss': actions_with_ss,
                'coverage': actions_with_ss / len(action_events) if action_events else 0
            })
            
        except Exception as e:
            print(f"⚠️  Error reading {replay_file.name}: {e}")
    
    # Print summary
    print(f"\n📈 OVERALL STATISTICS:")
    print(f"   Total sessions: {stats['total_sessions']}")
    print(f"   Sessions with screenshots: {stats['sessions_with_screenshots']} ({stats['sessions_with_screenshots']/stats['total_sessions']*100:.1f}%)")
    print(f"   Total events: {stats['total_events']}")
    print(f"   Events with screenshots: {stats['events_with_screenshots']} ({stats['events_with_screenshots']/stats['total_events']*100:.1f}%)")
    print(f"   Total actions: {stats['total_actions']}")
    print(f"   Actions with screenshots: {stats['actions_with_screenshots']} ({stats['actions_with_screenshots']/stats['total_actions']*100 if stats['total_actions'] > 0 else 0:.1f}%)")
    
    # Print by quality category
    print(f"\n📊 SESSIONS BY QUALITY:")
    
    for quality in ['excellent', 'good', 'partial', 'none', 'no_actions']:
        sessions = sessions_by_quality[quality]
        if not sessions:
            continue
        
        if quality == 'excellent':
            emoji = "🌟"
            desc = "90%+ screenshot coverage"
        elif quality == 'good':
            emoji = "✅"
            desc = "50-90% screenshot coverage"
        elif quality == 'partial':
            emoji = "⚠️"
            desc = "1-50% screenshot coverage"
        elif quality == 'none':
            emoji = "❌"
            desc = "0% screenshot coverage (NEEDS FIX)"
        else:
            emoji = "⚪"
            desc = "No actions"
        
        print(f"\n   {emoji} {quality.upper()} ({len(sessions)} sessions) - {desc}")
        
        # Show up to 3 examples
        for session in sessions[:3]:
            print(f"      • {session['file'][:40]:40s} | Actions: {session['actions']:2d} | Coverage: {session['coverage']*100:5.1f}%")
        
        if len(sessions) > 3:
            print(f"      ... and {len(sessions)-3} more")
    
    # Recommendations
    print(f"\n" + "="*80)
    print("💡 RECOMMENDATIONS")
    print("="*80)
    
    action_coverage = stats['actions_with_screenshots'] / stats['total_actions'] if stats['total_actions'] > 0 else 0
    
    if action_coverage < 0.1:
        print("\n❌ CRITICAL: Very low screenshot coverage!")
        print("   → The fix has been applied to the code")
        print("   → Run a NEW task to test the fix")
        print("   → All OLD sessions lack screenshots (expected)")
    elif action_coverage < 0.5:
        print("\n⚠️  WARNING: Some sessions missing screenshots")
        print("   → Check if all execution paths capture screenshots")
        print("   → Review sessions with 0% coverage")
    elif action_coverage < 0.9:
        print("\n✅ GOOD: Most actions have screenshots")
        print("   → Consider improving edge cases")
        print("   → Review partial coverage sessions")
    else:
        print("\n🌟 EXCELLENT: Strong screenshot coverage!")
        print("   → Data quality is suitable for training")
        print("   → Continue collecting diverse tasks")
    
    # Training data estimate
    print(f"\n" + "="*80)
    print("📚 TRAINING DATA ESTIMATE")
    print("="*80)
    
    quality_actions = stats['actions_with_screenshots']
    
    print(f"\nCurrent high-quality state-action pairs: {quality_actions}")
    
    if quality_actions < 100:
        print(f"\n🎯 Immediate Goal: Reach 500-2,000 pairs (proof of concept)")
        print(f"   Need: {500 - quality_actions} - {2000 - quality_actions} more")
        print(f"   Estimated sessions: {(500 - quality_actions) // 15} - {(2000 - quality_actions) // 15}")
    elif quality_actions < 5000:
        print(f"\n🎯 Current Goal: Reach 5,000-10,000 pairs (working prototype)")
        print(f"   Need: {5000 - quality_actions} - {10000 - quality_actions} more")
        print(f"   Estimated sessions: {(5000 - quality_actions) // 15} - {(10000 - quality_actions) // 15}")
    elif quality_actions < 50000:
        print(f"\n🎯 Current Goal: Reach 50,000 pairs (production ready)")
        print(f"   Need: {50000 - quality_actions} more")
        print(f"   Estimated sessions: {(50000 - quality_actions) // 15}")
    else:
        print(f"\n🌟 MILESTONE REACHED: Production-ready dataset!")
        print(f"   Continue collecting for expert-level performance")
    
    print("\n" + "="*80 + "\n")

if __name__ == '__main__':
    analyze_all_sessions()
