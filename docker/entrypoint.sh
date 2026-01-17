#!/bin/bash
set -e

echo "🚀 Starting Houdini Agent in Docker..."

# Start virtual display
echo "📺 Starting Xvfb on display $DISPLAY..."
Xvfb $DISPLAY -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} &
XVFB_PID=$!

# Wait for Xvfb to be ready
sleep 2

# Optional: Start VNC server for debugging (accessible on port 5900)
if [ "$ENABLE_VNC" = "true" ]; then
    echo "🔍 Starting VNC server on port 5900..."
    x11vnc -display $DISPLAY -forever -shared -rfbport 5900 -bg
fi

# Start window manager (needed for some apps)
echo "🪟 Starting window manager..."
openbox &

# Verify display is working
echo "✓ Display verification..."
xdpyinfo -display $DISPLAY >/dev/null 2>&1 || {
    echo "❌ Xvfb failed to start properly"
    exit 1
}

echo "✅ Docker environment ready!"
echo "   Display: $DISPLAY"
echo "   Resolution: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo "   Worker ID: ${WORKER_ID:-default}"

# Start the automation based on mode
if [ "$AUTO_MODE" = "true" ]; then
    echo "🤖 Starting in AUTO MODE (continuous task execution)..."
    python3 -m src.auto_collector
else
    echo "💻 Starting in MANUAL MODE..."
    # Keep container running for manual commands
    tail -f /dev/null
fi
