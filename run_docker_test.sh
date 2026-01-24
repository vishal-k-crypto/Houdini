#!/bin/bash
# Wait for Docker to be ready and run test

echo "🐳 Checking Docker status..."

# Wait up to 60 seconds for Docker to start
for i in {1..12}; do
    if docker info > /dev/null 2>&1; then
        echo "✅ Docker is ready!"
        break
    fi
    echo "⏳ Waiting for Docker to start... ($i/12)"
    sleep 5
done

# Check if Docker is ready
if ! docker info > /dev/null 2>&1; then
    echo ""
    echo "❌ Docker is not running after 60 seconds"
    echo ""
    echo "Please:"
    echo "  1. Open Docker Desktop manually"
    echo "  2. Wait for it to fully start (whale icon should be stable)"
    echo "  3. Run this script again"
    exit 1
fi

echo ""
echo "🏗️  Building Docker image (this may take a few minutes)..."
docker build -t houdini-agent . || {
    echo "❌ Build failed"
    exit 1
}

echo ""
echo "✅ Image built successfully!"
echo ""
echo "🧪 Running test task in Docker container..."
echo "   Task: Search Wikipedia for 'machine learning'"
echo ""

# Run test task
docker run -it --rm \
  -e DISPLAY=:99 \
  -e WORKER_ID=test-run \
  -v "$(pwd)/data:/app/data" \
  --shm-size=2gb \
  houdini-agent \
  python3 -m src.main "Search for machine learning on Wikipedia and read the first paragraph"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Task completed successfully!"
else
    echo "⚠️  Task exited with code $EXIT_CODE"
fi

echo ""
echo "📊 Analyzing generated data..."
python3 analyze_all_sessions.py

echo ""
echo "🎉 Test complete!"
echo ""
echo "To start automated 24/7 collection:"
echo "  docker compose up -d"
