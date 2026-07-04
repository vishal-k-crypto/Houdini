"""
Houdini Agent — FastAPI HTTP Server

Exposes the CLI capabilities over HTTP for:
- Task submission (POST /api/tasks)
- Status polling (GET /api/tasks/{id})
- Results retrieval (GET /api/tasks/{id}/result)
- Live event streaming (WebSocket /ws or SSE GET /api/tasks/{id}/stream)
- Health check (GET /api/health)
- Provider listing (GET /api/providers)
- Settings (GET/POST /api/settings)

Run:
    python -m src.api.server              # default: 127.0.0.1:8420
    python -m src.api.server --host 0.0.0.0 --port 9000
"""

import asyncio
import os
import time
import uuid
import threading
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..utils.logging import logger
from .dashboard import router as dashboard_router, push_dashboard_event
from .auth import router as auth_router, require_viewer, require_operator, AUTH_ENABLED
from .websocket_manager import ws_manager
from ..providers.registry import registry, get_default_provider
from ..providers.router import ProviderRouter

# ── Hook event bus → task records + dashboard + WebSocket ─────────────


def _wire_event_bus():
    """Subscribe to internal events so they show up in the API, dashboard, and WebSocket."""
    try:
        from ..utils.event_bus import event_bus

        def _on_event(payload):
            push_dashboard_event(payload)
            ws_manager.broadcast(payload)
            # Also attach to the most-recently-started running task
            with _tasks_lock:
                running = [r for r in _tasks.values() if r.status == TaskStatus.RUNNING]
            if running:
                running[-1].push_event(payload)

        event_bus.subscribe("confidence", _on_event)
        event_bus.subscribe("thinking", _on_event)
        event_bus.subscribe("screenshot", _on_event)
        event_bus.subscribe("action", _on_event)
        event_bus.subscribe("status", _on_event)
    except Exception:
        pass


# Deferred call (executed after _tasks/_tasks_lock are defined)
_WIRE_BUS_PENDING = True


# ── Pydantic schemas ────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskSubmission(BaseModel):
    task: str = Field(..., description="Task description", min_length=1)
    provider: Optional[str] = Field(None, description="Provider id (openai, anthropic, gemini, ollama, ...)")
    model: Optional[str] = Field(None, description="Model name/alias")
    architecture: Optional[str] = Field(
        "adaptive", description="Architecture: adaptive | langgraph | legacy"
    )
    use_enhanced: bool = Field(True, description="Use enhanced executor")
    cloud_endpoint: Optional[str] = Field(None, description="Deprecated: provider base URL override")
    checkpoint_path: Optional[str] = Field(
        None, description="SQLite checkpoint path (langgraph only)"
    )


class SettingsUpdate(BaseModel):
    model_config = {"extra": "ignore"}

    default_provider: Optional[str] = None
    provider_keys: Optional[Dict[str, str]] = None
    provider_models: Optional[Dict[str, str]] = None
    smart_router_enabled: Optional[bool] = None
    smart_router_prefer_local: Optional[bool] = None
    smart_router_budget_cap_usd: Optional[float] = None
    smart_router_latency_budget_ms: Optional[float] = None


class TaskInfo(BaseModel):
    task_id: str
    task: str
    status: TaskStatus
    architecture: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_s: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)
    confidence_scores: List[Dict[str, Any]] = Field(default_factory=list)


class TaskListResponse(BaseModel):
    tasks: List[TaskInfo]
    total: int


class HealthResponse(BaseModel):
    status: str
    uptime_s: float
    tasks_total: int
    tasks_running: int
    tasks_completed: int
    tasks_failed: int
    default_provider: Optional[str] = None


# ── In-memory task store ────────────────────────────────────────────

