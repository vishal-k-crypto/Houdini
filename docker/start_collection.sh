#!/bin/bash
# start_collection.sh

echo "📦 Starting Automated Data Collection Container"

# Start virtual display (Clean up locks first to prevent "Server already active" errors)
echo "🧹 Cleaning up Xvfb locks..."
rm -f /tmp/.X99-lock
rm -f /tmp/.X11-unix/X99

echo "📺 Starting Xvfb..."
# -ac disables access control (IMPORTANT for docker/headless reliability)
Xvfb :99 -ac -screen 0 1920x1080x24 > /dev/null 2>&1 &
export DISPLAY=:99
sleep 2

# Start window manager (important for focus)
echo "🖼️  Starting Openbox..."
openbox &

# Start VNC server (optional debugging)
echo "📡 Starting VNC Server (Password: headless)..."
mkdir -p /root/.vnc
# Create dummy Xauthority explicitly
touch /root/.Xauthority
export XAUTHORITY=/root/.Xauthority
echo "🔧 Created .Xauthority at $XAUTHORITY"
ls -la /root/.Xauthority

x11vnc -storepasswd headless /root/.vnc/passwd
x11vnc -display :99 -forever -usepw -shared -rfbport 5900 -bg

echo "🤖 Starting Auto-Collector Loop..."
# Run the collector as a module
# Use unbuffered output to see logs immediately
python3 -u -m src.data_collection.auto_collector --interval 5
