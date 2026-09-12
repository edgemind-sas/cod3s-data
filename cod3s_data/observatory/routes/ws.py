"""WebSocket endpoint for Observatory."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cod3s_data.observatory.debug import DebugGranularity

logger = structlog.get_logger()
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle WebSocket connections for real-time Observatory events."""
    ws_manager = websocket.app.state.ws_manager
    buffer = websocket.app.state.buffer
    debug = getattr(websocket.app.state, "debug_controller", None)
    bridge = websocket.app.state.bridge

    await websocket.accept()
    client_id = await ws_manager.connect(websocket)

    # `debug.step` waits for traffic that may never come, so it runs outside the
    # receive loop. The set both keeps the tasks referenced — asyncio only holds
    # a weak reference, and an unreferenced task can be collected mid-wait — and
    # gives the disconnect path something to cancel.
    stepping: set[asyncio.Task[None]] = set()

    try:
        # Send initial state snapshot
        snapshot = buffer.get_snapshot()
        config = getattr(websocket.app.state, "config", None)
        connected_payload: dict[str, Any] = {
            "server_version": "1.0.0",
            # The client keeps the same number of messages the server can still
            # describe, so no listed row is dead on click.
            "history_size": getattr(config, "retained_details", 500),
            **snapshot,
        }
        if debug is not None:
            connected_payload["debug"] = debug.get_state_dict()
        connected_payload["pipeline_info"] = bridge.get_pipeline_info()
        connected_payload["pipeline_state"] = bridge.get_pipeline_state()
        connected_payload["components"] = bridge.get_components_snapshot()
        connected_payload["topology"] = bridge.get_topology_snapshot()

        await websocket.send_json(
            {
                "type": "connected",
                "id": f"evt-{client_id}",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": connected_payload,
            }
        )

        # Process incoming commands
        while True:
            data: dict[str, Any] = await websocket.receive_json()
            response = await _handle_command(data, bridge, debug, websocket, stepping)
            if response is not None:
                await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info("Observatory client disconnected", client_id=client_id)
    finally:
        for task in stepping:
            task.cancel()
        ws_manager.disconnect(client_id)


async def _run_step(websocket: WebSocket, debug: Any, granularity: str) -> None:
    """Wait for one debug step to happen, then report it.

    Runs as its own task because `DebugController.step()` waits on an event that
    only a message flowing through the pipeline can set: awaiting it inside the
    receive loop would hold the connection with no reply for as long as the
    pipeline stays quiet. The client gets `debug.step_started` immediately and
    this event whenever the step actually occurs.

    Every send is guarded: by the time a step completes the client may be gone,
    and a step that outlives its socket must not raise into the event loop.
    """
    try:
        result = await debug.step(granularity)
    except asyncio.CancelledError:
        raise  # the client disconnected; the endpoint is cancelling us
    except Exception as e:
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "type": "error",
                    "id": "evt-err",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "payload": {"message": str(e)},
                }
            )
        return

    with contextlib.suppress(Exception):
        await websocket.send_json(
            {
                "type": "debug.step_result",
                "id": "evt-dbg",
                "timestamp": datetime.now(UTC).isoformat(),
                # The state first, so the client can apply the whole payload the
                # way it applies every other debug reply; `step` carries what is
                # specific to this one — which message, or which breakpoint.
                "payload": {**debug.get_state_dict(), "step": result},
            }
        )


