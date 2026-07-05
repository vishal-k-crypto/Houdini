# Houdini Agent — Frontend Developer Guide

Houdini ships with a local-first web frontend built with **SvelteKit 5 + TypeScript**. It uses `@sveltejs/adapter-static` for production builds, connects to the Houdini daemon, submits tasks, streams live events, and optionally runs frontier models in the browser via **WebLLM**.

---

## Project Layout

```
frontend/
├── src/
│   ├── app.html            # HTML shell
│   ├── app.css             # Global styles
│   ├── app.d.ts            # SvelteKit type declarations
│   ├── lib/
│   │   ├── store.ts        # Svelte stores (tasks, settings, events, WebSocket)
│   │   ├── types.ts        # Shared TypeScript types
│   │   └── webllm.ts       # WebLLM browser inference integration
│   └── routes/
│       ├── +layout.svelte  # Root layout (sidebar, nav)
│       ├── +page.svelte    # Home / task dashboard
│       ├── settings/
│       │   └── +page.svelte    # Provider & settings configuration
│       ├── benchmarks/
│       │   └── +page.svelte    # Benchmark runner UI
│       ├── sessions/
│       │   └── +page.svelte    # Session history
│       └── skills/
│           └── +page.svelte    # Skill browser
├── svelte.config.js
├── vite.config.ts
├── tsconfig.json
├── postcss.config.js
└── package.json
```

---

## How to Run the Frontend Dev Server

### Prerequisites

- **Node.js 18+** (LTS recommended)
- The Houdini Python backend (optional but recommended for full features)

### Install Dependencies

```bash
npm install --prefix frontend
```

### Start Dev Server

```bash
npm run dev --prefix frontend
```

By default, the dev server runs on `http://localhost:5173`. The frontend proxies API calls to `http://localhost:8420` via the Vite config.

### With the Daemon

```bash
# Terminal 1: start the Houdini API server
python -m src.api.server

# Terminal 2: start the frontend dev server
npm run dev --prefix frontend
```

Open `http://localhost:5173` and submit a task. The frontend will communicate with the daemon at `http://localhost:8420`.

---

## How to Build and Serve from the Daemon

### Production Build

```bash
npm run build --prefix frontend
```

This produces a `frontend/dist` directory with static HTML, CSS, and JS assets (via `@sveltejs/adapter-static`).

### Serve from the Daemon

The Houdini FastAPI server can serve the built frontend from `frontend/dist` if static file serving is enabled. This is the recommended way to run Houdini in a standalone mode.

```bash
# Build once
npm run build --prefix frontend

# Start the daemon — serves the frontend at /
python -m src.api.server
```

Then open `http://localhost:8420`. The API remains available under `/api/*`, `/ws`, etc.

> **Note:** If the frontend build is missing, the daemon still serves the HTTP API and dashboard endpoints.

---

## WebSocket Event Schema

The frontend connects to the daemon via WebSocket (typically at `ws://localhost:8420/ws`) to receive live task events. The connection is managed by the `connectWebSocket()` function in `src/lib/store.ts`.

### Connection

```typescript
// In src/lib/store.ts
import { appendEvent, appendScreenshot, appendTerminal } from '$lib/store';

export function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

  ws.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    appendEvent(event);
    // Route to specific handlers based on event.type
  };

  return ws;
}
```

### Incoming Messages (Server → Client)

| Type | Payload | Description |
|------|---------|-------------|
| `connection` | `{ client_id, message }` | Connection established |
| `started` | `{ task_id, task, ts }` | A task started executing |
| `architecture` | `{ task_id, value }` | Architecture mode selected (adaptive/langgraph/legacy) |
| `completed` | `{ task_id, success, result }` | Task finished successfully |
| `failed` | `{ task_id, error }` | Task failed |
| `error` | `{ task_id, error }` | Runtime error during execution |
| `confidence` | `{ task_id, score, label, source }` | Confidence score update |
| `screenshot` | `{ task_id, image_base64, timestamp }` | Browser/desktop screenshot |
| `ping` | `{ ts }` | Keep-alive ping |

Example:

```json
{
  "type": "started",
  "task_id": "abc123",
  "task": "Open Calculator",
  "ts": "2026-07-05T12:00:00"
}
```

### Outgoing Messages (Client → Server)

| Type | Payload | Description |
|------|---------|-------------|
| `ping` | `{ ts }` | Keep-alive response |
| `subscribe` | `{ task_id }` | Subscribe to a specific task's events |
| `unsubscribe` | `{ task_id }` | Unsubscribe from a task |

### Dashboard WebSocket

The daemon also exposes a dashboard WebSocket at `/ws/dashboard` used by the built-in dashboard (`/dashboard`). It emits the same event types but may include additional UI-specific fields.

---

## Svelte Stores

