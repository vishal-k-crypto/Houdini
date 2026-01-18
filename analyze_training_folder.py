#!/usr/bin/env python3
"""Quick analysis of training_sessions folder"""
import json
from pathlib import Path
from collections import Counter

folder = Path("data/training_sessions")
sessions = list(folder.glob("*.json"))

print(f"\n{'='*80}")
print(f"TRAINING_SESSIONS FOLDER ANALYSIS")
print(f"{'='*80}\n")

total_sessions = len(sessions)
total_actions = 0
total_screenshots = 0
success_count = 0
action_types = Counter()
unique_tasks = set()

for session_file in sessions:
    with open(session_file) as f:
        data = json.load(f)
    
    # Basic stats
    unique_tasks.add(data.get("task_description", ""))
    if data.get("success"):
        success_count += 1
    
    # Count actions and screenshots
    for event in data.get("events", []):
        if event.get("event_type") == "action_start":
            total_actions += 1
            action_type = event.get("data", {}).get("action_type", "unknown")
            action_types[action_type] += 1
        
        if event.get("screenshot_path"):
            total_screenshots += 1
            # Check if file exists
            if not Path(event["screenshot_path"]).exists():
                print(f"⚠️  Missing screenshot: {event['screenshot_path']}")

screenshot_coverage = (total_screenshots / total_actions * 100) if total_actions > 0 else 0
success_rate = (success_count / total_sessions * 100) if total_sessions > 0 else 0

print(f"📊 SESSION SUMMARY")
print(f"  Total Sessions: {total_sessions}")
print(f"  Unique Tasks: {len(unique_tasks)}")
print(f"  Success Rate: {success_count}/{total_sessions} ({success_rate:.1f}%)")
print()
print(f"📸 SCREENSHOT ANALYSIS")
print(f"  Total Actions: {total_actions}")
print(f"  Total Screenshots: {total_screenshots}")
print(f"  Coverage: {screenshot_coverage:.1f}%")
print()
print(f"🎯 ACTION TYPES")
for action_type, count in action_types.most_common():
    print(f"  • {action_type}: {count}")
print()

# Verdict
if screenshot_coverage >= 90 and success_rate >= 40:
    print("✅ EXCELLENT DATA - Ready for training!")
elif screenshot_coverage >= 60 and success_rate >= 20:
    print("⚠️  ACCEPTABLE DATA - Can start training with caution")
elif screenshot_coverage >= 30:
    print("⚠️  MARGINAL DATA - Needs improvement")
else:
    print("❌ POOR DATA - Not suitable for training")

print(f"\n{'='*80}\n")
