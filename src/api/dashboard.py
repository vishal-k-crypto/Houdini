"""
Houdini Agent — Web Monitoring Dashboard

Real-time dashboard for observing:
- Task execution progress
- Supervisor decisions & interventions
- Confidence scores over time
- Active / historical task list

Served at GET /dashboard by the FastAPI server.
Uses WebSocket at /ws for live updates, with SSE fallback.
"""

import json
import asyncio
import time
import threading
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ..utils.logging import logger

router = APIRouter(tags=["dashboard"])

# ── WebSocket hub ────────────────────────────────────────────────────

class _Hub:
    """Broadcast events to all connected dashboard clients."""

    def __init__(self):
        self._clients: Set[WebSocket] = set()
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self._clients.add(ws)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, payload: dict):
        data = json.dumps(payload, default=str)
        with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(data)
            except Exception:
                self.disconnect(ws)


hub = _Hub()


def push_dashboard_event(event: dict):
    """
    Thread-safe helper called from sync task runners to push
    events into the WebSocket hub.  Creates a one-shot event loop
    if there is none on the current thread.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(hub.broadcast(event))
    except RuntimeError:
        # No running loop on this thread — fire-and-forget
        try:
            asyncio.run(hub.broadcast(event))
        except Exception:
            pass


# ── WebSocket endpoint ──────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            # Keep connection alive; ignore inbound messages
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)


# ── Dashboard HTML ──────────────────────────────────────────────────

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Houdini — Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;
  --muted:#8b949e;--accent:#58a6ff;--green:#3fb950;--red:#f85149;
  --orange:#d29922;--purple:#bc8cff}
body{background:var(--bg);color:var(--text);font-family:'SF Mono',
  'Fira Code',Menlo,monospace;font-size:13px;padding:16px}
h1{font-size:20px;margin-bottom:12px;color:var(--accent)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;
  padding:14px}
.card h2{font-size:14px;color:var(--muted);margin-bottom:8px;
  text-transform:uppercase;letter-spacing:.5px}
.stat{font-size:28px;font-weight:700}
.stat.green{color:var(--green)}.stat.red{color:var(--red)}
.stat.orange{color:var(--orange)}.stat.blue{color:var(--accent)}

/* Task table */
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase}
td{font-size:12px}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;
  font-weight:600}
.badge.running{background:#1f6feb33;color:var(--accent)}
.badge.completed{background:#23883033;color:var(--green)}
.badge.failed{background:#da363333;color:var(--red)}
.badge.pending{background:#d2992233;color:var(--orange)}

/* Confidence chart (simple bar) */
.conf-bar{display:flex;align-items:center;gap:6px;margin:3px 0}
.conf-bar .bar{height:8px;border-radius:4px;transition:width .3s}
.conf-bar .label{min-width:36px;text-align:right;font-size:11px;color:var(--muted)}

/* Event log */
#event-log{max-height:340px;overflow-y:auto;font-size:11px;padding:6px;
  background:#0d1117;border:1px solid var(--border);border-radius:6px}
#event-log div{padding:2px 4px;border-bottom:1px solid #21262d}
#event-log .ts{color:var(--muted);margin-right:6px}

/* Connection indicator */
#conn{position:fixed;top:10px;right:16px;font-size:11px;display:flex;
  align-items:center;gap:5px}
#conn .dot{width:8px;height:8px;border-radius:50%;background:var(--red)}
#conn .dot.ok{background:var(--green)}
</style>
</head>
<body>

<div id="conn"><span class="dot" id="dot"></span><span id="conn-label">disconnected</span></div>
<h1>&#x1f3a9; Houdini Agent Dashboard</h1>

<div class="grid">
  <div class="card"><h2>Tasks</h2>
    <span class="stat blue" id="s-total">0</span> total &nbsp;
    <span class="stat orange" id="s-running">0</span> running &nbsp;
    <span class="stat green" id="s-completed">0</span> done &nbsp;
    <span class="stat red" id="s-failed">0</span> failed
  </div>
  <div class="card"><h2>Uptime</h2>
    <span class="stat" id="s-uptime">—</span>
  </div>
</div>

<div class="grid">
  <div class="card" style="grid-column:span 2">
    <h2>Active &amp; Recent Tasks</h2>
    <table>
      <thead><tr><th>ID</th><th>Task</th><th>Arch</th><th>Status</th><th>Duration</th><th>Confidence</th></tr></thead>
      <tbody id="task-body"></tbody>
    </table>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>Confidence Scores</h2>
    <div id="conf-container"><em style="color:var(--muted)">Waiting for data…</em></div>
  </div>
  <div class="card">
    <h2>Live Event Log</h2>
    <div id="event-log"><em style="color:var(--muted)">Waiting for events…</em></div>
  </div>
</div>

<script>
const API = location.origin;
const WS_URL = `ws://${location.host}/ws`;

/* ── State ───────────────────────────── */
let tasks = {};
let ws;

/* ── WebSocket ───────────────────────── */
function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => { setConn(true); };
  ws.onclose = () => { setConn(false); setTimeout(connectWS, 2000); };
  ws.onerror = () => { ws.close(); };
  ws.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data);
      appendEvent(ev);
      if (ev.task_id) {
        // Refresh that task
        fetchTask(ev.task_id);
      }
    } catch(_){}
  };
}

function setConn(ok) {
  document.getElementById('dot').className = 'dot' + (ok ? ' ok' : '');
  document.getElementById('conn-label').textContent = ok ? 'connected' : 'reconnecting…';
}

/* ── Polling (fallback & initial load) ── */
async function fetchHealth() {
  try {
    const r = await fetch(API + '/health');
    const d = await r.json();
    document.getElementById('s-total').textContent = d.tasks_total;
    document.getElementById('s-running').textContent = d.tasks_running;
    document.getElementById('s-completed').textContent = d.tasks_completed;
    document.getElementById('s-failed').textContent = d.tasks_failed;
    const m = Math.floor(d.uptime_s / 60);
    const s = Math.floor(d.uptime_s % 60);
    document.getElementById('s-uptime').textContent = `${m}m ${s}s`;
  } catch(_){}
}

async function fetchTasks() {
  try {
    const r = await fetch(API + '/tasks?limit=20');
    const d = await r.json();
    d.tasks.forEach(t => { tasks[t.task_id] = t; });
    renderTasks();
  } catch(_){}
}

async function fetchTask(id) {
  try {
    const r = await fetch(API + '/tasks/' + id);
    const t = await r.json();
    tasks[t.task_id] = t;
    renderTasks();
    renderConfidence(t);
  } catch(_){}
}

/* ── Renderers ───────────────────────── */
function renderTasks() {
  const tbody = document.getElementById('task-body');
  const sorted = Object.values(tasks).sort((a,b) => b.created_at.localeCompare(a.created_at));
  tbody.innerHTML = sorted.map(t => {
    const dur = t.duration_s != null ? t.duration_s.toFixed(1) + 's' : '—';
    const lastConf = t.confidence_scores?.length
      ? t.confidence_scores[t.confidence_scores.length-1]?.score?.toFixed(1) ?? '—'
      : '—';
    return `<tr>
      <td>${t.task_id}</td>
      <td title="${esc(t.task)}">${esc(t.task.slice(0,60))}</td>
      <td>${t.architecture}</td>
      <td><span class="badge ${t.status}">${t.status}</span></td>
      <td>${dur}</td>
      <td>${lastConf}</td>
    </tr>`;
  }).join('');
}

function renderConfidence(task) {
  if (!task.confidence_scores?.length) return;
  const el = document.getElementById('conf-container');
  el.innerHTML = task.confidence_scores.slice(-15).map(c => {
    const pct = Math.min(100, (c.score / 10) * 100);
    const color = c.score >= 7 ? 'var(--green)' : c.score >= 5 ? 'var(--orange)' : 'var(--red)';
    return `<div class="conf-bar">
      <span class="label">${c.score?.toFixed(1) ?? '?'}</span>
      <div class="bar" style="width:${pct}%;background:${color}"></div>
      <span style="color:var(--muted);font-size:10px">${esc((c.action||'').slice(0,40))}</span>
    </div>`;
  }).join('');
}

function appendEvent(ev) {
  const el = document.getElementById('event-log');
  if (el.querySelector('em')) el.innerHTML = '';
  const d = document.createElement('div');
  const now = new Date().toLocaleTimeString();
  d.innerHTML = `<span class="ts">${now}</span>${esc(JSON.stringify(ev))}`;
  el.prepend(d);
  while (el.children.length > 200) el.removeChild(el.lastChild);
}

function esc(s) { const d = document.createElement('span'); d.textContent = s; return d.innerHTML; }

/* ── Boot ────────────────────────────── */
connectWS();
fetchHealth();
fetchTasks();
setInterval(fetchHealth, 5000);
setInterval(fetchTasks, 8000);
</script>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the monitoring dashboard."""
    return _DASHBOARD_HTML
