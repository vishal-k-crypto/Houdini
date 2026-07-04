# Houdini Agent — Frontend Developer Guide

Houdini ships with a local-first web frontend built with **Vite + React + TypeScript**. It can connect to the Houdini daemon, submit tasks, stream live events, and optionally run frontier models in the browser via **WebLLM**.

---

## Project Layout

```
frontend/
├── public/                 # Static assets
├── src/
│   ├── main.tsx            # App entry
│   ├── App.tsx             # Root layout
│   ├── components/         # UI components
│   ├── hooks/              # React hooks (WebSocket, etc.)
│   ├── providers/          # WebLLM integration
│   └── types/              # TypeScript types
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
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

By default, the dev server runs on `http://localhost:5173`. The frontend proxies API calls to `http://localhost:8420` if configured in `vite.config.ts`.

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

This produces a `frontend/dist` directory with static HTML, CSS, and JS assets.

### Serve from the Daemon

The Houdini FastAPI server can serve the built frontend from `frontend/dist` if static file serving is enabled. This is the recommended way to run Houdini in a standalone mode.

```bash
# Build once
npm run build --prefix frontend

# Start the daemon — serves the frontend at /
python -m src.api.server
```

Then open `http://localhost:8420`. The API remains available under `/`, `/health`, `/tasks`, etc.

> **Note:** If the frontend build is missing, the daemon still serves the HTTP API and dashboard endpoints.

---

## WebSocket Event Schema

The frontend connects to the daemon via WebSocket (typically at `ws://localhost:8420/ws`) to receive live task events.

### Connection

```javascript
const ws = new WebSocket("ws://localhost:8420/ws");

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(message.type, message);
};
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

## WebLLM Integration

WebLLM allows running models directly in the browser without any backend API key.

### Supported Models

Recommended WebLLM models:

- `Llama-3.1-8B-Instruct`
- `Phi-4-mini-instruct`
- `Qwen2.5-7B-Instruct`

### Loading a Model

```typescript
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
# Type check
npm run type-check --prefix frontend

# Lint
npm run lint --prefix frontend

# Build
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
- See [PROVIDERS.md](PROVIDERS.md) for the Python provider layer and [README.md](../README.md) for high-level usage.
