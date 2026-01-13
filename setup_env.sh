#!/bin/bash
set -e

echo "🚀 Setting up Houdini Agent environment..."

# 1. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "✅ Virtual environment already exists."
fi

# 2. Upgrade pip
echo "⬆️  Upgrading pip..."
./.venv/bin/pip install --upgrade pip

# 3. Install dependencies
echo "📥 Installing dependencies from requirements.txt..."
./.venv/bin/pip install -r requirements.txt

# 4. Install Playwright browsers (if needed)
echo "🌍 Installing Playwright browsers..."
./.venv/bin/playwright install chromium

echo "
✅ Setup complete!

To run the agent, use:
  ./.venv/bin/python -m src.main --task \"Your task\"

Or activate the environment first:
  source .venv/bin/activate
  python -m src.main --task \"Your task\"
"
