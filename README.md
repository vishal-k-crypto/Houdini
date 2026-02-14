<div align="center">

# 🤖 Houdini Agent

**AI-Powered macOS Automation with Self-Evolving Intelligence**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-black.svg)](https://www.apple.com/macos/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<p align="center">
  <strong>Automate complex tasks on macOS using local AI models with vision capabilities</strong>
</p>

[Features](#-features) • [Quick Start](#-quick-start) • [Installation](#-installation) • [Usage](#-usage) • [Architecture](#-architecture)

</div>

---

## 🎯 What is Houdini Agent?

Houdini Agent is an intelligent automation system for macOS that uses **local AI models** to:

- 👁️ **See** your screen using computer vision
- 🧠 **Plan** complex multi-step tasks
- 🖱️ **Execute** actions (click, type, scroll) like a human
- 📚 **Learn** from experience and improve over time
- 💭 **Think** out loud with a real-time reasoning window

Unlike cloud-based solutions, Houdini runs **entirely on your machine** — no data leaves your computer.

---

## ✨ Features

### 🧠 Multi-Agent Architecture
| Component | Model | Purpose |
|-----------|-------|---------|
| **Planner** | Ollama (Qwen 3 Coder) | Breaks tasks into executable steps |
| **Executor** | Local Vision + Accessibility | Performs screen actions |
| **Supervisor** | llama.cpp (Qwen 2.5 7B) | Validates and corrects actions |

### 🚀 Key Capabilities

- **🖥️ Screen Understanding** - Uses YOLO + OCR + OmniParser to understand any UI
- **⚡ Fast Execution** - Native macOS accessibility APIs for 10-100x speed
- **🧠 Self-Improving** - Learns from failures and adapts prompts automatically
- **💭 Thinking Window** - Real-time visualization of AI reasoning
- **📊 Replay & Debug** - Time-travel through execution history
- **🔒 Privacy-First** - All AI models run locally on your machine

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/houdini-agent.git
cd houdini-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Install Ollama (Required)

```bash
# macOS
brew install ollama

# Or download from https://ollama.ai
```

### 3. Pull Required Models

```bash
# Pull the planning model (recommended)
ollama pull qwen2.5-coder:14b

# Or use smaller model for faster inference
ollama pull qwen2.5-coder:7b
```

### 4. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your settings (optional)
# Most features work without any API keys!
```

### 5. Run Your First Task

```bash
# Basic task
python -m src.main --task "Open Calculator and calculate 15 * 23"

# With thinking window
python -m src.main --task "Open Safari and search for Python tutorials" --thinking-window

# Complex multi-step task
python -m src.main --task "Create a new note in Notes app with today's date and a shopping list"
```

---

## 📦 Installation

### Prerequisites

- **macOS 12+** (Monterey or later)
- **Python 3.10+**
- **Ollama** installed and running
- **Accessibility Permissions** (granted on first run)

### Full Installation

```bash
# 1. Install system dependencies
brew install tesseract  # For OCR
brew install ollama     # For local LLMs

# 2. Clone and setup
git clone https://github.com/yourusername/houdini-agent.git
cd houdini-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Download YOLO model (for UI detection)
# This happens automatically on first run, or manually:
# wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt

# 5. Grant permissions
# First run will prompt for Accessibility and Screen Recording permissions
```

### Optional: Local Vision Models

For better performance on Apple Silicon:

```bash
# Install MLX-VLM for UI-TARS
pip install mlx-vlm

# Models are auto-downloaded on first use
# ~4GB for UI-TARS-7B model
```

---

## 🎮 Usage

### Basic Usage

```bash
# Simple tasks
python -m src.main --task "Open System Preferences"
python -m src.main --task "Take a screenshot"
python -m src.main --task "Open Terminal and run 'ls -la'"
```

### Advanced Options

```bash
# Enable thinking window (see AI reasoning in real-time)
python -m src.main --task "Your task" --thinking-window

# Use specific Ollama model
python -m src.main --task "Your task" --model qwen2.5-coder:14b

# Training mode (saves execution data for analysis)
python -m src.main --task "Your task" --train

# Disable enhanced executor (fallback to basic PyAutoGUI)
python -m src.main --task "Your task" --no-enhanced
```

### Replay & Debug

```bash
# List all sessions
python -m src.main --replay-list

# Replay a specific session
python -m src.main --replay --replay-session <session_id>

# Generate debug report
python -m src.main --debug-report
```

### Programmatic Usage

```python
from src.main import run_task_internal

# Run task programmatically
result = run_task_internal(
    task_description="Open Calculator and add 5 + 3",
    is_training=False
)

print(f"Success: {result['success']}")
print(f"Session ID: {result['session_id']}")
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Task                            │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  📋 Planner (Ollama Qwen)                                   │
│  └── Breaks task into macro/micro steps                     │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  🎯 Adaptive Loop Coordinator                               │
│  ├── Macro Planning (high-level strategy)                   │
│  └── Micro Execution (pixel-precise actions)                │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  👁️ Vision System                                           │
│  ├── OmniParser V2 (YOLO + OCR)                            │
│  ├── TinyClick (fast element detection)                     │
│  └── Accessibility API (macOS native)                       │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  ✋ Executor                                                │
│  ├── Blind Actions (keyboard shortcuts)                     │
│  └── Vision Actions (element interaction)                   │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  ✅ Supervisor (llama.cpp Qwen 2.5 7B)                      │
│  └── Validates actions and provides feedback                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧩 Project Structure

```
houdini-agent/
├── src/
│   ├── main.py                 # Entry point
│   ├── planner/                # Task planning agents
│   ├── agents/                 # Execution agents
│   ├── supervisor/             # Validation & feedback
│   ├── loop/                   # Execution coordinators
│   ├── ui/                     # Thinking window
│   ├── utils/                  # Utilities
│   └── replay/                 # Replay & debug
├── prompts/                    # System prompts (self-evolving)
├── examples/                   # Usage examples
├── data/                       # Runtime data (gitignored)
├── models/                     # Local models (gitignored)
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
└── README.md                  # This file
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file from `.env.example`:

```bash
# Required for cloud planning
GEMINI_API_KEY=your_key_here  # Optional - local models work without this

# Local model path
MODEL_PATH=./models/qwen2.5-7b-instruct-q5_k_m.gguf

# Default Ollama model
OLLAMA_MODEL=qwen2.5-coder:14b

# Logging
LOG_LEVEL=INFO

# Features
ENABLE_THINKING_WINDOW=false
```

### Grant macOS Permissions

On first run, macOS will prompt for:

1. **Accessibility** - Control your computer
2. **Screen Recording** - See the screen for vision

Go to **System Settings > Privacy & Security** to grant these permissions.

---

## 🎓 Examples

### Open Applications
```bash
python -m src.main --task "Open Safari and navigate to github.com"
python -m src.main --task "Launch Calculator and compute 123 * 456"
```

### Text Editing
```bash
python -m src.main --task "Open Notes and write a todo list"
python -m src.main --task "Select all text in the current document and copy it"
```

### System Control
```bash
python -m src.main --task "Take a screenshot and save it to Desktop"
python -m src.main --task "Open System Settings and navigate to Display"
```

### Multi-Step Workflows
```bash
python -m src.main --task "Create a new folder on Desktop called 'Projects' and open it in Finder"
```

---

## 🐛 Troubleshooting

### Common Issues

**Permission Denied**
```bash
# Grant Accessibility permissions in System Settings
# System Settings > Privacy & Security > Accessibility
```

**Ollama Not Found**
```bash
# Make sure Ollama is running
ollama serve

# Or install it
brew install ollama
```

**Model Not Found**
```bash
# Pull the required model
ollama pull qwen2.5-coder:14b
```

**Import Errors**
```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### Getting Help

- Check [issues](https://github.com/yourusername/houdini-agent/issues)
- Run with debug logging: `LOG_LEVEL=DEBUG python -m src.main --task "..."`
- Generate debug report: `python -m src.main --debug-report`

---

## 🗺️ Roadmap

- [ ] Windows & Linux support
- [ ] Browser extension for web automation
- [ ] Voice command interface
- [ ] Multi-monitor support
- [ ] Custom plugin system
- [ ] Cloud sync for learned patterns

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai) - Local LLM inference
- [OmniParser](https://github.com/microsoft/OmniParser) - Screen parsing
- [TinyClick](https://github.com/Samsung/TinyClick) - GUI automation
- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration
- [Agent-S](https://github.com/simular-ai/Agent-S) - Inspiration for architecture

---

<div align="center">

**⭐ Star this repo if you find it useful!**

Made with ❤️ by the Houdini Agent team

</div>
