"""
WebSocket manager for Houdini Agent.

Maintains a registry of connected frontend clients and forwards events
from the internal event bus without blocking the executor loop.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from typing import Any, Dict, List, Optional, Set

from ..utils.logging import logger


class WebSocketManager:
    """Manages active WebSocket connections and event broadcasting."""

    def __init__(self, max_history: int = 200):
        self.connections: Set[Any] = set()
        self._lock = threading.Lock()
        self._history: deque = deque(maxlen=max_history)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def connect(self, websocket):
        with self._lock:
            self.connections.add(websocket)
        logger.info(f"🧦 WebSocket connected: {id(websocket)}")

    def disconnect(self, websocket):
        with self._lock:
            self.connections.discard(websocket)
        logger.info(f"🧦 WebSocket disconnected: {id(websocket)}")

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    def broadcast(self, event: Dict[str, Any]):
        """Broadcast an event to all connected WebSockets (thread-safe)."""
        serialized = self._serialize(event)
        with self._lock:
            self._history.append(event)
            connections = list(self.connections)

        for ws in connections:
            try:
                if hasattr(ws, "send_text"):
                    # FastAPI WebSocket
                    coro = ws.send_text(serialized)
                    self._schedule(coro)
                elif asyncio.iscoroutinefunction(getattr(ws, "send", None)):
                    self._schedule(ws.send(serialized))
                else:
                    sync_send = getattr(ws, "send", None)
                    if sync_send:
                        sync_send(serialized)
            except Exception as e:
                logger.debug(f"WebSocket send failed: {e}")

    def _schedule(self, coro):
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            logger.debug(f"Failed to schedule WebSocket coroutine: {e}")

    def _serialize(self, event: Dict[str, Any]) -> str:
        return json.dumps(event, default=str)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)[-limit:]


# Singleton
ws_manager = WebSocketManager()
