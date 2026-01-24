FROM ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-tk \
    python3-dev \
    xvfb \
    x11vnc \
    xdotool \
    wmctrl \
    scrot \
    imagemagick \
    wget \
    curl \
    git \
    openbox \
    x11-utils \
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

# Install Chromium browser (package name varies by Ubuntu version)
RUN apt-get update && (apt-get install -y chromium-browser || apt-get install -y chromium) \
    && rm -rf /var/lib/apt/lists/*

# Install LibreOffice Impress (for presentation tasks)
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress \
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

# Install TinyClick dependencies for vision-based UI automation
# This enables element detection via Samsung's Florence-2 model
RUN pip3 install --no-cache-dir transformers==4.48.0 torch accelerate einops timm

# Copy application code
COPY . /app/

# Pre-download TinyClick model (Florence-2) to avoid runtime delays
# This caches the model in the Docker image
RUN python3 -c "from transformers import AutoProcessor, AutoModelForCausalLM; \
    import os; \
    cache_dir = os.path.expanduser('~/.cache/houdini/tinyclick'); \
    os.makedirs(cache_dir, exist_ok=True); \
    print('Downloading TinyClick model...'); \
    AutoProcessor.from_pretrained('Krystianz/TinyClick', cache_dir=cache_dir, trust_remote_code=True); \
    AutoModelForCausalLM.from_pretrained('Krystianz/TinyClick', cache_dir=cache_dir, trust_remote_code=True); \
    print('TinyClick model cached successfully')" || echo "Warning: TinyClick model download failed, will retry at runtime"

# Create data directories (including training_sessions for excellent quality data)
RUN mkdir -p /app/data/screenshots /app/data/replay_sessions /app/data/training_sessions

# Copy and set entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-m", "src.auto_collector"]
