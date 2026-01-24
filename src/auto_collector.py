#!/usr/bin/env python3
"""
Automated task collector - generates and executes tasks 24/7.
Focused on PPT Generation, Research, and Visual Asset Collection.
"""

import os
import sys
import time
import random
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional
import redis
import json
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LiveTopicFetcher:
    """Fetches real-time trending topics from the web."""
    
    def __init__(self):
        self.cached_topics = []
        self.last_fetch = 0
        self.cache_duration = 3600  # 1 hour
        
        # Fallback topics if fetch fails
        self.fallback_topics = [
            "Artificial Intelligence", "Climate Policy 2026", "Quantum Computing",
            "SpaceX Starship", "Global Economic Outlook", "Mental Health in Tech",
            "Sustainable Architecture", "Electric Vehicle Battery Tech"
        ]

    def get_trending_topics(self, limit=5) -> List[str]:
        """Get trending topics, refreshing cache if needed."""
        if time.time() - self.last_fetch > self.cache_duration or not self.cached_topics:
            self._fetch_new_topics()
            
        if not self.cached_topics:
            return random.sample(self.fallback_topics, min(limit, len(self.fallback_topics)))
            
        return random.sample(self.cached_topics, min(limit, len(self.cached_topics)))

    def _fetch_new_topics(self):
        """Scrape trending topics from Wikipedia/Google Trends."""
        new_topics = []
        try:
            # Try Wikipedia Main Page "In the news"
            resp = requests.get("https://en.wikipedia.org/wiki/Main_Page", timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, 'html.parser')
                # ITN box
                itn_box = soup.find(id="mp-itn")
                if itn_box:
                    for link in itn_box.find_all('a'):
                        title = link.get('title')
                        if title and len(title) > 5 and "Wikipedia" not in title:
                            new_topics.append(title)
            
            # Deduplicate and clean
            self.cached_topics = list(set([t for t in new_topics if t]))
            self.last_fetch = time.time()
            logger.info(f"🌍 LiveTopicFetcher: Fetched {len(self.cached_topics)} new topics")
            
        except Exception as e:
            logger.warning(f"Failed to fetch live topics: {e}")

# Task templates by category - HYBRID CURRICULUM
TASK_TEMPLATES = {
    "research_deep": [
        "Research '{topic}'. Find 3 key statistics/facts from reliable sources (BBC, Reuters, TechCrunch) and save them to a text file named 'research_notes.txt'.",
        "Investigate 'History of {topic}'. Create a markdown file with a timeline of 5 major events.",
        "Compare '{topic}' vs its main competitor. Save a comparison table in a text file.",
    ],
    
    "visual_creation_libreoffice": [
        "Open LibreOffice Impress. Create a 3-slide presentation about '{topic}'. Slide 1: Title. Slide 2: Key Facts (bullet points). Slide 3: Conclusion.",
        "Open LibreOffice. Create a Title Slide for '{topic}' using a blue background style.",
        "Open LibreOffice. Create a slide and insert an image related to '{topic}' (search for one first if needed).",
    ],
    
    "visual_creation_web": [
        "Go to slides.new (Google Slides). Create a generic Title slide saying '{topic}' (skip login/signin if prompted, just use the interface if possible or fallback to researching if blocked).",
        "Go to canva.com (public demo/templates). Search for a '{topic}' presentation template and take a screenshot of the best one.",
    ],
    
    "ai_copilot_workflow": [
        "Go to Gamma.app (or similar AI deck generator). Generate a deck about '{topic}'. Once generated, take a screenshot of the outline.",
        "Use an AI tool (ChatGPT/Claude/Gamma) to write a 5-slide outline for '{topic}', then open LibreOffice and manually copy the titles into 5 blank slides.",
    ],
    
    "asset_collection": [
        "Find 3 high-resolution diagrams explaining '{topic}'. Save them to the 'Downloads' folder.",
        "Find a corporate logo associated with '{topic}' (transparent PNG) and save it.",
    ]
}