async def _handle_command(
    data: dict[str, Any],
    bridge: Any,
    debug: Any,
    websocket: WebSocket | None = None,
    stepping: set[asyncio.Task[None]] | None = None,
) -> dict[str, Any] | None:
    """Dispatch a WebSocket command and return the immediate response.

    `websocket` and `stepping` are only needed by `debug.step`, which answers
    now and reports later; every other command is answered by its return value.
    """
    cmd_type = data.get("type", "")
    payload = data.get("payload", {})
    now = datetime.now(UTC).isoformat()

    # Pipeline control commands
    if cmd_type.startswith("pipeline."):
        try:
            if cmd_type == "pipeline.start":
                result = await bridge.start_pipeline()
                return {
                    "type": "pipeline.state",
                    "id": "evt-pipe",
                    "timestamp": now,
                    "payload": result,
                }

            if cmd_type == "pipeline.stop":
                result = await bridge.stop_pipeline()
                return {
                    "type": "pipeline.state",
                    "id": "evt-pipe",
                    "timestamp": now,
                    "payload": result,
                }

            if cmd_type == "pipeline.restart":
                result = await bridge.restart_pipeline()
                return {
                    "type": "pipeline.state",
                    "id": "evt-pipe",
                    "timestamp": now,
                    "payload": result,
                }
        except Exception as e:
            return {
                "type": "error",
                "id": "evt-err",
                "timestamp": now,
                "payload": {"message": str(e)},
            }

    if debug is None and cmd_type.startswith("debug."):
        return {
            "type": "error",
            "id": "evt-err",
            "timestamp": now,
            "payload": {"message": "Debug mode is not enabled"},
        }

    try:
        if cmd_type == "debug.pause":
            await debug.pause()
            return {
                "type": "debug.paused",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": debug.get_state_dict(),
            }

        if cmd_type == "debug.resume":
            await debug.resume()
            return {
                "type": "debug.resumed",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": debug.get_state_dict(),
            }

        if cmd_type == "debug.step":
            granularity = payload.get("granularity", "message")
            # Validated here rather than in the task: a bogus granularity is a
            # client error and has to come back on the command, not minutes
            # later as a stray event.
            DebugGranularity(granularity)
            if websocket is not None and stepping is not None:
                task = asyncio.create_task(_run_step(websocket, debug, granularity))
                stepping.add(task)
                task.add_done_callback(stepping.discard)
            return {
                "type": "debug.step_started",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": debug.get_state_dict(),
            }

        if cmd_type == "debug.set_granularity":
            granularity = payload.get("granularity", "message")
            debug.set_granularity(granularity)
            return {
                "type": "debug.granularity_set",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": debug.get_state_dict(),
            }

        if cmd_type == "debug.set_slow_motion":
            enabled = payload.get("enabled", False)
            delay_ms = payload.get("delay_ms", 500)
            debug.set_slow_motion(enabled, delay_ms)
            return {
                "type": "debug.slow_motion_set",
                "id": "evt-dbg",
                "timestamp": now,
                # The controller's state, not the request: it clamps the delay
                # to 100..5000 ms, so echoing `delay_ms` back announced a value
                # that was never applied.
                "payload": debug.get_state_dict(),
            }

    except Exception as e:
        return {
            "type": "error",
            "id": "evt-err",
            "timestamp": now,
            "payload": {"message": str(e)},
        }

    if cmd_type == "param.update":
        channel = payload.get("channel", "")
        if not channel:
            return {
                "type": "error",
                "id": "evt-err",
                "timestamp": now,
                "payload": {"message": "param.update requires 'channel' in payload"},
            }
        if "value" not in payload:
            return {
                "type": "error",
                "id": "evt-err",
                "timestamp": now,
                "payload": {"message": "param.update requires 'value' in payload"},
            }
        result = await bridge.update_param(channel, payload["value"], payload.get("key"))
        return {
            "type": "param.update_result",
            "id": "evt-param",
            "timestamp": now,
            "payload": result,
        }

    if cmd_type == "message.inspect":
        message_id = payload.get("message_id", "")
        detail = bridge.get_message_detail(message_id)
        if detail is None:
            return {
                "type": "error",
                "id": "evt-err",
                "timestamp": now,
                # The id travels with the error: the client shows the failure on
                # the row it was asked about, and ignores it if the selection
                # has moved on. Without it an inspect that missed left the panel
                # spinning, because nothing could tell it the answer was in.
                "payload": {
                    "message": (
                        f"Message {message_id} is no longer available — its details have "
                        "been evicted from the cache."
                    ),
                    "message_id": message_id,
                },
            }
        return {
            "type": "message.detail",
            "id": f"evt-{message_id[:8]}",
            "timestamp": now,
            "payload": detail,
        }

    return {
        "type": "error",
        "id": "evt-err",
        "timestamp": now,
        "payload": {"message": f"Unknown command: {cmd_type}"},
    }
