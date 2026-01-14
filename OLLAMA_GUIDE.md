# Ollama Integration Guide

## Overview

Houdini Agent now uses **Ollama with Qwen 3 Coder 480B** parameter model instead of Gemini for all three agents:
- **Planner**: Uses Ollama Qwen 3 Coder for task planning
- **Executor**: Executes actions and maintains operation history
- **Supervisor**: Validates results and tracks executor history

## Key Features

### 1. Executor History Loop
The executor now maintains a history of all previous operations, which provides context to the planner:
- History stored in `data/executor_history.json`
- Last 10 operations passed to planner for context-aware planning
- Supervisor tracks success rates and execution patterns

### 2. Ollama Cloud Support
- **Local**: Use `qwen2.5-coder:32b` model (faster, runs locally)
- **Cloud**: Use `qwen3-coder:480b` model (more powerful, requires cloud endpoint)

### 3. Improved Context Awareness
- Planner receives executor history before generating plans
- Learns from previous successes and failures
- Adapts timing and approach based on past executions

## Setup

### Install Ollama

```bash
# macOS
brew install ollama

# Or download from https://ollama.ai
```

### Pull the Model

```bash
# For local execution (recommended to start)
ollama pull qwen2.5-coder:32b

# For cloud execution (when available)
# No pull needed, model runs on Ollama Cloud
```

### Or Use Setup Script

```bash
./setup_ollama.sh
```

## Usage

### Basic Usage (Local Ollama)

```bash
# Activate virtual environment
source .venv/bin/activate

# Run with loop mode (recommended)
python -m src.main --task "search for quantum physics" --loop

# Run without thinking window
python -m src.main --task "open Safari and search for AI news" --loop --no-thinking-window
```

### Cloud Usage (480B Model)

```bash
# Using Ollama Cloud endpoint
python -m src.main \
  --task "create a detailed analysis of machine learning" \
  --loop \
  --model qwen3-coder:480b \
  --cloud-endpoint https://cloud.ollama.ai
```

### Disable Supervisor

```bash
# Run without supervisor (faster but no history tracking)
python -m src.main --task "your task" --loop --no-supervisor
```

## Command Line Options

```
--task, -t          Task description (required)
--model, -m         Ollama model (default: qwen2.5-coder:32b)
--cloud-endpoint    Ollama cloud endpoint URL
--loop              Use continuous loop mode (recommended)
--no-supervisor     Disable supervisor monitoring
--supervisor-mode   background (default) or checkpoint
--no-thinking-window Disable floating thinking window
--use-enhanced      Use enhanced executor (default: True)
--no-enhanced       Disable enhanced executor
```

## Architecture Changes

### Before (Gemini-based)
```
User Task → Gemini Planner → Executor → Gemini Supervisor → Result
```

### After (Ollama-based)
```
User Task → Ollama Planner ← Executor History
              ↓
          Executor (maintains history)
              ↓
          Ollama Supervisor → Updates History
              ↓
          Result
```

## Files Modified

### New Files
- `src/utils/ollama_client.py` - Ollama client wrapper
- `src/planner/ollama_planner.py` - Ollama-based planner with history context
- `src/supervisor/ollama_supervisor.py` - Supervisor with history tracking
- `setup_ollama.sh` - Setup script

### Modified Files
- `src/loop/loop_coordinator.py` - Updated to use Ollama components
- `src/main.py` - Updated initialization and CLI args
- All references to `GeminiCLI` replaced with `OllamaClient`
- All references to `GeminiPlanner` replaced with `OllamaPlanner`

## Data Files

### Executor History
Location: `data/executor_history.json`

Structure:
```json
[
  {
    "task": "search for quantum physics",
    "timestamp": "2026-01-14T20:00:00",
    "batches_count": 2,
    "success": true,
    "duration": 5.2,
    "error": null
  }
]
```

### Task History
Location: `data/task_history.json`
- Stores cached plans for faster repeat executions
- Maintained by planner

## Performance

### Local Model (qwen2.5-coder:32b)
- **Speed**: Fast (2-5 seconds per plan)
- **Quality**: Good for most tasks
- **Requirements**: 16GB RAM recommended

### Cloud Model (qwen3-coder:480b)
- **Speed**: Moderate (5-10 seconds per plan)
- **Quality**: Excellent reasoning and planning
- **Requirements**: Internet connection + Ollama Cloud access

## Troubleshooting

### "Ollama not found"
```bash
# Install Ollama
brew install ollama

# Start Ollama service
ollama serve
```

### "Model not found"
```bash
# Pull the model
ollama pull qwen2.5-coder:32b
```

### "Cloud endpoint connection failed"
- Check your internet connection
- Verify the cloud endpoint URL
- Ensure you have access to Ollama Cloud

### "Empty response from Ollama"
- Check if Ollama service is running: `ollama list`
- Try restarting Ollama: `killall ollama && ollama serve`

## Migration from Gemini

If you were using Gemini before:

1. **No data loss**: Task history and patterns are preserved
2. **Same commands**: Just remove Gemini-specific args
3. **Install Ollama**: Run `./setup_ollama.sh`
4. **Update calls**: Replace `--model gemini-2.5-pro` with `--model qwen2.5-coder:32b`

## Examples

### Search Task
```bash
python -m src.main --task "search for latest AI news" --loop
```

### Multi-step Task
```bash
python -m src.main --task "open YouTube and play the latest MKBHD video" --loop
```

### With Cloud Model
```bash
python -m src.main \
  --task "analyze the benefits of quantum computing" \
  --loop \
  --model qwen3-coder:480b \
  --cloud-endpoint https://cloud.ollama.ai
```

## Benefits of Ollama Integration

1. **Local Execution**: No API keys needed, runs on your machine
2. **Cost Effective**: No per-request charges
3. **Privacy**: Data stays local (except cloud mode)
4. **Customizable**: Use any Ollama-compatible model
5. **Executor History**: Context-aware planning from previous operations
6. **Learning**: Supervisor tracks patterns and improves over time

## Next Steps

1. Run setup: `./setup_ollama.sh`
2. Try a simple task: `python -m src.main --task "search for cats" --loop`
3. Check executor history: `cat data/executor_history.json`
4. Explore advanced options with `--help`
