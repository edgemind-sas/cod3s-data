"""Tests for Observatory WebSocketManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cod3s_data.observatory.websocket_manager import WebSocketManager


class TestWebSocketManager:
    """Tests for WebSocket connection management."""

    def test_initial_state(self):
        manager = WebSocketManager()
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_connect(self):
        manager = WebSocketManager()
        ws = MagicMock()
        client_id = await manager.connect(ws)
        assert len(client_id) == 8
        assert manager.client_count == 1

    @pytest.mark.asyncio
    async def test_disconnect(self):
        manager = WebSocketManager()
        ws = MagicMock()
        client_id = await manager.connect(ws)
        assert manager.client_count == 1
        manager.disconnect(client_id)
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown(self):
        manager = WebSocketManager()
        manager.disconnect("unknown-id")  # Should not raise
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_no_clients(self):
        manager = WebSocketManager()
        # Should not raise with no clients
        await manager.broadcast_event("test", {"data": 1})

    @pytest.mark.asyncio
    async def test_broadcast_to_clients(self):
        manager = WebSocketManager()
        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.broadcast_event("test.event", {"key": "value"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

        # Verify event structure
        msg = ws1.send_json.call_args[0][0]
        assert msg["type"] == "test.event"
        assert msg["payload"]["key"] == "value"
        assert "id" in msg
        assert "timestamp" in msg

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_clients(self):
        manager = WebSocketManager()
        good_ws = MagicMock()
        good_ws.send_json = AsyncMock()
        bad_ws = MagicMock()
        bad_ws.send_json = AsyncMock(side_effect=RuntimeError("closed"))

        await manager.connect(good_ws)
        await manager.connect(bad_ws)
        assert manager.client_count == 2

        await manager.broadcast_event("test", {})
        # Bad client should be removed
        assert manager.client_count == 1
        good_ws.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_connects(self):
        manager = WebSocketManager()
        ids = set()
        for _ in range(5):
            ws = MagicMock()
            cid = await manager.connect(ws)
            ids.add(cid)
        assert len(ids) == 5
        assert manager.client_count == 5
