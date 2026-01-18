#!/bin/bash
# run_auto_collector.sh

# Name of the container and image
IMAGE_NAME="houdini-collector"
CONTAINER_NAME="houdini-collector-instance"

echo "🚀 Setting up Automated Data Collector..."

# 1. Build Image
echo "🏗️  Building Docker image ($IMAGE_NAME)..."
docker build -t $IMAGE_NAME . || {
    echo "❌ Build failed"
    exit 1
}

# 2. Stop existing container if running
if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo "🛑 Stopping existing container..."
    docker stop $CONTAINER_NAME
    docker rm $CONTAINER_NAME
fi

# 3. Create data directory if missing
mkdir -p data/training_sessions
mkdir -p data/screenshots

# 4. Run Container
echo "🏃 Starting Collector 24/7..."
echo "   Logs check: docker logs -f $CONTAINER_NAME"
echo "   Data saved to: $(pwd)/data/training_sessions"

# Run the container (with restarting policy)
# Mounts:
# - src: so code changes apply immediately
# - data: so we can see logs and data on host
# - docker: so script changes apply immediately (Fix for stale start_collection.sh)
echo "🚀 Starting container..."
docker run -d \
    --name $CONTAINER_NAME \
    --restart always \
    -e DISPLAY=:99 \
    -e OLLAMA_HOST=host.docker.internal:11434 \
    -e XAUTHORITY=/root/.Xauthority \
    --add-host=host.docker.internal:host-gateway \
    -v "$(pwd)/data:/app/data" \
    -v "$(pwd)/src:/app/src" \
    -v "$(pwd)/docker:/app/docker" \
    --shm-size=2gb \
    --entrypoint /app/docker/start_collection.sh \
    $IMAGE_NAME

echo "✅ Collector started! Logs:"
echo "docker logs -f $CONTAINER_NAME"
echo "   To view live logs: tail -f data/collection.log (if mapped) or docker logs -f $CONTAINER_NAME"
