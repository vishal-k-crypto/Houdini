#!/bin/bash
# Test script for Docker-based data collection

echo "🚀 Testing Docker-based data collection system"
echo "=============================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

echo "✓ Docker is running"

# Build the image
echo ""
echo "📦 Building Docker image..."
docker build -t houdini-agent . || {
    echo "❌ Docker build failed"
    exit 1
}

echo "✓ Image built successfully"

# Test with a legal task
echo ""
echo "🧪 Running test task in Docker..."
echo "   Task: Search for Python tutorials on YouTube"
echo ""

# Run single task in Docker
docker run -it --rm \
  -e DISPLAY=:99 \
  -e WORKER_ID=test-worker \
  -v $(pwd)/data:/app/data \
  --shm-size=2gb \
  houdini-agent \
  python3 -m src.main "Search for Python programming tutorials on YouTube and watch the first result for 10 seconds"

echo ""
echo "✅ Test completed!"
echo ""
echo "📊 Checking generated data..."

# Find the most recent session
LATEST_SESSION=$(ls -t data/replay_sessions/*.json | head -1)

if [ -f "$LATEST_SESSION" ]; then
    echo "✓ Found replay session: $(basename $LATEST_SESSION)"
    
    # Analyze it
    python3 -c "
import json
import sys

with open('$LATEST_SESSION') as f:
    data = json.load(f)

total_events = len(data['events'])
actions = [e for e in data['events'] if e['event_type'] == 'action_start']
screenshots = sum(1 for e in data['events'] if e.get('screenshot_path'))

print(f'\n📈 Data Quality Report:')
print(f'   Total events: {total_events}')
print(f'   Actions: {len(actions)}')
print(f'   Screenshots: {screenshots}')
print(f'   Screenshot coverage: {screenshots/len(actions)*100 if actions else 0:.1f}%')
print(f'   Success: {data.get(\"success\")}')
print(f'   Duration: {data[\"events\"][-1][\"relative_ms\"]/1000:.1f}s')

if screenshots == 0:
    print('\n⚠️  WARNING: No screenshots captured!')
    print('   Check Docker Xvfb configuration')
    sys.exit(1)
elif screenshots/len(actions) < 0.8 if actions else False:
    print(f'\n⚠️  WARNING: Low screenshot coverage ({screenshots}/{len(actions)})')
    sys.exit(1)
else:
    print('\n✅ Data quality looks good!')
"
else
    echo "❌ No replay session found"
    exit 1
fi

echo ""
echo "🎉 Docker test successful!"
echo ""
echo "Next steps:"
echo "  1. Check data/replay_sessions/ for the session file"
echo "  2. Check data/screenshots/ for captured images"
echo "  3. Run: python3 analyze_data_quality.py"
echo "  4. If quality is good, start automated collection:"
echo "     docker-compose up -d"
