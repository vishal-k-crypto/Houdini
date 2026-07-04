"""
Task scheduler — pulls tasks from the priority queue and runs them through
the Houdini coordinator pipeline.

Supports:
- Configurable worker concurrency (default 1 for desktop automation)
- Graceful shutdown
- Timeout enforcement
- Event bridging to the API / dashboard
"""

import threading
import time
from typing import Any, Callable, Dict, Optional

from ..utils.logging import logger
from .queue import QueuedTask, TaskQueue, TaskState


class TaskScheduler:
    """
    Worker-pool scheduler that drains a ``TaskQueue``.

    For desktop automation the default concurrency is 1 (only one mouse/keyboard
    at a time). Increase ``max_workers`` for headless or multi-display setups.
    """

    def __init__(
        self,
        queue: TaskQueue,
        max_workers: int = 1,
        task_runner: Optional[Callable[[QueuedTask], Dict[str, Any]]] = None,
    ):
        self._queue = queue
        self._max_workers = max_workers
        self._task_runner = task_runner or _default_task_runner
        self._workers: list[threading.Thread] = []
        self._shutdown_event = threading.Event()
        self._active_tasks: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self):
        """Start the worker threads."""
        if self._workers:
            return  # already running
        self._shutdown_event.clear()
        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"scheduler-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
        logger.info(f"Scheduler started with {self._max_workers} worker(s)")

    def stop(self, timeout: float = 30.0):
        """Signal workers to stop and wait up to *timeout* seconds."""
        self._shutdown_event.set()
        for t in self._workers:
            t.join(timeout=timeout)
        self._workers.clear()
        logger.info("Scheduler stopped")

    @property
    def running(self) -> bool:
        return bool(self._workers) and not self._shutdown_event.is_set()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_tasks)

    # ── Worker loop ────────────────────────────────────────────────

    def _worker_loop(self):
        while not self._shutdown_event.is_set():
            task = self._queue.dequeue(timeout=1.0)
            if task is None:
                continue

            with self._lock:
                self._active_tasks[task.task_id] = threading.current_thread()

            try:
                self._execute(task)
            finally:
                with self._lock:
                    self._active_tasks.pop(task.task_id, None)

    def _execute(self, task: QueuedTask):
        logger.info(
            f"Scheduler: executing {task.task_id} "
            f"(priority={task.priority.name}): {task.description!r}"
        )
        try:
            # Enforce timeout
            result_container: Dict[str, Any] = {}
            error_container: Dict[str, str] = {}

            def _run():
                try:
                    result_container["result"] = self._task_runner(task)
                except Exception as exc:
                    error_container["error"] = str(exc)

            runner = threading.Thread(target=_run, daemon=True)
            runner.start()

            timeout = task.timeout_s or 3600  # default 1 hour
            runner.join(timeout=timeout)

            if runner.is_alive():
                # Task timed out
                self._queue.fail(task.task_id, f"Timed out after {timeout}s")
                return

            if "error" in error_container:
                self._queue.fail(task.task_id, error_container["error"])
            else:
                self._queue.complete(task.task_id, result_container.get("result"))

        except Exception as exc:
            logger.error(f"Scheduler error for {task.task_id}: {exc}", exc_info=True)
            self._queue.fail(task.task_id, str(exc))


# ── Default task runner ────────────────────────────────────────────


def _default_task_runner(task: QueuedTask) -> Dict[str, Any]:
    """
    Execute a Houdini task using the appropriate coordinator.

    This mirrors the logic in ``src/api/server.py:_run_task_sync``.
    """
    from ..utils.ollama_client import OllamaClient
    from config.settings import settings

    model = task.model or settings.ollama_default_model
    client = OllamaClient(model_name=model, cloud_endpoint=task.cloud_endpoint)

    if task.architecture == "langgraph":
        from ..loop.langgraph_coordinator import LangGraphCoordinator

        coordinator = LangGraphCoordinator(
            client=client,
            enable_thinking_window=False,
            max_iterations=100,
            checkpoint_path=task.checkpoint_path,
        )
    elif task.architecture == "legacy":
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
    else:
        from ..loop.adaptive_coordinator import AdaptiveLoopCoordinator

        coordinator = AdaptiveLoopCoordinator(
            client=client,
            enable_thinking_window=False,
            max_iterations=100,
        )

    return coordinator.execute(task.description)