class TaskGenerator:
    """Generates diverse, realistic tasks using dynamic data."""
    
    def __init__(self):
        self.generated_count = 0
        self.topic_fetcher = LiveTopicFetcher()
        
    def generate_task(self, difficulty: Optional[str] = None) -> Dict:
        """Generate a single task with parameters."""
        
        # Select category
        category = random.choice(list(TASK_TEMPLATES.keys()))
        template = random.choice(TASK_TEMPLATES[category])
        
        # Get dynamic data
        topics = self.topic_fetcher.get_trending_topics(limit=1)
        topic = topics[0] if topics else "Technology Trends"
        
        # Fill in parameters
        task_description = template.replace("{topic}", topic)
        
        # Estimate difficulty
        if difficulty is None:
            difficulty = "hard" if "LibreOffice" in task_description or "Google Slides" in task_description else "medium"
        
        self.generated_count += 1
        
        return {
            "id": f"auto_{self.generated_count}_{int(time.time())}",
            "description": task_description,
            "category": category,
            "difficulty": difficulty,
            "params": {"topic": topic},
            "generated_at": datetime.now().isoformat(),
        }

class AutoCollector:
    """Main automation controller."""
    
    def __init__(self, training_mode: bool = True):
        self.worker_id = os.getenv("WORKER_ID", "worker-default")
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.generator = TaskGenerator()
        self.training_mode = training_mode  # Enable training mode for excellent data quality
        
        try:
            self.redis_client = redis.from_url(self.redis_url)
            self.redis_client.ping()
            logger.info(f"✓ Connected to Redis at {self.redis_url}")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Running in standalone mode.")
            self.redis_client = None
    
    def run_forever(self):
        """Main loop - generate and execute tasks continuously."""
        logger.info(f"🤖 Auto-collector starting (Worker: {self.worker_id})")
        logger.info(f"📸 Training Mode: {'ENABLED' if self.training_mode else 'DISABLED'}")
        
        iteration = 0
        while True:
            try:
                iteration += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"Iteration {iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                # Generate a task
                task = self.generator.generate_task()
                logger.info(f"📝 Generated task: {task['description']}")
                logger.info(f"   Category: {task['category']}")
                
                # Execute the task
                logger.info(f"🚀 Executing task...")
                result = self._execute_task(task)
                
                if result.get("success"):
                    logger.info(f"✅ Task completed successfully!")
                else:
                    logger.warning(f"⚠️  Task failed: {result.get('error', 'Unknown error')}")
                
                # Log stats
                self._log_stats(iteration, task, result)
                
                # Random delay between tasks
                delay = random.uniform(5, 15)
                logger.info(f"⏳ Waiting {delay:.1f}s before next task...")
                time.sleep(delay)
                
            except KeyboardInterrupt:
                logger.info("\n🛑 Stopping auto-collector...")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                time.sleep(30)
    
    def _execute_task(self, task: Dict) -> Dict:
        """Execute a task using the main agent."""
        from src.main import run_task_internal
        
        try:
            start_time = time.time()
            result = run_task_internal(task['description'], is_training=self.training_mode)
            duration = time.time() - start_time
            
            return {
                "success": result.get("success", False),
                "duration": duration,
                "error": result.get("error"),
                "session_id": result.get("session_id"),
            }
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "duration": 0,
            }
    
    def _log_stats(self, iteration: int, task: Dict, result: Dict):
        """Log statistics."""
        stats = {
            "iteration": iteration,
            "worker_id": self.worker_id,
            "timestamp": datetime.now().isoformat(),
            "task_id": task["id"],
            "category": task["category"],
            "difficulty": task["difficulty"],
            "success": result.get("success", False),
            "duration": result.get("duration", 0),
        }
        
        # Save to Redis if available
        if self.redis_client:
            try:
                key = f"stats:{self.worker_id}:{iteration}"
                self.redis_client.setex(key, 86400, json.dumps(stats))
                self.redis_client.incr(f"counter:{self.worker_id}:total")
                if stats["success"]:
                    self.redis_client.incr(f"counter:{self.worker_id}:success")
                else:
                    self.redis_client.incr(f"counter:{self.worker_id}:failed")
            except Exception as e:
                pass
        
        # Save to local file
        try:
            stats_file = f"data/auto_collector_stats_{self.worker_id}.jsonl"
            with open(stats_file, "a") as f:
                f.write(json.dumps(stats) + "\n")
        except Exception as e:
            pass

def main():
    """Entry point."""
    logger.info("🚀 Starting Automated Data Collector (PPT Specialization)")
    collector = AutoCollector(training_mode=True)
    collector.run_forever()

if __name__ == "__main__":
    main()
