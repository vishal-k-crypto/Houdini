
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.auto_collector import TaskGenerator, LiveTopicFetcher

print("Testing LiveTopicFetcher...")
fetcher = LiveTopicFetcher()
topics = fetcher.get_trending_topics(limit=3)
print(f"Fetched topics: {topics}")

print("\nTesting TaskGenerator...")
generator = TaskGenerator()
# Inject fetcher to avoid fetching again if problematic in test env
generator.topic_fetcher = fetcher 

for i in range(5):
    task = generator.generate_task()
    print(f"\nTask {i+1}:")
    print(f"  Description: {task['description']}")
    print(f"  Category: {task['category']}")
    print(f"  Difficulty: {task['difficulty']}")

print("\nVerification Complete!")