class _TaskRecord:
    __slots__ = (
        "task_id", "task", "status", "architecture", "model", "provider",
        "use_enhanced", "cloud_endpoint", "checkpoint_path",
        "created_at", "started_at", "completed_at",
        "result", "events", "confidence_scores", "lock",
    )

    def __init__(self, task_id: str, sub: TaskSubmission):
        self.task_id = task_id
        self.task = sub.task
        self.status = TaskStatus.PENDING
        self.architecture = sub.architecture or "adaptive"
        self.model = sub.model
        self.provider = sub.provider
        self.use_enhanced = sub.use_enhanced
        self.cloud_endpoint = sub.cloud_endpoint
        self.checkpoint_path = sub.checkpoint_path
        self.created_at = datetime.now().isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.events: List[Dict[str, Any]] = []
        self.confidence_scores: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def to_info(self) -> TaskInfo:
        duration = None
        if self.started_at and self.completed_at:
            t0 = datetime.fromisoformat(self.started_at)
            t1 = datetime.fromisoformat(self.completed_at)
            duration = (t1 - t0).total_seconds()
        return TaskInfo(
            task_id=self.task_id,
            task=self.task,
            status=self.status,
            architecture=self.architecture,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            duration_s=duration,
            result=self.result,
            events=list(self.events),
            confidence_scores=list(self.confidence_scores),
        )

    def push_event(self, event: Dict[str, Any]):
        with self.lock:
            self.events.append(event)

    def push_confidence(self, score: Dict[str, Any]):
        with self.lock:
            self.confidence_scores.append(score)


_tasks: Dict[str, _TaskRecord] = {}
_tasks_lock = threading.Lock()
_start_time = time.time()

# Now that _tasks exists, wire up the event bus
_wire_event_bus()


