"""WebSocket connection manager for Observatory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()


class WebSocketManager:
    """Manages multiple WebSocket client connections."""

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

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
        return len(self._clients)

    async def broadcast_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Broadcast an event to all connected clients."""
        if not self._clients:
            return

        message = {
            "type": event_type,
            "id": f"evt-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }

        disconnected: list[str] = []
        for client_id, ws in self._clients.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)
