# 🤖 Houdini Agent

**AI-Powered Desktop Automation with Provider-Agnostic Intelligence**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-black.svg)](https://www.apple.com/macos/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/vishal-k-crypto/Houdini/actions/workflows/ci.yml/badge.svg)](https://github.com/vishal-k-crypto/Houdini/actions/workflows/ci.yml)

<p align="center">
  <strong>Automate complex desktop tasks using any LLM provider — local, cloud, or browser-based</strong>
</p>

[Features](#-features) • [Quick Start](#-quick-start) • [Installation](#-installation) • [Usage](#-usage) • [Architecture](#-architecture) • [Providers](#-providers) • [Frontend](#-frontend)

</div>

---

## 🎯 What is Houdini Agent?

Houdini Agent is an intelligent desktop automation system that uses **any compatible LLM provider** to:

- 👁️ **See** your screen using computer vision
- 🧠 **Plan** complex multi-step tasks
- 🖱️ **Execute** actions (click, type, scroll) like a human
- 📚 **Learn** from experience and improve over time
- 💭 **Think** out loud with a real-time reasoning window
- 🌐 **Chat** with it through a local-first web frontend

It supports **Bring Your Own Key (BYOK)** for cloud providers, runs entirely on **Ollama** locally, or even runs frontier models in the browser via **WebLLM** — your data stays under your control.

---

## ✨ Features

### 🧠 Multi-Agent Architecture
| Component | Role | Default Provider |
|-----------|------|------------------|
| **Planner** | Breaks tasks into executable macro steps | Ollama / OpenAI / Gemini / Anthropic |
| **Executor** | Performs screen actions via accessibility + vision | Local macOS APIs |
| **Supervisor** | Validates and corrects actions | Local Ollama or cloud model |

### 🚀 Key Capabilities

- **🖥️ Screen Understanding** - Uses YOLO + OCR + OmniParser to understand any UI
- **⚡ Fast Execution** - Native macOS accessibility APIs for 10-100x speed
- **🧠 Self-Improving** - Learns from failures and adapts prompts automatically
- **💭 Thinking Window** - Real-time visualization of AI reasoning
- **📊 Replay & Debug** - Time-travel through execution history
- **🔌 Provider Abstraction** - Swap LLM providers with one env variable
- **🌐 Local Web Frontend** - Chat with Houdini from your browser; no cloud required
- **🔒 Privacy-First** - Choose local-only (Ollama/WebLLM) or BYOK cloud providers

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
# Clone the repository
git clone https://github.com/vishal-k-crypto/Houdini.git
cd Houdini

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Choose a Provider

**Option A — Local Ollama (default, private):**
```bash
brew install ollama
ollama pull qwen2.5-coder:14b
```

**Option B — Cloud provider (BYOK):**
```bash
export OPENAI_API_KEY=sk-...
# or ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY, etc.
```

**Option C — Browser-based WebLLM:**
Start the frontend and select a WebLLM model — no installation, no API key.

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your preferred provider and model
```

### 4. Verify Setup

```bash
python -m src.main --health-check
```

### 5. Run Your First Task

```bash
# CLI task
python -m src.main --task "Open Calculator and calculate 15 * 23"

# With the web frontend
python -m src.api.server
# open http://localhost:8420
```

---

## 📦 Installation

### Prerequisites

- **macOS 12+** (Monterey or later)
- **Python 3.10+**
- At least one supported provider configured (Ollama, OpenAI, Anthropic, Gemini, etc.)
- **Accessibility & Screen Recording Permissions** (granted on first run)

### Full Installation

```bash
# 1. Install system dependencies
brew install tesseract  # For OCR
brew install ollama     # Optional: for local LLMs

# 2. Clone and setup
git clone https://github.com/vishal-k-crypto/Houdini.git
cd Houdini
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Install Playwright browsers (for web automation)
playwright install chromium

# 4. Configure environment
cp .env.example .env

# 5. Grant permissions
# First run will prompt for Accessibility and Screen Recording permissions
```

### Optional: Local Vision Models

For better performance on Apple Silicon:

```bash
pip install mlx-vlm
# Models are auto-downloaded on first use
# ~4GB for UI-TARS-7B model
```

### Frontend Setup

```bash
# Install Node.js dependencies
npm install --prefix frontend

# Start dev server
npm run dev --prefix frontend

# Or build for production
npm run build --prefix frontend
```

---

## 🎮 Usage

### CLI Usage

```bash
# Simple task
python -m src.main --task "Open System Preferences"

# Use a specific provider/model
python -m src.main --task "Open Safari" --model gpt-4o

# Enable thinking window
python -m src.main --task "Your task" --thinking-window

# Training mode
python -m src.main --task "Your task" --train

# Disable enhanced executor
python -m src.main --task "Your task" --no-enhanced
```

### Web Frontend

```bash
python -m src.api.server
```

Open `http://localhost:8420` in your browser. Submit tasks, watch live events, and review execution history.

### Programmatic API

```python
from src.main import run_task_internal

result = run_task_internal(
    task_description="Open Calculator and add 5 + 3",
    is_training=False
)

print(f"Success: {result['success']}")
print(f"Session ID: {result['session_id']}")
```

### HTTP API

```bash
# Submit a task
curl -X POST http://localhost:8420/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Open Notes and write a todo list"}'

# Stream events
curl http://localhost:8420/tasks/{task_id}/stream
```

---

## 🏗️ Architecture

> **Full details:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

```
 User Task
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  📋 Planner (any LLM provider)                             │
│  └── Task → 3-10 macro steps (cached via pattern store)     │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  🎯 Adaptive Coordinator                                    │
│  ├── Macro step → screen context → micro actions            │
│  ├── 4-tier vision: Accessibility → TinyClick → YOLO → VLM │
│  ├── Stuck detection + adaptive re-planning                 │
│  └── Supervisor verification (≥75% confidence to complete)  │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  ✅ Supervisor + Evolution                                   │
│  ├── LLM reviews final screen against success criteria      │
│  ├── Adds corrective steps if incomplete (max 3 attempts)   │
│  └── Screenshot-based verification for zero-element screens   │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  📚 Learning System                                         │
│  ├── Pattern store (cache successful plans)                   │
│  ├── Prompt evolution (self-improving prompts)                │
│  ├── Lesson store (failure analysis)                        │
│  └── Execution confidence (action reliability scoring)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔌 Providers

Houdini supports a wide range of LLM providers through a unified adapter layer.

### Supported Providers

| Provider | Type | Key / Detection | Notes |
|----------|------|-----------------|-------|
| **Ollama** | Local | `OLLAMA_ENDPOINT` (optional) | Default; runs locally |
| **OpenAI** | Cloud | `OPENAI_API_KEY` | GPT-4o, GPT-4, etc. |
| **Anthropic** | Cloud | `ANTHROPIC_API_KEY` | Claude 3/3.5 family |
| **Gemini** | Cloud | `GEMINI_API_KEY` | Google Gemini 2.0 |
| **DeepSeek** | Cloud | `DEEPSEEK_API_KEY` | OpenAI-compatible |
| **OpenRouter** | Cloud | `OPENROUTER_API_KEY` | OpenAI-compatible gateway |
| **Grok (xAI)** | Cloud | `XAI_API_KEY` | OpenAI-compatible |
| **WebLLM** | Browser | None | Runs models in browser, no install |
| **Claude Code CLI** | CLI | `claude` in PATH | Anthropic CLI agent |
| **Codex CLI** | CLI | `codex` in PATH | OpenAI CLI agent |
| **OpenCode CLI** | CLI | `opencode` in PATH | OpenAI CLI agent |
| **Kimi CLI** | CLI | `kimi` in PATH | Moonshot CLI agent |
| **Gemini CLI** | CLI | `gemini` in PATH | Google CLI agent |
| **agy / Antigravity** | CLI | `agy` in PATH | Terminal agent |
| **Qwen CLI** | CLI | `qwen` in PATH | Alibaba CLI agent |

> **See [docs/PROVIDERS.md](docs/PROVIDERS.md) for:** adding custom adapters, detection logic, fallback routing, and model aliases.

---

## 🌐 Frontend

Houdini ships with a local-first web frontend built with Vite + SvelteKit + TypeScript.

### Features

- Chat-style task submission
- Live WebSocket event stream
- Task history and replay
- Provider selector (including WebLLM)
- Dark mode

### Quick Start

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

### Serve from the Daemon

```bash
python -m src.api.server
# Serves static frontend from frontend/dist when built
npm run build --prefix frontend
```

> **See [docs/FRONTEND.md](docs/FRONTEND.md) for:** event schemas, build options, and WebSocket details.

---

## 🛠️ Skills

Houdini uses a **skill-as-file** protocol inspired by Open Design. Skills are Markdown files with YAML frontmatter that teach the agent reusable execution patterns for common task families (e.g. opening apps, web search, saving files).

### How it works

- Skills live in `skills/`.
- The planner injects relevant skill instructions into the prompt based on trigger keywords.
- You can browse and test skill matching in the frontend at **Skills**.

### Example skill

```markdown
---
id: open-app
name: Open an Application
triggers:
  - open
  - launch
tags:
  - macos
priority: 10
---

When opening an app, use Cmd+Space → type the app name → Enter.
```

> **See [docs/SKILLS.md](docs/SKILLS.md) for:** the full skill spec, how to add custom skills, and how matching works.

---

## ⚠️ Important Notes

### Browser-Only Frontier AI

Some models (e.g., certain WebLLM variants, Google Gemini web experiments) are only available through a browser. Use the Houdini frontend to leverage them.

### WebLLM Limitations

- Requires a modern browser with WebGPU support (Chrome 113+, Edge, Firefox Nightly).
- First model load may take 30–120 seconds while weights download/cached.
- Smaller models (Llama 3.1 8B, Phi-4) are recommended for lower-end machines.

---

## 🧩 Project Structure

```
Houdini/
├── src/
│   ├── main.py                 # Entry point & CLI
│   ├── health_check.py         # Pre-flight checks (--health-check)
│   ├── api/                    # FastAPI server + dashboard + auth
│   ├── providers/              # Unified LLM adapter layer
│   ├── planner/                # Task → macro step decomposition
│   ├── agents/                 # Action executors (blind, vision, enhanced)
│   ├── supervisor/             # Validation, semantic checking
│   ├── loop/                   # Execution coordinators
│   ├── skills/                 # Skill-as-file loader and registry
│   ├── ui/                     # Thinking window
│   ├── utils/                  # Vision, learning, accessibility, etc.
│   └── replay/                 # Time-travel debugging
├── frontend/                   # Vite + SvelteKit + TypeScript web UI
├── config/
│   └── settings.py             # Centralized configuration (HoudiniSettings)
├── prompts/                    # LLM system prompts
├── skills/                     # Reusable task instruction files
├── docs/
│   ├── ARCHITECTURE.md         # Detailed architecture docs
│   ├── PROVIDERS.md            # Provider adapter guide
│   ├── FRONTEND.md             # Frontend dev guide
│   └── SKILLS.md               # Skill protocol guide
├── tests/                      # pytest test suite
├── .github/
│   ├── workflows/ci.yml          # GitHub Actions CI
│   └── CONTRIBUTING.md           # Contribution guide
├── .env.example                # All configurable env vars
├── requirements.txt            # Python dependencies
├── frontend/package.json         # Node dependencies
└── README.md
```

---

## ⚙️ Configuration

All settings are managed by `config/settings.py`. Values come from (highest priority):

1. **Environment variables** — `COMPLETION_CONFIDENCE_THRESHOLD=0.8`
2. **`.env` file** — auto-loaded at startup
3. **Defaults** — defined in code

```bash
# Copy template and customize
cp .env.example .env
```

See [.env.example](.env.example) for all configurable parameters including provider keys, model names, thresholds, and timeouts.

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

- Check [issues](https://github.com/vishal-k-crypto/Houdini/issues)
- Run with debug logging: `LOG_LEVEL=DEBUG python -m src.main --task "..."`
- Generate debug report: `python -m src.main --debug-report`

---

## 🗺️ Roadmap

- [x] Provider abstraction layer (BYOK)
- [x] Local-first web frontend
- [x] WebLLM support
- [ ] Windows & Linux support
- [ ] Browser extension for web automation
- [ ] Voice command interface
- [ ] Multi-monitor support
- [ ] Custom plugin system
- [ ] Cloud sync for learned patterns (opt-in)

---

## 🤝 Contributing

Contributions are welcome! Please see [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines.

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
- [WebLLM](https://webllm.mlc.ai/) - In-browser LLM inference

---

<div align="center">

**⭐ Star this repo if you find it useful!**

Made with ❤️ by the Houdini Agent team

</div>