def _get_task(task_id: str) -> _TaskRecord:
    with _tasks_lock:
        rec = _tasks.get(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return rec


# ── Provider factory ────────────────────────────────────────────────

def _get_provider_client(rec: _TaskRecord):
    """Build a provider client from a task record using the new registry/router."""
    from config.settings import settings

    # If smart routing is enabled and the user did not explicitly pick a provider,
    # let the SmartRouter choose based on task complexity and constraints.
    if (
        getattr(settings, "smart_router_enabled", False)
        and not rec.provider
        and not os.environ.get("HOUDINI_DEFAULT_PROVIDER")
    ):
        try:
            from ..providers.smart_router import smart_router
            decision = smart_router.route(rec.task, "worker")
            logger.info(
                f"SmartRouter selected {decision.provider_id}/{decision.model} for task: {decision.reason}"
            )
            return registry.create(decision.provider_id, model_name=decision.model or rec.model)
        except Exception as exc:
            logger.warning(f"SmartRouter failed: {exc}; falling back to manual selection")

    provider_id = rec.provider or os.environ.get("HOUDINI_DEFAULT_PROVIDER") or get_default_provider() or "ollama"
    model_name = rec.model

    try:
        provider = registry.create(provider_id, model_name=model_name)
        return provider
    except Exception as exc:
        logger.warning(f"Provider '{provider_id}' failed to instantiate: {exc}; falling back to ollama")
        from ..utils.ollama_client import OllamaClient
        return OllamaClient(model_name=model_name or "llama3.2")


# ── Background task runner ──────────────────────────────────────────

def _run_task_sync(rec: _TaskRecord):
    """Execute a task in a background thread."""
    from config.settings import settings

    rec.status = TaskStatus.RUNNING
    rec.started_at = datetime.now().isoformat()
    rec.push_event({"type": "started", "ts": rec.started_at})
    push_dashboard_event({"task_id": rec.task_id, "type": "started", "task": rec.task})

    client = _get_provider_client(rec)

    try:
        if rec.architecture == "langgraph":
            from ..loop.langgraph_coordinator import LangGraphCoordinator
            coordinator = LangGraphCoordinator(
                client=client,
                enable_thinking_window=False,
                max_iterations=100,
                checkpoint_path=rec.checkpoint_path,
            )
            rec.push_event({"type": "architecture", "value": "langgraph"})
        elif rec.architecture == "legacy":
            from ..loop.loop_coordinator import LoopCoordinator
            from ..planner.ollama_planner import OllamaPlanner
            from ..supervisor.ollama_supervisor import OllamaSupervisor
            planner = OllamaPlanner(client)
            supervisor = OllamaSupervisor(client)
            coordinator = LoopCoordinator(
                client=client,
                planner=planner,
                supervisor=supervisor,
                enable_supervisor=True,
                supervisor_mode="background",
                enable_thinking_window=False,
            )
            rec.push_event({"type": "architecture", "value": "legacy"})
        else:
            from ..loop.adaptive_coordinator import AdaptiveLoopCoordinator
            smart_router = None
            if getattr(settings, "smart_router_enabled", False):
                try:
                    from ..providers.smart_router import smart_router as _sr
                    smart_router = _sr
                except Exception:
                    pass
            coordinator = AdaptiveLoopCoordinator(
                client=client,
                enable_thinking_window=False,
                max_iterations=100,
                smart_router=smart_router,
            )
            rec.push_event({"type": "architecture", "value": "adaptive"})

        # Hook into coordinator events if possible (adaptive / langgraph expose state)
        result = coordinator.execute(rec.task)

        rec.result = result
        if result.get("success"):
            rec.status = TaskStatus.COMPLETED
            rec.push_event({"type": "completed", "success": True})
            push_dashboard_event({"task_id": rec.task_id, "type": "completed", "success": True})
        else:
            rec.status = TaskStatus.FAILED
            rec.push_event({
                "type": "completed",
                "success": False,
                "error": result.get("error", "Unknown"),
            })
            push_dashboard_event({
                "task_id": rec.task_id, "type": "failed",
                "error": result.get("error", "Unknown"),
            })
    except Exception as exc:
        logger.error(f"API task {rec.task_id} failed: {exc}", exc_info=True)
        rec.status = TaskStatus.FAILED
        rec.result = {"success": False, "error": str(exc)}
        rec.push_event({"type": "error", "error": str(exc)})
        push_dashboard_event({"task_id": rec.task_id, "type": "error", "error": str(exc)})
    finally:
        rec.completed_at = datetime.now().isoformat()


# ── FastAPI app ─────────────────────────────────────────────────────

app = FastAPI(
    title="Houdini Agent API",
    version="0.5.0",
    description="HTTP/WebSocket wrapper around the Houdini desktop-automation agent",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the dashboard router (WebSocket + /dashboard page)
app.include_router(dashboard_router)

# Mount the auth router (/auth/*)
app.include_router(auth_router)


# ── API routes (prefixed with /api) ──────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health():
    """System health and aggregate task stats."""
    with _tasks_lock:
        all_tasks = list(_tasks.values())
    return HealthResponse(
        status="ok",
        uptime_s=round(time.time() - _start_time, 1),
        tasks_total=len(all_tasks),
        tasks_running=sum(1 for t in all_tasks if t.status == TaskStatus.RUNNING),
        tasks_completed=sum(1 for t in all_tasks if t.status == TaskStatus.COMPLETED),
        tasks_failed=sum(1 for t in all_tasks if t.status == TaskStatus.FAILED),
        default_provider=get_default_provider(),
    )


@app.get("/api/providers", tags=["system"])
def list_providers():
    """List all registered providers and which ones are available."""
    available = registry.detect_available()
    providers = []
    for pid in registry.list_providers():
        adapter_class = registry.get(pid)
        models = []
        if adapter_class is not None:
            # list_models() is an instance method; show the default model instead.
            default_model = getattr(adapter_class, "DEFAULT_MODEL", None)
            if default_model:
                models = [default_model]
            # If the provider is available, try to get its live model list.
            if pid in available:
                try:
                    instance = registry.create(pid)
                    models = instance.list_models() or models
                except Exception:
                    pass
        providers.append(
            {
                "id": pid,
                "available": pid in available,
                "details": available.get(pid, {}),
                "models": models,
            }
        )
    return {
        "providers": providers,
        "default": get_default_provider(),
    }


@app.get("/api/skills", tags=["system"])
def list_skills(task: Optional[str] = None):
    """List available skills, optionally filtered by task relevance."""
    try:
        from ..skills import skill_registry

        skills = skill_registry.skills
        if task:
            matched = skill_registry.match(task, top_k=10)
            matched_ids = {s.id for s in matched}
            return {
                "skills": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                        "triggers": s.triggers,
                        "tags": s.tags,
                        "priority": s.priority,
                        "matched": s.id in matched_ids,
                    }
                    for s in skills
                ],
                "matched": [s.id for s in matched],
            }
        return {
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "triggers": s.triggers,
                    "tags": s.tags,
                    "priority": s.priority,
                    "matched": False,
                }
                for s in skills
            ]
        }
    except Exception as exc:
        logger.warning(f"Skill registry unavailable: {exc}")
        return {"skills": [], "error": str(exc)}


