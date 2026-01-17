# Automated Data Collection System

## Overview
Automated 24/7 task execution in Docker for ML training data generation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Task Generator                           │
│  - Templates (search, download, form-fill, navigation)      │
│  - Real data sources (trending topics, common queries)      │
│  - Parameterized variations                                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 Task Queue (Redis/RabbitMQ)                 │
│  - Priority queue (easy → hard)                             │
│  - Deduplication                                            │
│  - Load balancing                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Docker Swarm / Kubernetes                      │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Container 1 │  │  Container 2 │  │  Container N │     │
│  │              │  │              │  │              │     │
│  │  - Xvfb      │  │  - Xvfb      │  │  - Xvfb      │     │
│  │  - Browser   │  │  - Browser   │  │  - Browser   │     │
│  │  - Agent     │  │  - Agent     │  │  - Agent     │     │
│  │  - Screen    │  │  - Screen    │  │  - Screen    │     │
│  │    Capture   │  │    Capture   │  │    Capture   │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │             │
└─────────┼─────────────────┼─────────────────┼─────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Centralized Storage (S3/MinIO)                 │
│  - Replay sessions (JSON)                                   │
│  - Screenshots (PNG)                                        │
│  - Metadata & metrics                                       │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│              Quality Control & Analysis                     │
│  - Success rate tracking                                    │
│  - Diversity metrics                                        │
│  - Automated filtering                                      │
│  - Data augmentation                                        │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Proof of Concept (1 week)
**Goal:** Single Docker container running tasks

- [ ] Create Dockerfile with GUI support
- [ ] Implement basic task generator (10 templates)
- [ ] Test screenshot capture in Docker
- [ ] Run 100 tasks successfully
- [ ] Verify data quality

**Expected output:** 100-500 tasks, ~60% success rate

### Phase 2: Task Variety (1 week)
**Goal:** Diverse, realistic tasks

- [ ] 50+ task templates
- [ ] Integration with real data sources:
  - Google Trends API (trending searches)
  - Reddit r/all (popular topics)
  - News headlines (current events)
  - Common web workflows
- [ ] Parameterized variations (different sites, queries, etc)
- [ ] Difficulty levels (easy → hard)

**Expected output:** 1,000-2,000 diverse tasks

### Phase 3: Parallel Execution (1 week)
**Goal:** Scale to multiple containers

- [ ] Docker Compose setup (5-10 containers)
- [ ] Task queue (Redis)
- [ ] Resource management
- [ ] Centralized logging
- [ ] Health monitoring

**Expected output:** 5,000-10,000 tasks/week

### Phase 4: Production (2 weeks)
**Goal:** 24/7 operation

- [ ] Kubernetes deployment
- [ ] Auto-scaling (based on queue depth)
- [ ] Error recovery & retry logic
- [ ] Data quality checks
- [ ] Storage optimization (compression)
- [ ] Cost monitoring

**Expected output:** 50,000+ tasks/month

## Task Templates

### Template Categories:

1. **Search & Browse** (30%)
   - "Search for {topic} on {search_engine}"
   - "Go to {website} and find information about {topic}"
   - "Browse {category} on {ecommerce_site}"

2. **Content Consumption** (20%)
   - "Watch the first minute of {video_topic} on YouTube"
   - "Read the article about {topic} on {news_site}"
   - "Listen to {podcast} on {platform}"

3. **Downloads** (15%)
   - "Download {file_type} from {source}"
   - "Save {content} to computer"
   - "Export {data} as {format}"

4. **Navigation** (15%)
   - "Navigate to {section} on {website}"
   - "Find the {page_type} page on {domain}"
   - "Scroll to {element} on current page"

5. **Forms & Interaction** (10%)
   - "Fill out contact form with dummy data"
   - "Subscribe to newsletter on {website}"
   - "Create account on {platform}" (use temp emails)

6. **Multi-step Workflows** (10%)
   - "Search for {product}, compare prices, open cheapest"
   - "Find {recipe}, view ingredients, check nutrition"
   - "Look up {movie}, watch trailer, read reviews"

### Task Generator Example:

```python
import random
from datetime import datetime

TEMPLATES = {
    "search_browse": [
        "Search for {topic} on Google",
        "Go to {website} and search for {query}",
        "Find information about {topic} on Wikipedia",
    ],
    "download": [
        "Go to {site} and download {content}",
        "Download the {quality} version of {media}",
    ],
    "navigation": [
        "Navigate to the {section} section of {website}",
        "Scroll down on {website} until you find {target}",
    ]
}

DATA_SOURCES = {
    "trending_topics": ["AI", "climate change", "electric vehicles", "quantum computing"],
    "websites": ["reddit.com", "github.com", "stackoverflow.com", "wikipedia.org"],
    "qualities": ["highest", "best", "4K", "1080p", "HD"],
}

def generate_task():
    category = random.choice(list(TEMPLATES.keys()))
    template = random.choice(TEMPLATES[category])
    
    # Fill in parameters
    task = template.format(
        topic=random.choice(DATA_SOURCES["trending_topics"]),
        website=random.choice(DATA_SOURCES["websites"]),
        quality=random.choice(DATA_SOURCES["qualities"]),
        # ... more parameters
    )
    
    return {
        "task": task,
        "category": category,
        "difficulty": estimate_difficulty(task),
        "timestamp": datetime.now().isoformat(),
    }
```

