# Automated Data Collection - Quick Start Guide

## 🚀 Get Started in 5 Minutes

### Prerequisites
- Docker installed
- Docker Compose installed
- 4GB+ RAM available

### Option 1: Quick Test (Single Container)

```bash
# Build the Docker image
docker build -t houdini-agent .

# Run a single worker
docker run -it --rm \
  -e AUTO_MODE=true \
  -e WORKER_ID=test-worker \
  -v $(pwd)/data:/app/data \
  --shm-size=2gb \
  houdini-agent
```

### Option 2: Full Setup (Multiple Workers)

```bash
# Start all services (3 workers + Redis)
docker-compose up -d

# View logs
docker-compose logs -f

# Scale to 5 workers
docker-compose up -d --scale agent=5

# Check status
docker-compose ps

# Stop everything
docker-compose down
```

### Option 3: Debug Mode (with VNC)

```bash
# Start debug worker with VNC
docker-compose --profile debug up agent-debug

# Connect with VNC viewer
# Address: localhost:5900
# You can see the screen in real-time!
```

## 📊 Monitor Progress

### Check Generated Data

```bash
# Count replay sessions
ls -1 data/replay_sessions/*.json | wc -l

# Count screenshots
find data/screenshots -name "*.png" | wc -l

# Check stats
cat data/auto_collector_stats_*.jsonl | tail -20

# Analyze quality
python3 analyze_all_sessions.py
```

### View Real-Time Stats

```bash
# Connect to Redis
docker exec -it houdini-redis redis-cli

# Get worker counters
KEYS counter:*
GET counter:worker-1:total
GET counter:worker-1:success
```

## 🎯 Expected Output

After running for:

**1 Hour:** 10-20 tasks completed
**1 Day:** 200-400 tasks completed  
**1 Week:** 1,500-3,000 tasks completed
**1 Month:** 6,000-12,000 tasks completed

(At ~15-20 tasks/hour per worker with 3 workers)

## 🔧 Configuration

Edit `docker-compose.yml` to customize:

```yaml
environment:
  - AUTO_MODE=true              # Auto-execution on/off
  - SCREEN_WIDTH=1920          # Screen resolution
  - SCREEN_HEIGHT=1080
  - WORKER_ID=worker-${WORKER_NUM:-1}

deploy:
  replicas: 5                   # Number of parallel workers
```

## 📈 Scaling Up

### Local Machine (3-5 workers)
```bash
docker-compose up -d --scale agent=5
```

### Multiple Machines
Run docker-compose on multiple computers, all pointing to same Redis:

```yaml
environment:
  - REDIS_URL=redis://MAIN_COMPUTER_IP:6379
```

### Cloud (AWS/GCP)
Deploy to cloud with Kubernetes for massive scale (50+ workers).

## 🛠 Troubleshooting

### Workers not starting?
```bash
# Check logs
docker-compose logs agent

# Verify Xvfb is running
docker exec houdini-agent-1 ps aux | grep Xvfb
```

### Low success rate?
```bash
# Check task difficulty distribution
python3 -c "
import json
from pathlib import Path

sessions = Path('data/replay_sessions').glob('*.json')
successes = sum(1 for s in sessions if json.load(open(s)).get('success'))
total = len(list(Path('data/replay_sessions').glob('*.json')))
print(f'Success rate: {successes}/{total} ({successes/total*100:.1f}%)')
"
```

### Out of disk space?
```bash
# Compress old screenshots
find data/screenshots -name "*.png" -mtime +7 -exec gzip {} \;

# Archive old sessions
tar -czf replay_sessions_backup.tar.gz data/replay_sessions/*.json
rm data/replay_sessions/*.json
```

## 🎉 Success Indicators

You'll know it's working when you see:
- ✅ New files in `data/replay_sessions/` every few minutes
- ✅ Screenshots accumulating in `data/screenshots/`
- ✅ Success rate >60%
- ✅ CPU usage 50-80% (normal for automation)
- ✅ Diverse task categories in logs

## 💡 Tips

1. **Start small:** 1-2 workers first, monitor quality
2. **Watch the first hour:** Make sure tasks are working
3. **Check diversity:** Ensure variety in generated tasks
4. **Adjust templates:** Edit `src/auto_collector.py` to add more tasks
5. **Balance success rate:** 60-80% is ideal (too high = too easy)

## 🚨 Important Notes

- **Docker needs GUI support:** Xvfb provides virtual display
- **Memory usage:** ~500MB-1GB per worker
- **Network:** Tasks will make real web requests
- **Ethics:** Respect robots.txt and rate limits
- **Privacy:** No personal data in automated tasks

## 📚 Next Steps

Once you have 5,000-10,000 tasks:
1. Run quality analysis: `python3 analyze_all_sessions.py`
2. Filter high-quality data
3. Start training your executor model!
4. See [AUTOMATED_DATA_COLLECTION.md](AUTOMATED_DATA_COLLECTION.md) for full details
