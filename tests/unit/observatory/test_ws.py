"""Tests for the Observatory WebSocket endpoint.

Covers the connection snapshot and the command dispatcher — the part the
frontend talks to, and the least covered module of the package before these
tests existed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cod3s_data.framework import Framework
from cod3s_data.observatory.bridge import ObservatoryBridge

from .conftest import PARAM_CHANNEL, make_message


def _roundtrip(client: TestClient, *commands: dict) -> list[dict]:
    """Connect, skip the snapshot, send each command and collect the replies."""
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()  # the "connected" snapshot
        return [(socket.send_json(cmd), socket.receive_json())[1] for cmd in commands]


class TestConnectionSnapshot:
    async def test_sends_a_snapshot_on_connect(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            event = socket.receive_json()

        assert event["type"] == "connected"
        payload = event["payload"]
        assert payload["server_version"] == "1.0.0"
        assert payload["pipeline_state"] == "idle"
        assert payload["pipeline_info"]["display_name"] == "Observatory surface"
        assert [c["component_id"] for c in payload["components"]] == ["src-0", "tfm-0", "dst-0"]
        assert set(payload["topology"]) == {"nodes", "edges"}

    async def test_snapshot_carries_buffered_messages(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        await bridge.on_message_published("sensors.temperature", make_message(value=198.0), 1)

        with client.websocket_connect("/ws") as socket:
            payload = socket.receive_json()["payload"]

        assert [m["data"]["channel"] for m in payload["messages"]] == ["sensors.temperature"]

    async def test_debug_state_absent_when_debug_is_off(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as socket:
            assert "debug" not in socket.receive_json()["payload"]

    async def test_debug_state_present_when_debug_is_on(self, debug_client: TestClient) -> None:
        with debug_client.websocket_connect("/ws") as socket:
            debug = socket.receive_json()["payload"]["debug"]

        assert debug["state"] == "running"
        assert debug["granularity"] == "message"

    async def test_client_is_registered_then_released(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        assert bridge._ws.client_count == 0

        with client.websocket_connect("/ws") as socket:
            socket.receive_json()
            assert bridge._ws.client_count == 1

        assert bridge._ws.client_count == 0


class TestCommandDispatch:
    async def test_unknown_command(self, client: TestClient) -> None:
        (reply,) = _roundtrip(client, {"type": "nonsense.command"})

        assert reply["type"] == "error"
        assert reply["payload"]["message"] == "Unknown command: nonsense.command"

    async def test_pipeline_command_reports_a_refused_transition(self, client: TestClient) -> None:
        (reply,) = _roundtrip(client, {"type": "pipeline.stop"})

        assert reply["type"] == "pipeline.state"
        assert reply["payload"]["status"] == "error"
        assert reply["payload"]["message"] == "Cannot stop from state idle"

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({}, "param.update requires 'channel' in payload"),
            ({"channel": PARAM_CHANNEL}, "param.update requires 'value' in payload"),
        ],
    )
    async def test_param_update_validates_its_payload(
        self, client: TestClient, payload: dict, expected: str
    ) -> None:
        (reply,) = _roundtrip(client, {"type": "param.update", "payload": payload})

        assert reply["type"] == "error"
        assert reply["payload"]["message"] == expected

    async def test_param_update_publishes(self, client: TestClient, framework: Framework) -> None:
        transform = framework.transformations[0]
        await framework.broker.start()
        await transform._param_stores[0].start()

        (reply,) = _roundtrip(
            client,
            {"type": "param.update", "payload": {"channel": PARAM_CHANNEL, "value": 220.0}},
        )

        assert reply["type"] == "param.update_result"
        assert reply["payload"]["status"] == "ok"
        assert transform.setpoint == 220.0

    async def test_message_inspect_unknown_id(self, client: TestClient) -> None:
        (reply,) = _roundtrip(client, {"type": "message.inspect", "payload": {"message_id": "zz"}})

        assert reply["type"] == "error"
        assert reply["payload"]["message"] == "Message zz not found"

    async def test_message_inspect_returns_detail_and_journey(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        message = make_message(value=198.0)
        await bridge.on_message_published("sensors.temperature", message, 1)

        (reply,) = _roundtrip(
            client, {"type": "message.inspect", "payload": {"message_id": str(message.id)}}
        )

        assert reply["type"] == "message.detail"
        assert reply["payload"]["channel"] == "sensors.temperature"
        assert "journey" in reply["payload"]


class TestDebugCommands:
    """`debug.step` is deliberately absent.

    The handler awaits `DebugController.step()` inline in the receive loop, and
    that waits on an event only a message flowing through the pipeline can set.
    With no traffic it never returns, so the command holds the connection open
    with no reply — a test of it would hang rather than fail.
    """

    async def test_refused_when_debug_is_off(self, client: TestClient) -> None:
        replies = _roundtrip(client, {"type": "debug.pause"}, {"type": "debug.step"})

        assert [r["type"] for r in replies] == ["error", "error"]
        assert {r["payload"]["message"] for r in replies} == {"Debug mode is not enabled"}

    async def test_pause_then_resume(self, debug_client: TestClient) -> None:
        paused, resumed = _roundtrip(
            debug_client, {"type": "debug.pause"}, {"type": "debug.resume"}
        )

        assert paused["type"] == "debug.paused"
        assert paused["payload"]["state"] == "paused"
        assert resumed["type"] == "debug.resumed"
        assert resumed["payload"]["state"] == "running"

    async def test_set_granularity(self, debug_client: TestClient) -> None:
        (reply,) = _roundtrip(
            debug_client, {"type": "debug.set_granularity", "payload": {"granularity": "stage"}}
        )

        assert reply["type"] == "debug.granularity_set"
        assert reply["payload"] == {"granularity": "stage"}

    async def test_invalid_granularity_is_reported_not_raised(
        self, debug_client: TestClient
    ) -> None:
        (reply,) = _roundtrip(
            debug_client, {"type": "debug.set_granularity", "payload": {"granularity": "bogus"}}
        )

        assert reply["type"] == "error"
        assert "bogus" in reply["payload"]["message"]

    async def test_set_slow_motion(
        self, debug_client: TestClient, debug_controller: object
    ) -> None:
        (reply,) = _roundtrip(
            debug_client,
            {"type": "debug.set_slow_motion", "payload": {"enabled": True, "delay_ms": 50}},
        )

        assert reply["type"] == "debug.slow_motion_set"
        assert reply["payload"] == {"enabled": True, "delay_ms": 50}
        # The controller clamps to its own range; the reply echoes the request.
        assert debug_controller._slow_motion_delay_ms == 100