## Docker Setup

### Dockerfile:

```dockerfile
FROM ubuntu:22.04

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    xvfb x11vnc \
    chromium-browser chromium-chromedriver \
    firefox geckodriver \
    xdotool wmctrl \
    scrot imagemagick \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt

# Copy agent code
COPY src/ /app/src/
COPY data/ /app/data/

# Setup virtual display
ENV DISPLAY=:99
ENV SCREEN_WIDTH=1920
ENV SCREEN_HEIGHT=1080
ENV SCREEN_DEPTH=24

# Create screenshots directory
RUN mkdir -p /app/data/screenshots /app/data/replay_sessions

# Entrypoint script
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/docker-entrypoint.sh"]
```

### docker-entrypoint.sh:

```bash
#!/bin/bash
set -e

# Start virtual display
Xvfb :99 -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} &
sleep 2

# Optional: Start VNC server for debugging
# x11vnc -display :99 -forever -shared &

# Start the agent
python3 -m src.main --auto-mode --docker

# Keep container running
tail -f /dev/null
```

### docker-compose.yml:

```yaml
version: '3.8'

services:
  task-queue:
    image: redis:alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  agent-worker:
    build: .
    depends_on:
      - task-queue
    environment:
      - REDIS_URL=redis://task-queue:6379
      - WORKER_ID=${WORKER_ID:-worker-1}
    volumes:
      - ./data:/app/data
      - shared-storage:/app/shared
    deploy:
      replicas: 5  # Run 5 parallel workers

  storage:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data

volumes:
  redis-data:
  minio-data:
  shared-storage:
```

## Cost Analysis

### Local Setup (Recommended Start):
- **Hardware:** Your existing computer
- **Containers:** 3-5 parallel workers
- **Cost:** $0 (electricity ~$5-10/month)
- **Output:** ~5,000-10,000 tasks/week

### Cloud Setup (Scale):
- **AWS EC2:** 5x t3.medium instances
- **Storage:** S3 (1TB)
- **Cost:** ~$200-300/month
- **Output:** ~50,000-100,000 tasks/month

### Optimal Hybrid:
- **Day:** Local (your computer idle time)
- **Night:** Cloud (AWS Spot instances)
- **Cost:** ~$50-100/month
- **Output:** ~20,000-40,000 tasks/month

## Data Quality Targets

### Diversity Metrics:
- ✓ **Websites:** 100+ unique domains
- ✓ **Task types:** 10+ categories
- ✓ **Success rate:** 60-80%
- ✓ **Action variety:** 15+ action types
- ✓ **Time of day:** 24-hour coverage

### Quality Filters:
1. **Too short:** <5 actions → discard
2. **Too long:** >100 actions → review
3. **No screenshots:** discard
4. **Crashes:** log for debugging
5. **Duplicates:** deduplicate by task hash

## Monitoring Dashboard

Track these metrics:
- Tasks/hour
- Success rate (overall & by category)
- Average task duration
- Screenshot capture rate
- Storage usage
- Error rates & types

## Realistic Timeline & Output

| Phase | Duration | Tasks Generated | Quality |
|-------|----------|-----------------|---------|
| POC | 1 week | 500 | 60% |
| Variety | 1 week | 2,000 | 65% |
| Parallel | 1 week | 10,000 | 70% |
| Production (1 month) | 4 weeks | 50,000 | 75% |
| **Total (2 months)** | **8 weeks** | **~100,000** | **70-75%** |

With quality filtering: **~70,000 high-quality tasks**

## Key Advantages of This Approach

1. **Diversity:** Random generation ensures wide coverage
2. **Scale:** 24/7 operation = fast data collection
3. **Cost:** Much cheaper than human annotators
4. **Control:** You own the infrastructure and data
5. **Iteration:** Can adjust templates based on results

## Potential Issues & Mitigations

| Issue | Mitigation |
|-------|-----------|
| Website blocks | Rotate User-Agents, use delays |
| Repetitive data | Increase template variety |
| Low quality | Implement stricter filters |
| Resource usage | Use spot instances, optimize storage |
| Model overfitting | Ensure diverse task distribution |

## Next Steps

1. **This Week:** Build POC Docker setup
2. **Next Week:** Generate 50 task templates
3. **Week 3:** Run 5,000 tasks locally
4. **Week 4:** Analyze data quality
5. **Month 2:** Scale to production

This approach is **highly viable** and could get you to production-quality training data in **2-3 months**! 🚀
