<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:0d1117&height=200&section=header&text=Houdini%20Agent&fontSize=60&fontColor=58a6ff&animation=fadeIn&fontAlignY=35&desc=AI-Powered%20macOS%20Automation%20with%20Self-Evolving%20Intelligence&descAlignY=55&descSize=18"/>

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/macOS-12+-000000?style=for-the-badge&logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLMs-000000?style=for-the-badge)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-2ea44f?style=for-the-badge)](LICENSE)

[Features](#-features) · [Quick Start](#-quick-start) · [Architecture](#-architecture) · [Examples](#-examples)

</div>

---

## 🎯 What is Houdini Agent?

Houdini Agent is an **intelligent automation system for macOS** that uses **local AI models** with computer vision to automate complex tasks. Unlike cloud-based solutions, it runs **entirely on your machine** — no data leaves your computer.

Think of it as an AI intern that can:
- 👁️ **See** your screen and understand any UI
- 🧠 **Plan** multi-step tasks autonomously
- 🖱️ **Execute** actions (click, type, scroll) like a human
- 📚 **Learn** from failures and self-improve
- 💭 **Think** out loud with a real-time reasoning window

---

<a id="features"></a>

## ✨ Features

### 🧠 Multi-Agent Architecture

| Component | Model | Purpose |
|-----------|-------|---------|
| **Planner** | Ollama (Qwen 3 Coder) | Breaks tasks into executable steps |
| **Executor** | Local Vision + Accessibility | Performs screen actions |
| **Supervisor** | llama.cpp (Qwen 2.5 7B) | Validates and corrects actions |

### 🚀 Key Capabilities

- **🖥️ Screen Understanding** — YOLO + OCR + OmniParser V2 for any UI
- **⚡ Fast Execution** — Native macOS accessibility APIs (10-100x faster than pixel-based)
- **🧠 Self-Improving** — Self-evolving prompts that learn from failures
- **💭 Thinking Window** — Real-time visualization of AI reasoning
- **📊 Replay & Debug** — Time-travel through execution history
- **🔒 Privacy-First** — All AI models run locally; zero cloud dependency

---

<a id="quick-start"></a>

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/vishal-k-crypto/Houdini.git
cd Houdini
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Ollama

```bash
brew install ollama
ollama pull qwen2.5-coder:14b
```

### 3. Configure & Run

```bash
cp .env.example .env
python -m src.main --task "Open Safari and search for Python tutorials" --thinking-window
```

---

<a id="architecture"></a>

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

## 📁 Project Structure

```
Houdini/
├── src/
│   ├── main.py              # Entry point
│   ├── planner/             # Task planning agents
│   ├── agents/              # Execution agents
│   ├── supervisor/          # Validation & feedback
│   ├── loop/                # Execution coordinators
│   ├── ui/                  # Thinking window
│   ├── utils/               # Utilities
│   └── replay/              # Replay & debug
├── prompts/                 # System prompts (self-evolving)
├── examples/                # Usage examples
├── requirements.txt         # Python dependencies
├── .env.example            # Environment template
└── README.md               # This file
```

---

## 🎓 Examples

```bash
# Open applications
python -m src.main --task "Open Safari and navigate to github.com"

# Text editing
python -m src.main --task "Open Notes and write a todo list"

# System control
python -m src.main --task "Take a screenshot and save it to Desktop"

# Multi-step workflows
python -m src.main --task "Create a new folder on Desktop called 'Projects' and open it in Finder"
```

---

## ⚙️ Configuration

Create `.env` from `.env.example`:

```bash
OLLAMA_MODEL=qwen2.5-coder:14b
LOG_LEVEL=INFO
ENABLE_THINKING_WINDOW=false
```

**Required macOS Permissions:**
- **Accessibility** — Control your computer
- **Screen Recording** — See screen contents

> Go to **System Settings > Privacy & Security** to grant these permissions.

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Permission Denied** | Grant Accessibility/Screen Recording in System Settings |
| **Ollama Not Found** | Run `ollama serve` or `brew install ollama` |
| **Model Not Found** | Run `ollama pull qwen2.5-coder:14b` |
| **Import Errors** | Reinstall: `pip install -r requirements.txt` |

---

## 🗺️ Roadmap

- [ ] Windows & Linux support
- [ ] Browser extension for web automation
- [ ] Voice command interface
- [ ] Multi-monitor support
- [ ] Custom plugin system

---

## 🤝 Contributing

Contributions welcome! Please submit a Pull Request.

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with** 🐍 **Python** · 🧠 **Local LLMs** · 👁️ **Computer Vision**

</div>
