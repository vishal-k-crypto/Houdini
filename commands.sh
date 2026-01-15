#!/bin/bash
# Houdini Agent Commands
# Loop mode and supervisor enabled by default

# ============================================================
# SETUP (One-time)
# ============================================================

brew install ollama
ollama pull qwen2.5-coder:32b
pip install -r requirements.txt

# Note: If you see a google.generativeai deprecation warning,
# update the package:
# pip install --upgrade google-genai

# OmniParser V2 (OPTIONAL - for non-accessible apps like Adobe, Electron)
# Requires CUDA GPU for optimal performance (~0.8s vs ~5s on CPU)
# Step 1: Install dependencies
pip install torch ultralytics transformers huggingface-hub easyocr supervision

# Step 2: Download model weights (~2GB)
./scripts/download_omniparser.sh


# ============================================================
# USAGE
# ============================================================

# Activate environment
source .venv/bin/activate

# Run any task (uses new ADAPTIVE architecture by default)
# Now with PROBABILITY MODEL for flexible task execution:
# - Handles incomplete task specs (80-90% info provided)
# - Adjusts execution strategy based on task analysis
# - Uses dynamic match probability thresholds
python -m src.main --task "your task here"

# Use LangGraph architecture (NEW - with checkpointing & crash recovery)
python -m src.main --task "your task here" --langgraph

# LangGraph with persistent checkpoints (resume after crash)
python -m src.main --task "your task here" --langgraph --checkpoint-path data/checkpoints.db

# Resume a LangGraph execution from checkpoint
python -m src.main --task "your task here" --langgraph --checkpoint-path data/checkpoints.db --resume-thread <thread_id>

# LangGraph with human-in-the-loop approval
python -m src.main --task "your task here" --langgraph --human-approval

# Use legacy architecture (if needed)
python -m src.main --task "your task here" --legacy


# ============================================================
# EXAMPLES (Adaptive Architecture)
# ============================================================

python -m src.main --task "search for AI news"
python -m src.main --task "open YouTube and play latest MKBHD video"
python -m src.main --task "search for quantum physics"
python -m src.main --task "send a message to kushal saying hi on whatsapp"

# Image generation examples
python -m src.main --task "go to gemini.google.com, click Create image, and generate: sunset over mountains"
python -m src.main --task "navigate to specific-website.com and create an image with prompt: your prompt here"


# ============================================================
# CONTEXT-AWARE MEMORY EXAMPLES
# ============================================================

# After creating a file, the agent remembers its location:
python -m src.main --task "create quarterly report in Documents/Reports folder"

# Later, you can reference it naturally:
python -m src.main --task "send the report to John"
# → Agent knows: report = ~/Documents/Reports/quarterly_report.pdf

# The agent learns from every successful task and stores context in:
# data/context_memory/

# Test context memory:
python test_context_memory.py


# ============================================================
# ARCHITECTURE MODES
# ============================================================

# ADAPTIVE (default): Macro Planner → Micro Executor → Adaptive Supervisor
# - Planner gives high-level steps only
# - Executor generates micro cursor actions based on screen
# - Supervisor handles randomness, verifies completion, evolves task
python -m src.main --task "your task"

# LANGGRAPH (new): State Machine with built-in checkpointing
# - Same macro/micro/supervisor logic as adaptive
# - Built-in state management via LangGraph
# - Checkpointing for crash recovery
# - Human-in-the-loop support
# - Resume execution from any point
python -m src.main --task "your task" --langgraph

# LEGACY: Traditional Planner → Executor → Supervisor
python -m src.main --task "your task" --legacy


# ============================================================
# LANGGRAPH EXAMPLES (with checkpointing)
# ============================================================

# Basic LangGraph execution
python -m src.main --task "search for AI news" --langgraph

# With persistent checkpoints (survives crashes)
python -m src.main --task "complex multi-step task" \
    --langgraph \
    --checkpoint-path data/checkpoints.db

# Resume from checkpoint after interruption
python -m src.main --task "same task" \
    --langgraph \
    --checkpoint-path data/checkpoints.db \
    --resume-thread abc12345

# Human approval required at key points
python -m src.main --task "send important email" \
    --langgraph \
    --human-approval


# ============================================================
# MONITORING
# ============================================================

# View recent operations
cat data/executor_history.json | jq '.[-5:]'


# ============================================================
# TIME TRAVEL DEBUGGING (REPLAY MODE)
# ============================================================

# Enter replay mode - interactive session picker
python -m src.main --replay

# List all available replay sessions
python -m src.main --replay-list

# Replay a specific session by task ID
python -m src.main --replay-session <task_id>

# Replay sessions are automatically recorded during execution
# and saved to: data/replay_sessions/

# In replay mode, you can:
# - SPACE: play/pause
# - ←/→: seek backward/forward
# - ↑/↓: adjust playback speed
# - n/p: jump to next/previous marker
# - q: quit

# What you can see in replay:
# - Exact cursor positions and movements
# - AI thinking at each millisecond
# - Screenshots at checkpoints
# - Action timing and success/failure


# ============================================================
# TROUBLESHOOTING
# ============================================================

# Check Ollama
ollama list

# Restart Ollama
killall ollama && ollama serve

# Test setup
python test_ollama.py
