"""WebSocket connection manager for Observatory."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()

# How long arrivals are gathered before one frame goes out. Well under what an
# eye resolves, and the client coalesces per animation frame anyway, so the only
# thing it costs is latency nobody sees.
FLUSH_INTERVAL_S = 0.05
# Events waiting to go out. A monitor that falls behind must drop what it cannot
# show rather than grow without bound or stall the pipeline feeding it.
MAX_PENDING_EVENTS = 2000


class WebSocketManager:
    """Manages multiple WebSocket client connections."""

    def __init__(
        self,
        flush_interval_s: float = FLUSH_INTERVAL_S,
        max_pending: int = MAX_PENDING_EVENTS,
    ) -> None:
        self._clients: dict[str, Any] = {}
        self._pending: deque[dict[str, Any]] = deque(maxlen=max_pending)
        self._flush_interval_s = flush_interval_s
        self._drain_task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()

    async def connect(self, websocket: Any) -> str:
        """Register a new WebSocket client."""
        client_id = uuid.uuid4().hex[:8]
        self._clients[client_id] = websocket
        logger.info("Observatory client connected", client_id=client_id)
        return client_id

    def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket client."""
        self._clients.pop(client_id, None)

    @property
    def client_count(self) -> int:
        """How many WebSocket clients are currently registered."""
        return len(self._clients)

    def _envelope(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": event_type,
            "id": f"evt-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }

    async def _send_to_all(self, message: dict[str, Any]) -> None:
        disconnected: list[str] = []
        for client_id, ws in list(self._clients.items()):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)

    async def broadcast_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Broadcast an event to all connected clients, now.

        For the events a person acts on and waits for — a state change, a param
        rebind, a debug reply. High-frequency traffic goes through
        `queue_event` instead.
        """
        if not self._clients:
            return
        await self._send_to_all(self._envelope(event_type, payload))

    def queue_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Hand an event to the sender and return immediately.

        `broadcast_event` is awaited from inside `broker.publish()`, so every
        published message used to cost the pipeline a JSON serialisation and a
        socket write per connected client, in line, before the publish returned.
        Queueing takes that off the hot path, and the drain coalesces a window
        of events into a single frame — one serialisation and one write for the
        fifty messages a busy pipeline emits in 50 ms, instead of fifty of each.

        Ordering within the queue is preserved. Immediate broadcasts may
        overtake queued ones; that is only ever a state change arriving before
        a message, which no view correlates.
        """
        if not self._clients:
            return
        self._pending.append(self._envelope(event_type, payload))
        self._ensure_drain_task()
        self._wake.set()

    def _ensure_drain_task(self) -> None:
        if self._drain_task is not None and not self._drain_task.done():
            return
        try:
            self._drain_task = asyncio.create_task(self._drain())
        except RuntimeError:
            # No running loop — nothing to drain into. Queued events stay put
            # and go out with the next flush that does have one.
            self._drain_task = None

    async def _drain(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            await asyncio.sleep(self._flush_interval_s)
            await self.flush()

    async def flush(self) -> None:
        """Send everything queued as one frame. Safe to call with nothing to do."""
        if not self._pending:
            return
        batch = list(self._pending)
        self._pending.clear()
        if not self._clients:
            return
        if len(batch) == 1:
            await self._send_to_all(batch[0])
            return
        await self._send_to_all(self._envelope("batch", {"events": batch}))

    async def stop(self) -> None:
        """Flush what is queued and stop the drain task."""
        task = self._drain_task
        self._drain_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        with contextlib.suppress(Exception):
            await self.flush()
