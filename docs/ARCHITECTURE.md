# Houdini Agent — Architecture

## Overview

Houdini is a multi-agent macOS automation system. A user gives a natural-language task (e.g. *"send a WhatsApp message to John saying I'll be late"*) and the system plans, executes, verifies, and self-corrects autonomously.

Inference can run locally via **Ollama** or **WebLLM**, or you can Bring Your Own Key (BYOK) for cloud providers such as OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter, and Grok. See [PROVIDERS.md](PROVIDERS.md) for details.

---

## Execution Pipeline

```
 User Task
     │
     ▼
┌──────────────────────────────┐
│ 1. PLANNER (Ollama Qwen 3)  │  Decomposes task into 3-10 macro steps.
│    ollama_planner.py         │  Checks pattern store for cached plans.
│                              │  If pattern confidence ≥ 0.85, skips LLM.
└──────────┬───────────────────┘
           ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. ADAPTIVE COORDINATOR (main loop)                          │
│    adaptive_coordinator.py                                   │
│                                                              │
│    For each macro step:                                      │
│    ┌──────────────────────────────┐                          │
│    │ 2a. EXECUTOR generates micro │  Converts macro step +   │
│    │     actions from screen      │  screen context → micro  │
│    │     context                  │  actions (click, type,   │
│    │     enhanced_executor.py     │  hotkey, scroll, wait)   │
│    │     vision_executor.py       │                          │
│    └──────────┬───────────────────┘                          │
│               ▼                                              │
│    ┌──────────────────────────────┐                          │
│    │ 2b. ACTION EXECUTION        │  4-tier strategy:         │
│    │                              │  1. Accessibility API    │
│    │                              │     (0.002s, native)     │
│    │                              │  2. TinyClick Florence-2 │
│    │                              │     (250ms, learned)     │
│    │                              │  3. OmniParser + YOLO    │
│    │                              │     (1-3s, visual)       │
│    │                              │  4. VLM analysis         │
│    │                              │     (1-5s, last resort)  │
│    └──────────┬───────────────────┘                          │
│               ▼                                              │
│    ┌──────────────────────────────┐                          │
│    │ 2c. STEP VERIFICATION       │  Checks screen state     │
│    │     + stuck detection       │  against expectations.    │
│    │                              │  If stuck > 5 attempts,  │
│    │                              │  skips or re-plans.      │
│    └──────────────────────────────┘                          │
│                                                              │
│    When all macro steps complete:                            │
│    ┌──────────────────────────────┐                          │
│    │ 2d. SUPERVISOR VERIFICATION │  LLM reviews final       │
│    │     _supervisor_verify_     │  screen + actions.        │
│    │     completion()            │  Requires ≥ 75% conf.    │
│    │                              │  Zero-element screens    │
│    │                              │  verified via screenshot.│
│    └──────────┬───────────────────┘                          │
│               │                                              │
│          ┌────┴────┐                                         │
│          │ Pass?   │                                         │
│          └────┬────┘                                         │
│           yes │ no                                           │
│          ┌────┘                                              │
│          │    ┌──────────────────────────┐                   │
│          │    │ 2e. EVOLUTION            │  Supervisor adds  │
│          │    │ _supervisor_evolve_task()│  corrective steps │
│          │    │ Max 3 attempts, then     │  and re-enters    │
│          │    │ marks FAILED             │  the execution    │
│          │    └──────────────────────────┘  loop.            │
│          ▼                                                   │
│       COMPLETED or FAILED                                    │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 3. LEARNING                  │  Pattern store, prompt evolution,
│    pattern_store.py          │  lesson store, confidence model
│    prompt_evolution.py       │  all updated from the outcome.
│    lesson_store.py           │
│    execution_confidence.py   │
└──────────────────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 4. REPLAY SYSTEM             │  Every action, screen capture,
│    execution_logger.py       │  and LLM call logged with ms
│    replay_ui.py              │  precision for time-travel debug.
└──────────────────────────────┘
```

---

## Architecture Modes

| Mode | Flag | Coordinator | Status |
|------|------|-------------|--------|
| **Adaptive** (default) | `--use-adaptive` | `AdaptiveLoopCoordinator` | **Primary** — production use |
| LangGraph | `--langgraph` | `LangGraphCoordinator` | Experimental — state machine with checkpointing |
| Legacy | `--legacy` | `LoopCoordinator` + `ExecutorLoop` | Deprecated — kept for backwards compat |

The adaptive coordinator is the only one actively maintained. Use `--langgraph` only for checkpointing experiments.

---

## Module Map

