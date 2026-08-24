"""Topology API endpoints for Observatory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/topology")
async def get_topology(request: Request) -> dict[str, Any]:
    """Return pipeline topology as nodes and edges."""
    # Build topology from buffered component state events
    buffer = request.app.state.buffer
    from cod3s_data.observatory.buffer import EventType

    # Collect latest state per component
    components: dict[str, dict[str, Any]] = {}
    state_events = buffer.get_recent(200, EventType.COMPONENT_STATE)
    for event in state_events:
        data = event["data"]
        cid = data.get("component_id", "")
        components[cid] = {
            "id": cid,
            "type": data.get("component_type", "unknown"),
            "state": data.get("new_state", "unknown"),
        }

    # Collect subscription edges
    edges: list[dict[str, str]] = []
    sub_events = buffer.get_recent(200, EventType.SUBSCRIPTION)
    for event in sub_events:
        data = event["data"]
        if data.get("action") == "subscribe":
            edges.append(
                {
                    "pattern": data.get("pattern", ""),
                    "subscriber_id": data.get("subscriber_id", ""),
                }
            )

    return {
        "nodes": list(components.values()),
        "edges": edges,
    }


@router.get("/components/{component_id}")
async def get_component(component_id: str, request: Request) -> dict[str, Any]:
    """Return details for a specific component."""
    buffer = request.app.state.buffer
    from cod3s_data.observatory.buffer import EventType

    state_events = buffer.get_recent(200, EventType.COMPONENT_STATE)
    for event in reversed(state_events):
        data = event["data"]
        if data.get("component_id") == component_id:
            return {
                "id": component_id,
                "type": data.get("component_type", "unknown"),
                "state": data.get("new_state", "unknown"),
            }

    raise HTTPException(status_code=404, detail=f"Component '{component_id}' not found")
