
import os
import sys
import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Mock dependencies
sys.path.append(os.getcwd())
from src.auto_collector import TaskGenerator

# Setup directories
DATA_DIR = Path("data/training_sessions")
SCREENSHOT_DIR = Path("data/screenshots")
DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

def create_mock_screenshot(text: str, path: Path):
    """Create a dummy screenshot with text overlay."""
    img = Image.new('RGB', (1920, 1080), color=(50, 50, 60))
    d = ImageDraw.Draw(img)
    
    # Draw simple "UI"
    d.rectangle([0, 0, 1920, 60], fill=(30, 30, 40))  # Top bar
    d.rectangle([0, 1020, 1920, 1080], fill=(30, 30, 40))  # Bottom bar
    
    # Draw text
    d.text((100, 100), f"SIMULATED SCREENSHOT", fill=(255, 255, 255), align="center", font_size=40)
    d.text((100, 200), f"Action: {text}", fill=(0, 255, 0), font_size=30)
    d.text((100, 300), f"Timestamp: {datetime.now().isoformat()}", fill=(200, 200, 200), font_size=20)
    
    img.save(path)

def simulate_execution(task_description: str):
    """Simulate a full execution trace."""
    task_id = f"{int(time.time())}_{random.randint(1000,9999)}"
    session_file = DATA_DIR / f"{task_id}_{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.json"
    
    events = []
    
    # 1. Start
    events.append({
        "event_type": "task_start",
        "timestamp_ms": int(time.time() * 1000),
        "data": {"task_description": task_description}
    })
    
    steps = [
        ("Opens LibreOffice", "hotkey:command,space"),
        ("Types 'LibreOffice'", "type:LibreOffice"),
        ("Opens Presentation", "click:Presentation Icon"),
        ("Creates Title Slide", "click:Title Layout"),
        ("Types Topic", f"type:{task_description[:20]}...")
    ]
    
    for i, (desc, action) in enumerate(steps):
        # Screenshot
        ss_name = f"{task_id}_step{i}.png"
        ss_path = SCREENSHOT_DIR / ss_name
        create_mock_screenshot(desc, ss_path)
        
        # Thinking
        events.append({
            "event_type": "thinking_executor",
            "timestamp_ms": int(time.time() * 1000),
            "data": {"message": f"Planning step: {desc}"}
        })
        
        # Action Start
        events.append({
            "event_type": "action_start",
            "timestamp_ms": int(time.time() * 1000) + 100,
            "data": {"action": action},
            "screenshot_path": str(ss_path.absolute())
        })
        
        # Action Complete
        time.sleep(0.1)
        events.append({
            "event_type": "action_complete",
            "timestamp_ms": int(time.time() * 1000) + 500,
            "data": {"success": True}
        })
        
    # Complete
    events.append({
        "event_type": "task_complete",
        "timestamp_ms": int(time.time() * 1000),
        "data": {"success": True}
    })
    
    session_data = {
        "task_id": task_id,
        "task_description": task_description,
        "success": True,
        "events": events
    }
    
    with open(session_file, 'w') as f:
        json.dump(session_data, f, indent=2)
        
    return session_file, len(steps)

import random

print("🚀 Starting SIMULATED Data Collection Run...")
generator = TaskGenerator()
# Inject mock fetcher to avoid network issues
class MockFetcher:
    def get_trending_topics(self, limit=1): return ["Artificial Intelligence 2026"]
generator.topic_fetcher = MockFetcher()

# Generate one task
task = generator.generate_task()
print(f"\n📝 Generated Task: {task['description']}")

# Execute simulation
print("⚡ Executing (Simulated)...")
json_path, actions = simulate_execution(task['description'])

print(f"\n✅ Simulation Complete!")
print(f"📁 Log saved to: {json_path}")
print(f"📸 Screenshots saved: {actions} images in {SCREENSHOT_DIR}")
print("\nSample Log Content:")
os.system(f"head -n 20 {json_path}")