```
src/
├── main.py                    Entry point, CLI arg parsing
├── health_check.py            Pre-flight checks (--health-check)
│
├── planner/
│   └── ollama_planner.py      Task → macro steps (with pattern cache)
│
├── loop/                      Execution coordinators
│   ├── adaptive_coordinator   PRIMARY: macro→micro→verify→evolve loop
│   ├── langgraph_coordinator  EXPERIMENTAL: graph-based state machine
│   ├── loop_coordinator       DEPRECATED: legacy orchestrator
│   ├── executor_loop          DEPRECATED: legacy executor
│   ├── supervisor_loop        DEPRECATED: legacy supervisor loop
│   ├── task_verifier          Multi-method completion verification
│   ├── recovery_handler       Stuck detection & recovery
│   ├── loop_state             State dataclasses
│   └── langgraph_state        LangGraph state schema
│
├── agents/                    Action executors
│   ├── enhanced_executor      Accessibility-first fast executor
│   ├── vision_executor        Vision-based element interaction
│   ├── blind_executor         Keyboard-only (no screen check)
│   ├── grounding              Coordinate grounding for vision
│   └── memory                 Agent working memory
│
├── supervisor/                Validation layer
│   ├── ollama_supervisor      LLM-based validation + history
│   ├── qwen_validator         Local llama.cpp validator
│   └── semantic_checker       Fast keyword-based pre-check
│
├── utils/                     ~40 utility modules
│   ├── ollama_client          Ollama API wrapper
│   ├── accessibility_reader   macOS accessibility tree
│   ├── tinyclick_server       TinyClick vision model
│   ├── local_vision_localizer OmniParser integration
│   ├── pattern_store          Cached plan patterns
│   ├── prompt_evolution       Self-improving prompts
│   ├── execution_confidence   Action confidence scoring
│   ├── lesson_store           Failure lesson database
│   ├── context_memory         Long-term file/resource memory
│   ├── probability_model      Handles incomplete task specs
│   ├── ui_wait                Event-driven UI waiting
│   └── ...                    Logging, schemas, embedding, etc.
│
├── ui/
│   └── thinking_window        Real-time reasoning visualization
│
├── replay/
│   ├── execution_logger       Event recording (ms precision)
│   └── replay_ui              Time-travel session viewer
│
└── data_collection/
    └── auto_collector         Automated training data generation

config/
├── settings.py                Centralized configuration (HoudiniSettings)
└── __init__.py

prompts/                       LLM system prompts
├── adaptive_supervisor_prompt Supervisor instructions
├── executor_prompt            Executor instructions
├── planner_prompt             Planner instructions
├── supervisor_prompt          Validation prompt
└── ...
```

---

## Vision Strategy Fallback Chain

When the executor needs to interact with a UI element, it tries these strategies in order:

| Priority | Strategy | Speed | Accuracy | When Used |
|----------|----------|-------|----------|-----------|
| 1 | **Accessibility API** | 0.002s | 100% | Element has accessibility label |
| 2 | **TinyClick (Florence-2)** | 250ms | ~74% | Element visible but no label |
| 3 | **OmniParser + YOLO** | 1-3s | ~65% | Complex/custom UI |
| 4 | **VLM Analysis** | 1-5s | ~50% | Last resort, asks LLM to locate |

The executor picks the fastest strategy that can handle the current element. If a strategy fails, it falls through to the next.

---

## Configuration

All tunable parameters are in `config/settings.py`. Values come from (highest priority first):

1. **Environment variables** — `COMPLETION_CONFIDENCE_THRESHOLD=0.8`
2. **`.env` file** — auto-loaded at startup
3. **Defaults** — defined in `HoudiniSettings`

See [.env.example](../.env.example) for all available settings.

Key thresholds:

| Setting | Default | Purpose |
|---------|---------|---------|
| `COMPLETION_CONFIDENCE_THRESHOLD` | 0.75 | Min confidence to accept task as done |
| `PATTERN_SIMILARITY_THRESHOLD` | 0.70 | Min similarity for cached plan reuse |
| `MAX_STEP_ATTEMPTS` | 5 | Retries before skipping stuck step |
| `MAX_EVOLUTION_ATTEMPTS` | 3 | Max supervisor re-plans before failing |
| `ZERO_ELEMENT_SCREENSHOT_CAP` | 0.80 | Confidence cap when no accessibility elements |

---

## Learning System

Houdini improves over time through four mechanisms:

1. **Pattern Store** — Caches successful task plans. If a new task is similar enough (≥ 0.70), reuses the cached plan instead of calling the LLM.

2. **Prompt Evolution** — Tracks which prompt variants produce better results. Slowly evolves prompts toward higher success rates.

3. **Lesson Store** — Records failure analysis. When the same failure pattern recurs, the system can apply the previous fix.

4. **Execution Confidence** — Rates each action type's reliability in each context. Low-confidence actions trigger extra verification.

---

## Data Flow

```
Task → Planner → [Pattern Store hit?]
                  │ yes → Use cached plan
                  │ no  → LLM generates plan
                  ▼
       Macro Steps → For each step:
                     Screen Context → Executor → Micro Actions
                                                      │
                     ┌────────────────────────────────┘
                     ▼
                     Action → [Confidence gating]
                              │ pass → Execute → Log to Replay
                              │ fail → Skip / Ask Supervisor
                     ▼
                     Step Verification → [Screen matches?]
                              │ yes → Next step
                              │ no  → Adaptive re-plan
                     ▼
       All Steps Done → Supervisor Verification
                        │ ≥ 75% confidence → COMPLETED
                        │ < 75% confidence → Evolution (max 3x)
                        │ Max attempts → FAILED
```
