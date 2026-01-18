"""
Automated Data Collection Loop
=============================
Runs an infinite loop of:
1. Generating diverse web tasks using an LLM
2. Executing them using the Houdini Agent (with --train flag)
3. Determining success/failure and logging results

Usage:
    python3 -m src.data_collection.auto_collector
"""
import time
import random
import logging
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Optional

from ..utils.ollama_client import OllamaClient
from ..main import run_task_internal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/collection.log")
    ]
)
logger = logging.getLogger("auto_collector")

# Task categories to rotate through for diversity
TASK_CATEGORIES = [
    "complex_research_comparison",
    "travel_planning_multistep",
    "technical_troubleshooting",
    "market_analysis",
    "content_verification",
    "informational_search",
    "navigational_search",
    "video_playback"
]

class TaskGenerator:
    """Generates varied tasks using Ollama."""
    
    def __init__(self, client: OllamaClient):
        self.client = client
        self.history: List[str] = []
        
    def generate_task(self, category: str) -> str:
        """Generate a single solvable task for the given category."""
        
        system_prompt = """You are an Advanced Synthetic Task Generator for training a high-capabilities web agent.
Your goal is to create COMPLEX, REAL-WORLD, and MULTI-STEP web browsing tasks that mimic actual human workflows.

The agent is capable of:
- Complex navigation across multiple sites
- Extracting and comparing information
- Reading documentation and applying fixes
- Watching specific content parts

LIMITATIONS:
- No solving CAPTCHAs
- No logging in (assume public access)

CRITICAL INSTRUCTION:
- Move beyond simple "find X" tasks. 
- Create scenarios involving COMPARISON, ANALYSIS, or SPECIFIC CONSTRAINTS.
- Example: "Compare the specs of iPhone 15 vs S24 on GSMArena and find which has better battery life"
- Example: "Find a vegan pasta recipe on AllRecipes that takes under 30 mins and list the main ingredients"

Output ONLY the task description string."""

        category_prompts = {
            "complex_research_comparison": "Generate a task that requires comparing two or more items/concepts across one or more websites. Example: 'Go to rtings.com and compare the color accuracy of LG C3 vs Sony A95L'",
            "travel_planning_multistep": "Generate a task involving travel research (flights, hotels, things to do) with specific constraints. Example: 'Find the top rated 3-star hotel in Tokyo near Shibuya crossing on TripAdvisor'",
            "technical_troubleshooting": "Generate a task to find a fix for a specific technical error. Example: 'Search StackOverflow for python ImportError: No module named rich and find the most upvoted solution'",
            "market_analysis": "Generate a task to analyze trends or prices. Example: 'Go to CoinMarketCap and find the top gaining crypto token in the last 24h other than Bitcoin'",
            "content_verification": "Generate a task to verify a claim or find a source. Example: 'Go to Snopes.com and check if the recent rumor about X is true'",
            "informational_search": "Generate a task to find deep specific details. Example: 'Find the release date of the next LTS version of Ubuntu and its main features'",
            "navigational_search": "Generate a complex navigation task. Example: 'Go to the OpenAI API documentation, find the section on Audio generation, and check the price per minute'",
            "video_playback": "Generate a specific video task. Example: 'Find a review of the latest MacBook Air M3 on YouTube and watch the segment about battery life'"
        }
        
        prompt = f"""Generate a unique task for the category: {category}.
{category_prompts.get(category, "Generate a simple web browsing task.")}

Ensure it is DIFFERENT from these previous tasks:
{', '.join(self.history[-5:])}

Task Description:"""

        try:
            task = self.client.generate(prompt, system_prompt=system_prompt, temperature=0.9).strip()
            # Cleanup common LLM artifacts
            clean_task = task.replace('"', '').replace("Task Description:", "").strip()
            
            self.history.append(clean_task)
            if len(self.history) > 20:
                self.history.pop(0)
                
            return clean_task
        except Exception as e:
            logger.error(f"Failed to generate task: {e}")
            return f"Search for {category} on Google"

class AutoCollector:
    """Main loop for automated data collection."""
    
    def __init__(self, limit: int = 0, interval: int = 10):
        self.client = OllamaClient()
        self.generator = TaskGenerator(self.client)
        self.limit = limit
        self.interval = interval
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0
        }
        
    def run(self):
        """Start the infinite collection loop."""
        logger.info(f"🚀 Starting Auto-Collector (Limit: {self.limit if self.limit > 0 else 'Infinite'})")
        
        while True:
            try:
                # 1. Select Category
                category = random.choice(TASK_CATEGORIES)
                
                # 2. Generate Task
                logger.info(f"🎲 Generating task for category: {category}...")
                task = self.generator.generate_task(category)
                logger.info(f"📋 Task: {task}")
                
                # 3. Execute Task
                logger.info("▶️ Executing task...")
                start_time = time.time()
                
                # Run the agent (internal call effectively does the same as main.py --train)
                # We use main.run_task_internal but we need to ensure it uses the TRAIN mode logic
                # run_task_internal creates a coordinator. We need to pass is_training=True to it.
                # However, run_task_internal signature in main.py currently is simpler.
                # I'll directly instantiate logic here to control it better or update run_task_internal.
                # For now let's import the specific pieces to ensure we get the training flag in.
                
                from ..loop.adaptive_coordinator import AdaptiveLoopCoordinator
                
                coordinator = AdaptiveLoopCoordinator(
                    client=self.client,
                    enable_thinking_window=False, # No GUI in docker usually, or optional
                    max_iterations=50
                )
                
                # Pass is_training=True for data collection
                result = coordinator.execute(task, is_training=True)
                
                duration = time.time() - start_time
                success = result.get("success", False)
                
                # 4. Update Stats
                self.stats["total"] += 1
                if success:
                    self.stats["success"] += 1
                    logger.info(f"✅ Task Success ({duration:.1f}s)")
                else:
                    self.stats["failed"] += 1
                    logger.error(f"❌ Task Failed ({duration:.1f}s): {result.get('error')}")
                
                logger.info(f"📊 Stats: {self.stats['success']}/{self.stats['total']} ({self.stats['success']/self.stats['total']*100:.1f}%)")
                
                # Check limits
                if self.limit > 0 and self.stats["total"] >= self.limit:
                    logger.info("🛑 Reached execution limit. Stopping.")
                    break
                
                # Wait before next task
                logger.info(f"⏳ Waiting {self.interval}s...")
                time.sleep(self.interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Stopped by user.")
                break
            except Exception as e:
                logger.error(f"⚠️ Critical Collector Error: {e}", exc_info=True)
                time.sleep(30) # Backoff on crash

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Data Collector")
    parser.add_argument("--limit", type=int, default=0, help="Max tasks to run (0=infinite)")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between tasks")
    args = parser.parse_args()
    
    collector = AutoCollector(limit=args.limit, interval=args.interval)
    collector.run()
