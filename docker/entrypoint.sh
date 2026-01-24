#!/bin/bash
set -e

echo "🚀 Starting Houdini Agent in Docker..."

# Clean up any stale Xvfb lock files
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

# Start virtual display
echo "📺 Starting Xvfb on display $DISPLAY..."
Xvfb $DISPLAY -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} &
XVFB_PID=$!
touch /root/.Xauthority

# Wait for Xvfb to be ready with retry
echo "⏳ Waiting for Xvfb to initialize..."
max_retries=10
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if [ -e "/tmp/.X11-unix/X${DISPLAY#:}" ] || [ -e "/tmp/.X99-lock" ]; then
        echo "✓ Xvfb socket detected"
        break
    fi
    sleep 1
    retry_count=$((retry_count + 1))
    echo "   Waiting... ($retry_count/$max_retries)"
done

if [ $retry_count -eq $max_retries ]; then
    echo "⚠️ Xvfb socket not detected, attempting to continue anyway..."
fi

# Optional: Start VNC server for debugging
if [ "$ENABLE_VNC" = "true" ]; then
    echo "🔍 Starting VNC server on port 5900..."
    x11vnc -display $DISPLAY -forever -shared -rfbport 5900 -bg
fi

# Start window manager
echo "🪟 Starting window manager..."
openbox &
sleep 1

# Verify display is working using a simple test
echo "✓ Display verification..."
export DISPLAY=$DISPLAY
if command -v xdpyinfo &>/dev/null; then
    xdpyinfo -display $DISPLAY >/dev/null 2>&1 || echo "⚠️ xdpyinfo check failed (non-fatal)"
fi

# Check if Xvfb process is running
if kill -0 $XVFB_PID 2>/dev/null; then
    echo "✓ Xvfb process is running (PID: $XVFB_PID)"
else
    echo "❌ Xvfb process died unexpectedly"
    exit 1
fi

echo "✅ Docker environment ready!"
echo "   Display: $DISPLAY"
echo "   Resolution: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}"
echo "   Worker ID: ${WORKER_ID:-default}"

# Verify screenshot capture works
echo "📸 Verifying screenshot capture..."
sleep 1  # Give display time to settle
if scrot /tmp/test_screenshot.png 2>/dev/null; then
    rm /tmp/test_screenshot.png
    echo "✓ Screenshot capture working (scrot)"
else
    echo "⚠️ scrot screenshot failed, will use pyautogui fallback"
fi

# Execute the command passed to docker run
exec "$@"
