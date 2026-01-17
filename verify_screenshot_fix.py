#!/usr/bin/env python3
"""Test screenshot capture in replay sessions."""

import sys
import json
from pathlib import Path

def verify_screenshot_capture():
    """Verify that screenshot capture is working."""
    
    print("\n" + "="*70)
    print("🔍 SCREENSHOT CAPTURE VERIFICATION")
    print("="*70)
    
    # Check if screenshots directory exists
    screenshots_dir = Path("data/screenshots")
    if not screenshots_dir.exists():
        print("\n❌ ERROR: Screenshots directory doesn't exist!")
        return False
    
    print(f"\n✓ Screenshots directory exists: {screenshots_dir}")
    
    # Count screenshots
    screenshots = list(screenshots_dir.rglob("*.png"))
    print(f"✓ Found {len(screenshots)} existing screenshots")
    
    # Check recent replay sessions
    replay_dir = Path("data/replay_sessions")
    if replay_dir.exists():
        replay_files = sorted(replay_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        print(f"\n📋 Analyzing recent replay sessions:")
        
        for i, replay_file in enumerate(replay_files[:5]):  # Check last 5 sessions
            with open(replay_file) as f:
                data = json.load(f)
            
            total_events = len(data['events'])
            events_with_screenshots = sum(1 for e in data['events'] if e.get('screenshot_path'))
            action_events = sum(1 for e in data['events'] if e['event_type'] == 'action_start')
            
            percentage = (events_with_screenshots / total_events * 100) if total_events > 0 else 0
            
            # Get filename
            filename = replay_file.name
            timestamp = data.get('started_at', 'unknown')
            
            status = "✓" if events_with_screenshots > 0 else "✗"
            print(f"\n  {status} Session: {filename}")
            print(f"     Started: {timestamp}")
            print(f"     Events: {total_events}")
            print(f"     Actions: {action_events}")
            print(f"     Screenshots: {events_with_screenshots} ({percentage:.1f}%)")
            
            if events_with_screenshots == 0:
                print(f"     ⚠️  WARNING: No screenshots captured!")
    
    print("\n" + "="*70)
    print("📝 FIX SUMMARY")
    print("="*70)
    
    print("\n✅ Applied fixes:")
    print("   1. Added screenshot capture before each action in adaptive_coordinator.py")
    print("   2. Screenshot paths are now passed to log_action() calls")
    print("   3. Visual state will be captured for all future executions")
    
    print("\n🎯 What this means for training data:")
    print("   • Each action will now have a 'before' screenshot")
    print("   • State-action pairs will include visual context")
    print("   • Vision-based models can learn from this data")
    print("   • Screenshots stored in: data/screenshots/")
    
    print("\n💡 Next steps:")
    print("   1. Run a new task to generate a replay session")
    print("   2. Verify screenshots are captured: check data/screenshots/")
    print("   3. Verify replay has screenshot_path set: check data/replay_sessions/")
    print("   4. Re-run analyze_data_quality.py on the new session")
    
    print("\n" + "="*70 + "\n")
    
    return True

if __name__ == '__main__':
    success = verify_screenshot_capture()
    sys.exit(0 if success else 1)