@app.get("/api/settings", tags=["system"])
def get_settings(_user=Depends(require_viewer)):
    """Return non-sensitive current settings."""
    from config.settings import settings
    return {
        "default_provider": os.environ.get("HOUDINI_DEFAULT_PROVIDER") or get_default_provider(),
        "available_providers": list(registry.detect_available().keys()),
        "ollama_default_model": getattr(settings, "ollama_default_model", None),
        "gemini_default_model": getattr(settings, "gemini_default_model", None),
        "webllm_enabled": os.environ.get("HOUDINI_WEBLLM_ENABLED", "false").lower() == "true",
        "smart_router": {
            "enabled": getattr(settings, "smart_router_enabled", False),
            "prefer_local": getattr(settings, "smart_router_prefer_local", False),
            "budget_cap_usd": getattr(settings, "smart_router_budget_cap_usd", None),
            "latency_budget_ms": getattr(settings, "smart_router_latency_budget_ms", None),
        },
    }


@app.post("/api/settings", tags=["system"])
def update_settings(body: SettingsUpdate, _user=Depends(require_operator)):
    """Apply non-persistent settings (keys are set in memory for the current process)."""
    from config.settings import settings as _settings
    if body.default_provider:
        os.environ["HOUDINI_DEFAULT_PROVIDER"] = body.default_provider
    if body.provider_keys:
        for key, value in body.provider_keys.items():
            os.environ[key.upper()] = value
    if body.provider_models:
        for key, value in body.provider_models.items():
            os.environ[f"HOUDINI_{key.upper()}_MODEL"] = value
    # Note: dataclasses are frozen, so in-memory settings changes are stored in env vars
    # and reflected via getattr fallbacks above.
    if body.smart_router_enabled is not None:
        os.environ["HOUDINI_SMART_ROUTER_ENABLED"] = str(body.smart_router_enabled).lower()
    if body.smart_router_prefer_local is not None:
        os.environ["HOUDINI_PREFER_LOCAL"] = str(body.smart_router_prefer_local).lower()
    if body.smart_router_budget_cap_usd is not None:
        os.environ["HOUDINI_BUDGET_CAP_USD"] = str(body.smart_router_budget_cap_usd)
    if body.smart_router_latency_budget_ms is not None:
        os.environ["HOUDINI_LATENCY_BUDGET_MS"] = str(body.smart_router_latency_budget_ms)

    # Re-sync the global smart router with the latest env vars
    try:
        from ..providers.smart_router import configure_from_env as _sync_smart_router
        _sync_smart_router()
    except Exception:
        pass
    return get_settings()


@app.post("/api/tasks", response_model=TaskInfo, status_code=202, tags=["tasks"])
def submit_task(body: TaskSubmission, _user=Depends(require_operator)):
    """Submit a new task for execution (returns immediately)."""
    task_id = uuid.uuid4().hex[:12]
    rec = _TaskRecord(task_id, body)
    with _tasks_lock:
        _tasks[task_id] = rec

    thread = threading.Thread(target=_run_task_sync, args=(rec,), daemon=True)
    thread.start()
    logger.info(f"API: task {task_id} queued — {body.task!r}")
    return rec.to_info()


@app.get("/api/tasks", response_model=TaskListResponse, tags=["tasks"])
def list_tasks(status: Optional[TaskStatus] = None, limit: int = 50, _user=Depends(require_viewer)):
    """List submitted tasks, optionally filtered by status."""
    with _tasks_lock:
        recs = list(_tasks.values())
    if status:
        recs = [r for r in recs if r.status == status]
    recs = sorted(recs, key=lambda r: r.created_at, reverse=True)[:limit]
    return TaskListResponse(tasks=[r.to_info() for r in recs], total=len(recs))


@app.get("/api/tasks/{task_id}", response_model=TaskInfo, tags=["tasks"])
def get_task(task_id: str):
    """Get full details for a task including events and confidence scores."""
    return _get_task(task_id).to_info()


@app.get("/api/tasks/{task_id}/result", tags=["tasks"])
def get_task_result(task_id: str):
    """Get just the result payload (blocks concept: returns 202 while running)."""
    rec = _get_task(task_id)
    if rec.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        return {"task_id": task_id, "status": rec.status.value, "result": None}
    return {"task_id": task_id, "status": rec.status.value, "result": rec.result}


