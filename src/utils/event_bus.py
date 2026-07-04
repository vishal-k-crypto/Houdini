"""
Houdini Agent — Event Bus

Lightweight publish-subscribe bus so coordinators can emit events
(confidence scores, phase changes, supervisor decisions) that the
API server and dashboard can observe without tight coupling.

Usage from coordinators:
    from ..utils.event_bus import event_bus
    event_bus.emit("confidence", {"task_id": ..., "score": 7.2, ...})

Usage from API server:
    from ..utils.event_bus import event_bus
    event_bus.subscribe("confidence", my_handler)
"""

import threading
from typing import Any, Callable, Dict, List

_Callback = Callable[[Dict[str, Any]], None]


class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[_Callback]] = {}
        self._lock = threading.Lock()

    def subscribe(self, topic: str, callback: _Callback):
        with self._lock:
            self._subs.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic: str, callback: _Callback):
        with self._lock:
            cbs = self._subs.get(topic, [])
            try:
                cbs.remove(callback)
            except ValueError:
                pass

    def emit(self, topic: str, payload: Dict[str, Any]):
        with self._lock:
            cbs = list(self._subs.get(topic, []))
        for cb in cbs:
            try:
                cb(payload)
            except Exception:
                pass  # never let a subscriber crash the emitter


# Singleton
event_bus = EventBus()
