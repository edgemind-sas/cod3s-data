"""Tests for Observatory WebSocketManager."""

import asyncio
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


class TestQueuedBroadcast:
    """`queue_event` takes the socket off the pipeline's hot path.

    `broadcast_event` is awaited from inside `broker.publish()`. Every published
    message therefore cost a JSON serialisation and a socket write per client,
    in line, before the publish returned. Queued events are handed to a drain
    task and coalesced into one frame per window.
    """

    async def test_queue_returns_without_sending(self):
        manager = WebSocketManager(flush_interval_s=0.01)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        await manager.connect(ws)

        manager.queue_event("message.published", {"channel": "sensors.temp"})

        ws.send_json.assert_not_called()
        await manager.stop()

    async def test_a_single_queued_event_is_sent_as_itself(self):
        manager = WebSocketManager(flush_interval_s=0.01)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        await manager.connect(ws)

        manager.queue_event("message.published", {"channel": "sensors.temp"})
        await manager.flush()

        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "message.published"
        assert sent["payload"]["channel"] == "sensors.temp"
        await manager.stop()

    async def test_a_window_of_events_becomes_one_frame(self):
        manager = WebSocketManager(flush_interval_s=0.01)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        await manager.connect(ws)

        for i in range(50):
            manager.queue_event("message.published", {"channel": f"sensors.{i}"})
        await manager.flush()

        # One write for fifty messages, not fifty.
        assert ws.send_json.call_count == 1
        sent = ws.send_json.call_args[0][0]
        assert sent["type"] == "batch"
        events = sent["payload"]["events"]
        assert len(events) == 50
        # Order is what the pipeline published, so the client can replay it.
        assert [e["payload"]["channel"] for e in events] == [f"sensors.{i}" for i in range(50)]
        await manager.stop()

    async def test_the_drain_task_sends_on_its_own(self):
        manager = WebSocketManager(flush_interval_s=0.01)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        await manager.connect(ws)

        manager.queue_event("message.published", {"channel": "sensors.temp"})
        for _ in range(50):
            await asyncio.sleep(0.01)
            if ws.send_json.call_count:
                break

        assert ws.send_json.call_count == 1
        await manager.stop()

    async def test_nothing_is_queued_without_a_client(self):
        manager = WebSocketManager(flush_interval_s=0.01)
        for _ in range(10):
            manager.queue_event("message.published", {"channel": "sensors.temp"})
        assert len(manager._pending) == 0

    async def test_a_backlog_drops_the_oldest(self):
        manager = WebSocketManager(flush_interval_s=10.0, max_pending=5)
        ws = MagicMock()
        ws.send_json = AsyncMock()
        await manager.connect(ws)

        for i in range(20):
            manager.queue_event("message.published", {"seq": i})
        await manager.flush()

        # A monitor that falls behind drops what it cannot show; it must not
        # grow without bound, nor stall the pipeline feeding it.
        events = ws.send_json.call_args[0][0]["payload"]["events"]
        assert [e["payload"]["seq"] for e in events] == [15, 16, 17, 18, 19]
        await manager.stop()
