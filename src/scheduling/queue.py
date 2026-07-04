"""
Priority task queue with thread-safe operations.
"""

import heapq
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

from ..utils.logging import logger


class TaskPriority(IntEnum):
    """Task priority levels (lower value = higher priority)."""

    CRITICAL = 0
    HIGH = 10
    NORMAL = 20
    LOW = 30
    BACKGROUND = 40


class TaskState:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass(order=False)
class QueuedTask:
    """A task in the priority queue."""

    task_id: str
    description: str
    priority: TaskPriority
    state: str = TaskState.QUEUED

    # Execution details
    model: Optional[str] = None
    architecture: str = "adaptive"
    use_enhanced: bool = True
    cloud_endpoint: Optional[str] = None
    checkpoint_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Result
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Scheduling hints
    depends_on: List[str] = field(default_factory=list)  # task_ids this depends on
    max_retries: int = 1
    retry_count: int = 0
    timeout_s: Optional[float] = None  # max execution time

    # Internal: for heap ordering
    _seq: int = 0  # tie-breaker for same-priority tasks

    def __lt__(self, other: "QueuedTask") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self._seq < other._seq

    def __le__(self, other: "QueuedTask") -> bool:
        return self == other or self < other


class TaskQueue:
    """
    Thread-safe priority queue for task scheduling.

    Tasks are ordered by priority (lower = higher priority) and then
    insertion order (FIFO within same priority).
    """

    def __init__(self, max_size: int = 1000):
        self._heap: List[QueuedTask] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._seq = 0
        self._max_size = max_size
        self._tasks: Dict[str, QueuedTask] = {}  # task_id → task for O(1) lookup
        self._paused = False
        self._callbacks: Dict[str, List[Callable]] = {
            "enqueued": [],
            "started": [],
            "completed": [],
            "failed": [],
            "cancelled": [],
        }

    # ── Enqueue / dequeue ──────────────────────────────────────────

    def enqueue(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        task_id: Optional[str] = None,
        **kwargs,
    ) -> QueuedTask:
        """Add a task to the queue. Returns the created ``QueuedTask``."""
        with self._lock:
            if len(self._heap) >= self._max_size:
                raise RuntimeError(f"Queue full ({self._max_size} tasks)")

            tid = task_id or uuid.uuid4().hex[:12]
            if tid in self._tasks:
                raise ValueError(f"Duplicate task_id: {tid}")

            task = QueuedTask(
                task_id=tid,
                description=description,
                priority=priority,
                queued_at=datetime.now().isoformat(),
                _seq=self._seq,
                **kwargs,
            )
            self._seq += 1
            heapq.heappush(self._heap, task)
            self._tasks[tid] = task
            self._not_empty.notify()

        logger.info(f"Queue: enqueued {tid} (priority={priority.name}): {description!r}")
        self._fire("enqueued", task)
        return task

    def dequeue(self, timeout: Optional[float] = None) -> Optional[QueuedTask]:
        """
        Remove and return the highest-priority task that is ready.

        Blocks up to *timeout* seconds if the queue is empty.
        Returns ``None`` on timeout or if the queue is paused.
        """
        with self._not_empty:
            deadline = time.monotonic() + timeout if timeout else None
            while True:
                if self._paused:
                    return None

                # Find first task whose dependencies are met
                task = self._pick_ready()
                if task is not None:
                    return task

                # Wait for new items
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                self._not_empty.wait(timeout=remaining)

    def _pick_ready(self) -> Optional[QueuedTask]:
        """Pop the first queued task whose dependencies are satisfied (lock held)."""
        # Rebuild heap without cancelled/completed tasks
        ready_idx = None
        for i, task in enumerate(self._heap):
            if task.state != TaskState.QUEUED:
                continue
            if self._deps_met(task):
                ready_idx = i
                break

        if ready_idx is None:
            return None

        # Swap with end and pop (maintain heap property later)
        task = self._heap[ready_idx]
        self._heap[ready_idx] = self._heap[-1]
        self._heap.pop()
        if self._heap:
            heapq.heapify(self._heap)

        task.state = TaskState.RUNNING
        task.started_at = datetime.now().isoformat()
        self._fire("started", task)
        return task

    def _deps_met(self, task: QueuedTask) -> bool:
        for dep_id in task.depends_on:
            dep = self._tasks.get(dep_id)
            if dep is None or dep.state != TaskState.COMPLETED:
                return False
        return True

    # ── Task lifecycle ─────────────────────────────────────────────

    def complete(self, task_id: str, result: Optional[Dict[str, Any]] = None):
        """Mark a task as completed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.state = TaskState.COMPLETED
            task.completed_at = datetime.now().isoformat()
            task.result = result
            # Notify waiters — dependent tasks may now be ready
            self._not_empty.notify_all()
        self._fire("completed", task)

    def fail(self, task_id: str, error: str):
        """Mark a task as failed. Re-enqueues if retries remain."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                task.state = TaskState.QUEUED
                task.started_at = None
                task.error = error
                heapq.heappush(self._heap, task)
                self._not_empty.notify()
                logger.info(
                    f"Queue: retrying {task_id} "
                    f"({task.retry_count}/{task.max_retries})"
                )
                return

            task.state = TaskState.FAILED
            task.completed_at = datetime.now().isoformat()
            task.error = error
            self._not_empty.notify_all()
        self._fire("failed", task)

    def cancel(self, task_id: str) -> bool:
        """Cancel a queued task. Returns False if already running/completed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.state != TaskState.QUEUED:
                return False
            task.state = TaskState.CANCELLED
            task.completed_at = datetime.now().isoformat()
        self._fire("cancelled", task)
        return True

    # ── Queue management ───────────────────────────────────────────

    def pause(self):
        """Pause the queue — workers will stop pulling tasks."""
        with self._lock:
            self._paused = True
            logger.info("Queue: paused")

    def resume(self):
        """Resume the queue."""
        with self._lock:
            self._paused = False
            self._not_empty.notify_all()
            logger.info("Queue: resumed")

    @property
    def paused(self) -> bool:
        return self._paused

    def reprioritise(self, task_id: str, new_priority: TaskPriority) -> bool:
        """Change the priority of a queued task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.state != TaskState.QUEUED:
                return False
            task.priority = new_priority
            heapq.heapify(self._heap)
        return True

    # ── Queries ────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[QueuedTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(
        self,
        state: Optional[str] = None,
        limit: int = 100,
    ) -> List[QueuedTask]:
        with self._lock:
            tasks = list(self._tasks.values())
        if state:
            tasks = [t for t in tasks if t.state == state]
        tasks.sort(key=lambda t: (t.priority, t._seq))
        return tasks[:limit]

    @property
    def size(self) -> int:
        """Number of queued (waiting) tasks."""
        with self._lock:
            return sum(1 for t in self._heap if t.state == TaskState.QUEUED)

    @property
    def total(self) -> int:
        """Total tasks tracked (all states)."""
        with self._lock:
            return len(self._tasks)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            all_tasks = list(self._tasks.values())
        counts: Dict[str, int] = {}
        for t in all_tasks:
            counts[t.state] = counts.get(t.state, 0) + 1
        return counts

    # ── Event callbacks ────────────────────────────────────────────

    def on(self, event: str, callback: Callable):
        """Register a callback for queue events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _fire(self, event: str, task: QueuedTask):
        for cb in self._callbacks.get(event, []):
            try:
                cb(task)
            except Exception as exc:
                logger.error(f"Queue callback error ({event}): {exc}")
