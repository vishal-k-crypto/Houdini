# Houdini Agent Overhaul Plan

**Goal:** Evolve Houdini from an Ollama-locked, CLI-only macOS automator into an open-source, multi-provider, cross-platform AI agent with a local-first web frontend (inspired by Open Design), BYOK CLI adapters, and a street-smart agent loop that can compete with higher-tier models through architecture, not just bigger local weights.

**Target repo:** https://github.com/vishal-k-crypto/Houdini

---

## 1. Current State Snapshot

- Planner: `src/planner/ollama_planner.py` + `src/planner/gemini_planner.py` — hardcoded to Ollama/Gemini CLI.
- Supervisor: `src/supervisor/ollama_supervisor.py` — Ollama-locked.
- LLM clients: `src/utils/ollama_client.py`, `src/utils/gemini_client.py`.
- Loop: `src/loop/adaptive_coordinator.py` drives 4-tier vision (accessibility -> tinyclick -> YOLO -> VLM).
- UI: only `src/ui/thinking_window.py` (local TK overlay) and `src/api/server.py` (FastAPI dashboard).
- No unified provider abstraction; no OpenAI / Anthropic / Claude Code / Codex / OpenCode / Kimi / DeepSeek / BYOK support.
- No web frontend; no agent-agnostic skill runtime; no local-first web workspace.

---

## 2. Design Principles (derived from Open Design)

1. **BYOK at every layer** — user brings their own API keys or installed CLI agents.
2. **Agent-agnostic adapters** — same prompts/loops run through Claude Code, Codex, OpenCode, Kimi, Gemini CLI, Ollama, OpenAI, Anthropic, DeepSeek, Grok, etc.
3. **Local-first web frontend** — a single-page web app (SvelteKit or Next.js) that communicates with a local Python daemon over WebSocket/SSE, runs in the browser, can be packaged as an Electron/Tauri desktop app later.
4. **Skill-driven design** — agent instructions live as markdown files in `skills/` and can be consumed by any adapter.
5. **Street-smart loop** — fast failure recovery, speculative execution, learned patterns, and tiered vision fallback to minimize latency and maximize accuracy.
6. **Browser-capable frontier benchmarks** — support WebLLM / WebGPU in the frontend for lightweight local inference and privacy-sensitive tasks, while the heavy executor still runs natively.

---

## 3. New Architecture

```
                    ┌─────────────────────────────────────┐
                    │  Web Frontend (SvelteKit)          │
                    │  - Chat / task input               │
                    │  - Session history                   │
                    │  - Live screenshots / thinking log   │
                    │  - Settings / provider picker        │
                    │  - Optional: WebLLM local model      │
                    └──────────────┬──────────────────────┘
                                   │ WebSocket / SSE
                    ┌──────────────▼──────────────────────┐
                    │  Houdini Daemon (FastAPI/uvicorn)  │
                    │  - REST API + WebSocket              │
                    │  - Session manager                     │
                    │  - Provider router                     │
                    │  - Vision / executor / loop            │
                    └──────────────┬──────────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
            ▼                      ▼                      ▼
    ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
    │ LLM Adapter   │     │ LLM Adapter   │      │ CLI Adapter   │
    │ (OpenAI fmt)  │     │ (Anthropic)  │      │ (Claude Code) │
    └──────────────┘     └──────────────┘      └──────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
    ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
    │ OpenAI SDK   │     │ Anthropic SDK│      │ subprocess   │
    │ DeepSeek SDK │     │ Gemini SDK   │      │ od / agy CLI │
    └──────────────┘     └──────────────┘      └──────────────┘
```

---

## 4. Implementation Tasks (Phased)

### Phase A: Foundation (Provider Abstraction)

1. **Create `src/providers/base.py`** — `LLMProvider` abstract base with `generate`, `generate_with_image`, `supports_vision`, `tool_call`, `model_name`, `list_models`.
2. **Create `src/providers/registry.py`** — provider registry + discovery via env vars / CLI detection / config.
3. **Create adapters in `src/providers/adapters/`**:
   - `openai_adapter.py` — OpenAI, OpenRouter, DeepSeek, Grok, any OpenAI-compatible endpoint.
   - `anthropic_adapter.py` — Anthropic Claude.
   - `gemini_adapter.py` — Google Gemini (SDK).
   - `ollama_adapter.py` — Reuse/rewrite Ollama client as an adapter.
   - `webllm_adapter.py` — Future: browser-side WebLLM stub (placeholder for now).
