"""Tests for the Observatory WebSocket endpoint.

Covers the connection snapshot and the command dispatcher — the part the
frontend talks to, and the least covered module of the package before these
tests existed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cod3s_data.framework import Framework
from cod3s_data.observatory.bridge import ObservatoryBridge
from cod3s_data.observatory.routes.ws import _run_step

from .conftest import PARAM_CHANNEL, make_message


class _RecordingSocket:
    """The one method `_run_step` uses of a WebSocket, keeping what it is given."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        """Record one outgoing frame."""
        self.sent.append(payload)


class _ClosedSocket:
    """A socket whose client has gone, which is what a closed one does on send."""

    async def send_json(self, payload: dict) -> None:
        """Fail the way a departed client fails."""
        raise RuntimeError('Cannot call "send" once a close message has been sent.')


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
        assert "zz" in reply["payload"]["message"]
        # The id comes back with the error so the client can tell which row
        # failed: without it the Inspector had nothing to match the reply to and
        # stayed on its loading bar for good.
        assert reply["payload"]["message_id"] == "zz"

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
    """Every debug command answers on the command, including `debug.step`.

    `step` used to be untestable: the handler awaited `DebugController.step()`
    inline in the receive loop, and that waits on an event only a message
    flowing through the pipeline can set, so with no traffic the command held
    the connection open with no reply and a test would have hung rather than
    failed. It now acknowledges immediately and reports the step as its own
    event, which is what makes the first two tests below possible at all.
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
        # The whole state, not just the field that moved: the client applies
        # every debug reply the same way, so a partial payload left the rest of
        # its view untouched until the next pause or step.
        assert reply["payload"]["granularity"] == "stage"
        assert "slow_motion" in reply["payload"]
        assert "state" in reply["payload"]

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
        # 50 ms was asked for and 100 is what the controller keeps, so 100 is
        # what the reply has to say. Echoing the request announced a delay that
        # was never applied.
        assert reply["payload"]["slow_motion"] is True
        assert reply["payload"]["slow_motion_delay_ms"] == 100
        assert debug_controller._slow_motion_delay_ms == 100

    async def test_step_answers_immediately_with_no_traffic(self, debug_client: TestClient) -> None:
        """The command that used to hang.

        Nothing is flowing through this pipeline, so the step itself cannot
        happen; the point is that the client is told so rather than left
        holding a silent socket. Reaching the assertion is the test.
        """
        paused, started = _roundtrip(debug_client, {"type": "debug.pause"}, {"type": "debug.step"})

        assert paused["type"] == "debug.paused"
        assert started["type"] == "debug.step_started"
        assert started["payload"]["state"] == "paused"

    async def test_step_reports_the_step_when_a_message_flows(self, debug_controller: Any) -> None:
        """`debug.step_result` carries the step *and* the state, once it happens.

        Driven against `_run_step` rather than through `TestClient`: the client
        runs the app in a portal of its own, so releasing the step from the test
        would set an `asyncio.Event` across two event loops — which happens to
        work and is not something to rest a test on.
        """
        socket = _RecordingSocket()
        await debug_controller.pause()

        task = asyncio.create_task(_run_step(socket, debug_controller, "message"))
        await asyncio.sleep(0)  # let the task reach its wait

        assert socket.sent == [], "nothing to report until a message flows"

        # What the pipeline would do on its own: one message reaches the
        # controller, which releases the step waiting on it.
        await debug_controller.check_message("sensors.temperature", make_message())
        await task

        (event,) = socket.sent
        assert event["type"] == "debug.step_result"
        assert event["payload"]["step"]["channel"] == "sensors.temperature"
        # The state travels with it, so one payload updates the client fully.
        assert event["payload"]["state"] == "paused"
        assert event["payload"]["step_count"] == 1

    async def test_step_outliving_its_socket_is_not_an_error(self, debug_controller: Any) -> None:
        """A step can complete long after the client left; that must stay quiet.

        The wait is unbounded by design, so the socket going away underneath it
        is ordinary, not exceptional — and an exception raised here would land
        in the event loop with no one to catch it.
        """
        socket = _ClosedSocket()
        await debug_controller.pause()

        task = asyncio.create_task(_run_step(socket, debug_controller, "message"))
        await asyncio.sleep(0)
        await debug_controller.check_message("sensors.temperature", make_message())

        await task  # the send raises inside; the task must still finish cleanly

    async def test_invalid_granularity_on_step_is_reported_immediately(
        self, debug_client: TestClient
    ) -> None:
        """A bad granularity is a client error, so it comes back on the command.

        Left to the deferred task it would surface as a stray error event
        whenever the next message happened to arrive, or never.
        """
        (reply,) = _roundtrip(
            debug_client, {"type": "debug.step", "payload": {"granularity": "bogus"}}
        )

        assert reply["type"] == "error"
        assert "bogus" in reply["payload"]["message"]
