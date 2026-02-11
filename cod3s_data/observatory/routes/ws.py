"""WebSocket endpoint for Observatory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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

    try:
        # Send initial state snapshot
        snapshot = buffer.get_snapshot()
        connected_payload: dict[str, Any] = {
            "server_version": "1.0.0",
            **snapshot,
        }
        if debug is not None:
            connected_payload["debug"] = debug.get_state_dict()
        connected_payload["pipeline_state"] = bridge.get_pipeline_state()
        connected_payload["components"] = bridge.get_components_snapshot()
        connected_payload["topology"] = bridge.get_topology_snapshot()

        await websocket.send_json({
            "type": "connected",
            "id": f"evt-{client_id}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": connected_payload,
        })

        # Process incoming commands
        while True:
            data: dict[str, Any] = await websocket.receive_json()
            response = await _handle_command(data, bridge, debug)
            if response is not None:
                await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info("Observatory client disconnected", client_id=client_id)
    finally:
        ws_manager.disconnect(client_id)


async def _handle_command(
    data: dict[str, Any],
    bridge: Any,
    debug: Any,
) -> dict[str, Any] | None:
    """Dispatch a WebSocket command and return a response."""
    cmd_type = data.get("type", "")
    payload = data.get("payload", {})
    now = datetime.now(timezone.utc).isoformat()

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
            result = await debug.step(granularity)
            return {
                "type": "debug.step_result",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": result,
            }

        if cmd_type == "debug.set_granularity":
            granularity = payload.get("granularity", "message")
            debug.set_granularity(granularity)
            return {
                "type": "debug.granularity_set",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": {"granularity": granularity},
            }

        if cmd_type == "debug.set_slow_motion":
            enabled = payload.get("enabled", False)
            delay_ms = payload.get("delay_ms", 500)
            debug.set_slow_motion(enabled, delay_ms)
            return {
                "type": "debug.slow_motion_set",
                "id": "evt-dbg",
                "timestamp": now,
                "payload": {"enabled": enabled, "delay_ms": delay_ms},
            }

    except Exception as e:
        return {
            "type": "error",
            "id": "evt-err",
            "timestamp": now,
            "payload": {"message": str(e)},
        }

    return {
        "type": "error",
        "id": "evt-err",
        "timestamp": now,
        "payload": {"message": f"Unknown command: {cmd_type}"},
    }