The frontend state is managed via Svelte writable/derived stores in `src/lib/store.ts`:

| Store | Type | Description |
|-------|------|-------------|
| `tasks` | `Writable<Task[]>` | All submitted tasks |
| `health` | `Writable<Health \| null>` | Backend health status |
| `settings` | `Writable<Settings>` | Persisted user settings (localStorage) |
| `wsConnected` | `Writable<boolean>` | WebSocket connection state |
| `terminal` | `Writable<TerminalEntry[]>` | Terminal log entries |
| `screenshots` | `Writable<ScreenshotEvent[]>` | Recent screenshots |
| `events` | `Writable<SessionEvent[]>` | Raw session events |
| `selectedTaskId` | `Writable<string \| null>` | Currently selected task |
| `selectedTask` | `Readable<Task \| null>` | Derived: current task details |

Settings are automatically persisted to `localStorage` under the key `houdini.settings`.

---

## WebLLM Integration

WebLLM allows running models directly in the browser without any backend API key.

### Supported Models

Recommended WebLLM models:

- `Llama-3.1-8B-Instruct`
- `Phi-4-mini-instruct`
- `Qwen2.5-7B-Instruct`

### Loading a Model

```typescript
// In src/lib/webllm.ts
import * as webllm from "@mlc-ai/web-llm";

const engine = new webllm.MLCEngine();
await engine.reload("Llama-3.1-8B-Instruct-q4f32_1-MLC");

const reply = await engine.chat.completions.create({
  messages: [{ role: "user", content: "Plan a desktop task" }],
});
```

### Limitations

- **Browser support:** WebGPU is required. Use Chrome 113+, Edge, or Firefox Nightly.
- **First load:** Model weights are downloaded and cached; first run can take 30–120 seconds.
- **Performance:** Large models may be slow on machines without a fast GPU. Use 7B parameter models or smaller.
- **Vision:** WebLLM models generally do not support image inputs; use the Python backend for vision tasks.

### Using WebLLM with the Daemon

1. Open the frontend in a WebGPU-capable browser.
2. Select **WebLLM** in the provider dropdown.
3. Choose a model and wait for it to load.
4. Submit a task. The frontend can:
   - Use the local model for planning, then send actions to the daemon, OR
   - Use WebLLM as a chat assistant alongside the daemon's execution.

---

## Browser Vision (Set-of-Marks)

The browser agent supports **vision-based grounding** using Set-of-Marks (SoM). When enabled:

1. The agent takes a screenshot of the current page.
2. Interactive elements are detected and numbered with red markers.
3. The annotated screenshot is sent to a vision-capable LLM.
4. The LLM refers to elements by their SoM ID (e.g., "click element [3]").
5. SoM IDs are resolved back to stable Playwright selectors.

### Enabling Browser Vision

- **Settings UI:** Toggle "Use browser vision (screenshot + Set-of-Marks)" in `/settings`.
- **API:** POST `/api/settings` with `{"use_browser_vision": true}`.
- **Environment:** Set `HOUDINI_USE_BROWSER_VISION=true`.

> **Note:** Browser vision requires a provider that supports image inputs (e.g., GPT-4o, Gemini, Claude). If the active provider lacks vision, the agent falls back to text-only planning using the accessibility tree.

---

## Environment Variables

Frontend build-time variables are defined in `.env` files under `frontend/`:

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8420` | Backend HTTP API base URL |
| `VITE_WS_BASE_URL` | `ws://localhost:8420` | Backend WebSocket base URL |

Create `frontend/.env.local` to override these for development.

---

## Type-Checking and Linting

```bash
# Type check (SvelteKit + svelte-check)
npm run check --prefix frontend

# Build (production)
npm run build --prefix frontend
```

---

## Common Issues

### Dev server cannot reach the backend

Ensure the backend is running and the proxy in `frontend/vite.config.ts` points to the correct port:

```typescript
server: {
  proxy: {
    "/api": "http://localhost:8420",
    "/ws": {
      target: "ws://localhost:8420",
      ws: true,
    },
  },
},
```

### WebLLM model fails to load

- Check that your browser supports WebGPU (`chrome://gpu` in Chrome).
- Try a smaller model.
- Disable browser extensions that may interfere with WebGPU.

### Static build not served by daemon

Make sure `frontend/dist` exists and the daemon is configured to mount static files from that directory. The default `src.api.server` setup includes a static file mount when the directory is present.

---

## Summary

- Run dev: `npm run dev --prefix frontend`
- Build: `npm run build --prefix frontend`
- Serve: `python -m src.api.server` (after building)
- WebSocket events stream live task updates.
- WebLLM runs in the browser without an API key.
- Browser vision (SoM) enables visual element grounding for web tasks.
- See [PROVIDERS.md](PROVIDERS.md) for the Python provider layer and [README.md](../README.md) for high-level usage.
