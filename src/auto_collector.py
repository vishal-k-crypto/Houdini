#!/usr/bin/env python3
"""
Automated task collector - generates and executes tasks 24/7.
"""

import os
import sys
import time
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional
import redis
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Task templates by category
TASK_TEMPLATES = {
    "search_browse": [
        "Search for {topic} on Google",
        "Go to {website} and search for {query}",
        "Find information about {topic} on Wikipedia",
        "Browse {category} articles on {news_site}",
        "Look up {term} definition on dictionary.com",
    ],
    
    "download": [
        "Go to {site} and download {content}",
        "Download the {quality} version of {media_item}",
        "Find and download {resource_type} from {source}",
    ],
    
    "navigation": [
        "Navigate to the {section} section of {website}",
        "Scroll down on {website} until you find {target}",
        "Go to {website} home page",
        "Visit {url} and explore the main sections",
    ],
    
    "content": [
        "Read the article about {topic} on {news_site}",
        "Watch a video about {subject} on YouTube",
        "Listen to a podcast about {theme}",
    ],
    
    "social": [
        "Check {topic} on Reddit",
        "Browse {category} posts on {social_site}",
        "Look up {hashtag} on Twitter",
    ],
    
    "productivity": [
        "Look up weather forecast for {city}",
        "Search for {recipe} recipe",
        "Find {movie} showtimes near you",
        "Look up stock price for {company}",
    ],
}

# Data pools for parameterization
DATA_POOLS = {
    "topic": [
        "artificial intelligence", "climate change", "electric vehicles",
        "quantum computing", "space exploration", "renewable energy",
        "cryptocurrency", "machine learning", "robotics", "biotechnology",
        "virtual reality", "5G technology", "autonomous vehicles",
        "gene editing", "blockchain", "neural networks",
    ],
    
    "website": [
        "github.com", "stackoverflow.com", "wikipedia.org",
        "reddit.com", "medium.com", "dev.to", "arxiv.org",
    ],
    
    "news_site": [
        "bbc.com", "reuters.com", "theguardian.com",
        "npr.org", "apnews.com",
    ],
    
    "query": [
        "how to {skill}", "best {item} 2026", "{topic} explained",
        "tutorial for {subject}", "guide to {topic}",
    ],
    
    "quality": ["highest", "best", "HD", "1080p", "4K", "maximum"],
    
    "category": ["technology", "science", "business", "health", "sports"],
    
    "city": ["New York", "London", "Tokyo", "Paris", "Berlin", "Sydney"],
    
    "company": ["Apple", "Google", "Microsoft", "Amazon", "Tesla", "NVIDIA"],
}


class TaskGenerator:
    """Generates diverse, realistic tasks."""
    
    def __init__(self):
        self.generated_count = 0
        
    def generate_task(self, difficulty: Optional[str] = None) -> Dict:
        """Generate a single task with parameters."""
        
        # Select category
        category = random.choice(list(TASK_TEMPLATES.keys()))
        template = random.choice(TASK_TEMPLATES[category])
        
        # Extract placeholders from template
        placeholders = self._extract_placeholders(template)
        
        # Fill in parameters
        params = {}
        for placeholder in placeholders:
            if placeholder in DATA_POOLS:
                value = random.choice(DATA_POOLS[placeholder])
                # Handle nested placeholders
                if "{" in value:
                    nested = self._extract_placeholders(value)
                    for nested_ph in nested:
                        if nested_ph in DATA_POOLS:
                            value = value.replace(
                                f"{{{nested_ph}}}",
                                random.choice(DATA_POOLS[nested_ph])
                            )
                params[placeholder] = value
        
        # Generate final task description
        task_description = template.format(**params)
        
        # Estimate difficulty
        if difficulty is None:
            difficulty = self._estimate_difficulty(task_description, category)
        
        self.generated_count += 1
        
        return {
            "id": f"auto_{self.generated_count}_{int(time.time())}",
            "description": task_description,
            "category": category,
            "difficulty": difficulty,
            "params": params,
            "generated_at": datetime.now().isoformat(),
        }
    
    def _extract_placeholders(self, template: str) -> List[str]:
        """Extract {placeholder} names from template."""
        import re
        return re.findall(r'\{(\w+)\}', template)
    
    def _estimate_difficulty(self, task: str, category: str) -> str:
        """Estimate task difficulty."""
        # Simple heuristic
        word_count = len(task.split())
        
        if "download" in category or word_count > 15:
            return "hard"
        elif "search" in category or "browse" in category:
            return "easy"
        else:
            return "medium"
    
    def generate_batch(self, count: int = 10) -> List[Dict]:
        """Generate a batch of tasks."""
        return [self.generate_task() for _ in range(count)]


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
        if self.training_mode:
            logger.info(f"   → Screenshots before/after every action")
            logger.info(f"   → Data saved to: data/training_sessions/")
        
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
                logger.info(f"   Category: {task['category']}, Difficulty: {task['difficulty']}")
                
                # Execute the task
                logger.info(f"🚀 Executing task...")
                result = self._execute_task(task)
                
                if result.get("success"):
                    logger.info(f"✅ Task completed successfully!")
                else:
                    logger.warning(f"⚠️  Task failed: {result.get('error', 'Unknown error')}")
                
                # Log stats
                self._log_stats(iteration, task, result)
                
                # Random delay between tasks (human-like)
                delay = random.uniform(5, 15)
                logger.info(f"⏳ Waiting {delay:.1f}s before next task...")
                time.sleep(delay)
                
            except KeyboardInterrupt:
                logger.info("\n🛑 Stopping auto-collector...")
                break
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                time.sleep(30)  # Wait before retrying
    
    def _execute_task(self, task: Dict) -> Dict:
        """Execute a task using the main agent."""
        from src.main import run_task_internal
        
        try:
            start_time = time.time()
            
            # Run the task in TRAINING MODE for excellent data quality
            # This captures screenshots before/after every action
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
        """Log statistics to Redis (if available) and local file."""
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
                self.redis_client.setex(key, 86400, json.dumps(stats))  # Keep for 24h
                
                # Increment counters
                self.redis_client.incr(f"counter:{self.worker_id}:total")
                if stats["success"]:
                    self.redis_client.incr(f"counter:{self.worker_id}:success")
                else:
                    self.redis_client.incr(f"counter:{self.worker_id}:failed")
            except Exception as e:
                logger.debug(f"Could not save stats to Redis: {e}")
        
        # Save to local file
        try:
            stats_file = f"data/auto_collector_stats_{self.worker_id}.jsonl"
            with open(stats_file, "a") as f:
                f.write(json.dumps(stats) + "\n")
        except Exception as e:
            logger.debug(f"Could not save stats to file: {e}")


def main():
    """Entry point."""
    logger.info("🚀 Starting Automated Data Collector")
    logger.info(f"   Worker ID: {os.getenv('WORKER_ID', 'default')}")
    logger.info(f"   Display: {os.getenv('DISPLAY', 'not set')}")
    logger.info(f"   Training Mode: ENABLED (excellent data quality)")
    logger.info(f"   Data saved to: data/training_sessions/")
    
    # Training mode = True for excellent data quality:
    # - Screenshots before/after every action (200% coverage)
    # - Only successful sessions saved
    # - Data saved to training_sessions folder
    collector = AutoCollector(training_mode=True)
    collector.run_forever()


if __name__ == "__main__":
    main()
