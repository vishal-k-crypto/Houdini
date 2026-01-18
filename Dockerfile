FROM ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    xvfb \
    x11vnc \
    chromium-browser \
    chromium-chromedriver \
    xdotool \
    wmctrl \
    scrot \
    imagemagick \
    wget \
    curl \
    git \
    openbox \
    fonts-liberation \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Setup virtual display
ENV DISPLAY=:99
ENV SCREEN_WIDTH=1920
ENV SCREEN_HEIGHT=1080
ENV SCREEN_DEPTH=24

# Install Python dependencies (use docker-specific requirements without macOS packages)
WORKDIR /app
COPY requirements-docker.txt .
RUN pip3 install --no-cache-dir -r requirements-docker.txt

# Install additional automation packages
RUN pip3 install --no-cache-dir redis fake-useragent requests beautifulsoup4 rich textual

# Copy application code
COPY . /app/

# Create data directories (including training_sessions for excellent quality data)
RUN mkdir -p /app/data/screenshots /app/data/replay_sessions /app/data/training_sessions

# Copy and set entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