@app.get("/api/tasks/{task_id}/stream", tags=["tasks"])
async def stream_task_events(task_id: str):
    """
    Server-Sent Events stream for live task monitoring.

    Emits JSON events as they occur. Closes when the task completes.
    """
    rec = _get_task(task_id)

    async def _generate():
        seen = 0
        while True:
            with rec.lock:
                new_events = rec.events[seen:]
                seen = len(rec.events)
            for ev in new_events:
                yield f"data: {_json_dumps(ev)}\n\n"
            if rec.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                yield f"data: {_json_dumps({'type': 'done', 'status': rec.status.value})}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(_generate(), media_type="text/event-stream")


@app.delete("/api/tasks/{task_id}", tags=["tasks"])
def delete_task(task_id: str):
    """Remove a completed/failed task from memory."""
    rec = _get_task(task_id)
    if rec.status == TaskStatus.RUNNING:
        raise HTTPException(400, "Cannot delete a running task")
    with _tasks_lock:
        _tasks.pop(task_id, None)
    return {"deleted": task_id}


# ── WebSocket endpoint ─────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_manager.connect(websocket)
    try:
        # Send recent history so new clients can catch up
        for ev in ws_manager.recent_events(limit=100):
            await websocket.send_text(_json_dumps(ev))
        while True:
            # Keep connection alive and handle client messages (optional)
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                msg = {}
            if msg.get("type") == "ping":
                await websocket.send_text(_json_dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


# ── Static frontend serving ─────────────────────────────────────────

_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")


@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the built frontend."""
    index = os.path.join(_frontend_dist, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Houdini Agent API is running. Frontend not built."}


@app.get("/{path:path}", include_in_schema=False)
async def serve_static(path: str):
    """Serve static frontend assets."""
    file_path = os.path.join(_frontend_dist, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    index = os.path.join(_frontend_dist, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Houdini Agent API is running. Frontend not built."}


# ── Benchmark endpoint ───────────────────────────────────────────────

class BenchmarkRequest(BaseModel):
    tag: Optional[str] = None
    task_id: Optional[str] = None
    architecture: str = "adaptive"
    provider: Optional[str] = None
    model: Optional[str] = None
    cloud_endpoint: Optional[str] = None
    verify_with_llm: bool = False
    generate_skills_on_failure: bool = False


class BenchmarkTaskInfo(BaseModel):
    id: str
    description: str
    tags: List[str]
    expected_app: Optional[str] = None
    timeout_s: float = 120.0
    verify_hint: Optional[str] = None


@app.get("/api/benchmarks/tasks", tags=["benchmark"])
def list_benchmark_tasks(task: Optional[str] = None, tag: Optional[str] = None):
    """List all available benchmark tasks, optionally filtered by query or tag."""
    from ..benchmark import BENCHMARK_TASKS

    tasks = list(BENCHMARK_TASKS)
    if tag:
        tasks = [t for t in tasks if tag in t.tags]
    if task:
        task_l = task.lower()
        tasks = [t for t in tasks if task_l in t.description.lower() or task_l in t.id.lower()]
    return {
        "tasks": [
            BenchmarkTaskInfo(
                id=t.id,
                description=t.description,
                tags=t.tags,
                expected_app=t.expected_app,
                timeout_s=t.timeout_s,
                verify_hint=t.verify_hint,
            )
            for t in tasks
        ],
        "total": len(tasks),
    }


@app.post("/api/benchmarks/run", tags=["benchmark"])
def run_benchmark_v2(body: BenchmarkRequest, background_tasks: BackgroundTasks, _user=Depends(require_operator)):
    """
    Kick off a benchmark run in the background.
    Returns immediately with a run_id; poll GET /api/benchmarks/results/{run_id}.
    """
    from ..benchmark import BENCHMARK_TASKS, BenchmarkRunner
    from dataclasses import asdict

    tasks = list(BENCHMARK_TASKS)
    if body.tag:
        tasks = [t for t in tasks if body.tag in t.tags]
    if body.task_id:
        tasks = [t for t in tasks if t.id == body.task_id]
    if not tasks:
        raise HTTPException(404, "No matching benchmark tasks")

    runner = BenchmarkRunner(
        tasks=tasks,
        provider=body.provider,
        model=body.model,
        architecture=body.architecture,
        cloud_endpoint=body.cloud_endpoint,
        verify_with_llm=body.verify_with_llm,
        generate_skills_on_failure=body.generate_skills_on_failure,
    )

    import uuid
    run_id = uuid.uuid4().hex[:12]

    def _bg():
        report = runner.run()
        _benchmark_results[run_id] = asdict(report)

    background_tasks.add_task(_bg)
    return {"run_id": run_id, "tasks": len(tasks), "status": "started"}


# Backwards-compatible alias
@app.post("/api/benchmark", tags=["benchmark"])
def run_benchmark_compat(body: BenchmarkRequest, background_tasks: BackgroundTasks, _user=Depends(require_operator)):
    """Deprecated: use /api/benchmarks/run instead."""
    return run_benchmark_v2(body, background_tasks, _user)


_benchmark_results: Dict[str, Any] = {}
_benchmark_results_lock = threading.Lock()


@app.get("/api/benchmarks/results/{run_id}", tags=["benchmark"])
def get_benchmark_result_v2(run_id: str):
    """Poll for benchmark results."""
    with _benchmark_results_lock:
        result = _benchmark_results.get(run_id)
    if result is None:
        return {"run_id": run_id, "status": "running"}
    return {"run_id": run_id, "status": "complete", "report": result}


@app.get("/api/benchmark/{run_id}", tags=["benchmark"])
def get_benchmark_result_compat(run_id: str):
    """Deprecated: use /api/benchmarks/results/{run_id} instead."""
    return get_benchmark_result_v2(run_id)


# ── Smart router endpoints ───────────────────────────────────────────

class RouterDecisionRequest(BaseModel):
    task: str = Field(..., min_length=1)
    role: str = Field("worker", description="planner | supervisor | vision | worker")
    require_vision: bool = False
    require_tools: bool = False
    require_local: bool = False


@app.post("/api/router/decision", tags=["router"])
def get_router_decision(body: RouterDecisionRequest, _user=Depends(require_viewer)):
    """Ask the smart router which provider/model it would select for a task/role."""
    from ..providers.smart_router import smart_router
    try:
        decision = smart_router.route(
            body.task,
            body.role,
            require_vision=body.require_vision,
            require_tools=body.require_tools,
            require_local=body.require_local,
        )
        return {
            "role": decision.role,
            "provider": decision.provider_id,
            "model": decision.model,
            "reason": decision.reason,
            "local": decision.local,
            "supports_vision": decision.supports_vision,
            "estimated_cost_usd": decision.estimated_cost_usd,
            "estimated_latency_ms": decision.estimated_latency_ms,
        }
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/router/usage", tags=["router"])
def get_router_usage(_user=Depends(require_viewer)):
    """Return aggregate usage/cost summary from the smart router."""
    from ..providers.smart_router import smart_router
    return smart_router.usage_summary()


# ── Skill generation endpoint ────────────────────────────────────────

class SkillGenerationRequest(BaseModel):
    task: str = Field(..., min_length=1)
    error: Optional[str] = None


@app.post("/api/skills/generate-from-failure", tags=["skills"])
def generate_skill_from_failure_endpoint(body: SkillGenerationRequest, _user=Depends(require_operator)):
    """Generate and save a skill from a failed task description and error."""
    from ..skills.generator import generate_skill_from_failure
    try:
        result = generate_skill_from_failure(task=body.task, error=body.error)
        return {
            "skill_id": result["skill_id"],
            "path": str(result["path"]),
            "skill_text": result["skill_text"],
        }
    except Exception as exc:
        logger.error(f"Skill generation failed: {exc}")
        raise HTTPException(500, f"Skill generation failed: {exc}")


# ── Task queue / scheduler endpoints ─────────────────────────────────

from ..scheduling.queue import TaskQueue, TaskPriority, TaskState as QTaskState
from ..scheduling.scheduler import TaskScheduler

_task_queue = TaskQueue(max_size=1000)
_scheduler = TaskScheduler(queue=_task_queue, max_workers=1)


def _ensure_scheduler():
    """Lazily start the scheduler on first queue endpoint call."""
    if not _scheduler.running:
        # Bridge queue events → dashboard
        def _on_q_event(task):
            push_dashboard_event({
                "task_id": task.task_id,
                "type": f"queue_{task.state}",
                "description": task.description,
                "priority": task.priority.name,
            })

        for evt in ("enqueued", "started", "completed", "failed", "cancelled"):
            _task_queue.on(evt, _on_q_event)

        _scheduler.start()


class QueueSubmission(BaseModel):
    task: str = Field(..., min_length=1)
    priority: str = Field("normal", description="critical|high|normal|low|background")
    model: Optional[str] = None
    architecture: str = "adaptive"
    use_enhanced: bool = True
    cloud_endpoint: Optional[str] = None
    checkpoint_path: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    max_retries: int = 1
    timeout_s: Optional[float] = None


_PRIORITY_MAP = {
    "critical": TaskPriority.CRITICAL,
    "high": TaskPriority.HIGH,
    "normal": TaskPriority.NORMAL,
    "low": TaskPriority.LOW,
    "background": TaskPriority.BACKGROUND,
}


class QueueTaskInfo(BaseModel):
    task_id: str
    description: str
    priority: str
    state: str
    created_at: str
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 1


def _qtask_to_info(t) -> QueueTaskInfo:
    return QueueTaskInfo(
        task_id=t.task_id,
        description=t.description,
        priority=t.priority.name.lower(),
        state=t.state,
        created_at=t.created_at,
        queued_at=t.queued_at,
        started_at=t.started_at,
        completed_at=t.completed_at,
        result=t.result,
        error=t.error,
        retry_count=t.retry_count,
        max_retries=t.max_retries,
    )


@app.post("/api/queue/tasks", response_model=QueueTaskInfo, status_code=202, tags=["queue"])
def enqueue_task(body: QueueSubmission, _user=Depends(require_operator)):
    """Submit a task to the priority queue."""
    _ensure_scheduler()
    priority = _PRIORITY_MAP.get(body.priority.lower(), TaskPriority.NORMAL)
    task = _task_queue.enqueue(
        description=body.task,
        priority=priority,
        model=body.model,
        architecture=body.architecture,
        use_enhanced=body.use_enhanced,
        cloud_endpoint=body.cloud_endpoint,
        checkpoint_path=body.checkpoint_path,
        depends_on=body.depends_on,
        max_retries=body.max_retries,
        timeout_s=body.timeout_s,
    )
    return _qtask_to_info(task)


@app.get("/api/queue/tasks", tags=["queue"])
def list_queue_tasks(state: Optional[str] = None, limit: int = 100):
    """List tasks in the queue, optionally filtered by state."""
    tasks = _task_queue.list_tasks(state=state, limit=limit)
    return {"tasks": [_qtask_to_info(t) for t in tasks], "total": len(tasks)}


@app.get("/api/queue/tasks/{task_id}", response_model=QueueTaskInfo, tags=["queue"])
def get_queue_task(task_id: str):
    """Get details for a queued task."""
    task = _task_queue.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Queue task {task_id} not found")
    return _qtask_to_info(task)


@app.delete("/api/queue/tasks/{task_id}", tags=["queue"])
def cancel_queue_task(task_id: str):
    """Cancel a queued (not yet running) task."""
    if not _task_queue.cancel(task_id):
        raise HTTPException(400, "Task cannot be cancelled (already running or completed)")
    return {"cancelled": task_id}


@app.put("/api/queue/tasks/{task_id}/priority", tags=["queue"])
def reprioritise_queue_task(task_id: str, priority: str):
    """Change the priority of a queued task."""
    new_pri = _PRIORITY_MAP.get(priority.lower())
    if new_pri is None:
        raise HTTPException(400, f"Invalid priority: {priority}")
    if not _task_queue.reprioritise(task_id, new_pri):
        raise HTTPException(400, "Cannot reprioritise (task not in queued state)")
    return {"task_id": task_id, "new_priority": priority}


@app.post("/api/queue/pause", tags=["queue"])
def pause_queue():
    """Pause the task queue — workers stop pulling new tasks."""
    _task_queue.pause()
    return {"paused": True}


@app.post("/api/queue/resume", tags=["queue"])
def resume_queue():
    """Resume the task queue."""
    _task_queue.resume()
    return {"paused": False}


@app.get("/api/queue/stats", tags=["queue"])
def queue_stats():
    """Queue statistics."""
    _ensure_scheduler()
    return {
        "stats": _task_queue.stats(),
        "size": _task_queue.size,
        "total": _task_queue.total,
        "paused": _task_queue.paused,
        "active_workers": _scheduler.active_count,
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _json_dumps(obj):
    import json
    return json.dumps(obj, default=str)


# ── CLI entry point ──────────────────────────────────────────────────

def _cli():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Houdini Agent HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    logger.info(f"🌐 Starting Houdini API on {args.host}:{args.port}")
    uvicorn.run(
        "src.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    _cli()