4. **Create `src/providers/cli_adapter.py`** — generic adapter that wraps installed CLI agents (Claude Code, Codex, OpenCode, Kimi, Gemini CLI, agy, Qwen CLI, etc.) by command template and prompt-injection convention.
5. **Create `src/providers/router.py`** — route tasks by provider preference, fallback, quota, cost, latency; dynamic role switching (planner vs worker vs vision).
6. **Update `config/settings.py`** — add provider config, credential pool, BYOK settings, adapter detection.
7. **Refactor `src/planner/` and `src/supervisor/`** to use provider abstraction instead of hardcoded Ollama/Gemini.

### Phase B: Street-Smart Agent Loop

8. **Add `src/loop/fast_executor.py`** — speculative parallel execution of blind actions, batching, and pre-computed coordinates.
9. **Add `src/utils/execution_confidence.py` improvements** — model-based confidence + runtime calibration.
10. **Add `src/utils/semantic_cache.py`** — vector cache of successful plans using small embeddings (sentence-transformers / BGE via ONNX).
11. **Add `src/loop/recovery_router.py`** — classify failures (network, vision, permission, UI changed) and pick correct recovery strategy.
12. **Improve `src/utils/prompt_evolution.py`** — automatic prompt A/B testing and mutation tracking.

### Phase C: Local-First Web Frontend

13. **Create `frontend/` SvelteKit app**:
    - `src/routes/+page.svelte` — chat interface with screenshot panel.
    - `src/lib/api.ts` — WebSocket/REST client.
    - `src/routes/settings/+page.svelte` — provider picker, key management, CLI detection.
    - `src/lib/terminal.ts` — optional embedded terminal view.
14. **Create `frontend/src/lib/webllm.ts`** — optional in-browser LLM via `@mlc-ai/web-llm` (local mode, no API key).
15. **Update daemon FastAPI server** (`src/api/server.py`) to serve frontend static files and expose WebSocket for streaming events.
16. **Add `frontend/package.json` and lockfile** with Vite, SvelteKit, Tailwind.

### Phase D: Open-Source Polish

17. **Add `.env.example` keys** for all new providers.
18. **Update `README.md`** — new architecture, provider table, frontend setup, browser-only AI benchmark note, WebLLM support.
19. **Add `docs/PROVIDERS.md`** and `docs/FRONTEND.md`.
20. **Add tests** for new provider registry and router.
21. **Add `.github/workflows/ci.yml`** — lint, type check, pytest.

---

## 5. Provider Matrix (target)

| Provider | Adapter | Vision | Tool Use | Notes |
|----------|---------|--------|----------|-------|
| OpenAI (GPT-4o/o3) | openai_adapter | yes | yes | BYOK |
| Anthropic (Claude 4.x/Opus/Sonnet) | anthropic_adapter | yes | yes | BYOK |
| Google Gemini | gemini_adapter | yes | yes | BYOK |
| DeepSeek | openai_adapter | no | yes | BYOK, OpenAI-compatible |
| OpenRouter | openai_adapter | yes | yes | BYOK, one key many models |
| Ollama | ollama_adapter | via LLaVA | limited | local |
| WebLLM | webllm_adapter | no | no | browser, WebGPU |
| Claude Code CLI | cli_adapter | no | yes | CLI detection |
| Codex CLI | cli_adapter | no | yes | CLI detection |
| OpenCode CLI | cli_adapter | no | yes | CLI detection |
| Kimi CLI | cli_adapter | no | yes | CLI detection |
| Gemini CLI | cli_adapter | no | yes | CLI detection |
| agy (Antigravity) | cli_adapter | no | yes | CLI detection |
| Qwen CLI | cli_adapter | no | yes | CLI detection |

---

## 6. Browser-Only Frontier AI Benchmark Note

Per current research (2026), browser-only frontier models cannot access the full machine. WebLLM enables Llama 3.2 1B, Qwen3-VL/Qwen3-Omni small variants, and Transformers.js models inside the browser with WebGPU/WebAssembly. To compete with higher-tier cloud models, Houdini should:

- Use the **native executor** (Python + accessibility) for the heavy lifting, not browser models.
- Use the browser models only for **fast classification, summarization, routing, and offline privacy-sensitive tasks**.
- Implement a **Mixture-of-Agents (MoA)** loop where cheap/fast local models handle classification/filtering and expensive cloud models handle planning/vision reasoning.
- Add **automatic provider tier routing** (free/local → cheap → frontier) with budget caps.

---

## 7. Verification Plan

- Run `python -m pytest tests/ -q` after each phase and fix new failures only.
- Start the daemon and hit `/health` and `/api/providers` endpoints.
- Launch the frontend dev server and connect to the daemon.
- Run a simple task end-to-end (open Calculator) through at least two providers.
- Commit and push after each verified phase.

---

**Plan created:** 20260705_004046