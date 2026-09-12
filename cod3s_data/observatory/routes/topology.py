"""Topology API endpoints for Observatory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _declared_topology(bridge: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """The pipeline as configured: every component, and who subscribes to what.

    The buffered events alone are not enough. A component announces its state
    and its subscriptions once, at startup, into the same ring buffer the
    messages flow through — so on any busy pipeline they are evicted within
    seconds and this endpoint went back to reporting an empty pipeline. What the
    framework declares does not expire, so it is the floor; the buffer only
    refreshes it.
    """
    components: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    if bridge is None:
        return components, edges
    snapshot = bridge.get_topology_snapshot()
    for node in snapshot.get("nodes", []):
        cid = node.get("component_id", "")
        components[cid] = {
            "id": cid,
            "type": node.get("component_type", "unknown"),
            "state": node.get("state", "unknown"),
        }
        for pattern in node.get("channels", {}).get("subscribes", []):
            edges.append({"pattern": pattern, "subscriber_id": cid})
    return components, edges


@router.get("/topology")
async def get_topology(request: Request) -> dict[str, Any]:
    """Return pipeline topology as nodes and edges."""
    buffer = request.app.state.buffer
    from cod3s_data.observatory.buffer import EventType

    components, edges = _declared_topology(getattr(request.app.state, "bridge", None))

    # Then whatever the buffer still holds, which is more recent when it is there.
    state_events = buffer.get_recent(200, EventType.COMPONENT_STATE)
    for event in state_events:
        data = event["data"]
        cid = data.get("component_id", "")
        components[cid] = {
            "id": cid,
            "type": data.get("component_type", "unknown"),
            "state": data.get("new_state", "unknown"),
        }

    seen = {(e["pattern"], e["subscriber_id"]) for e in edges}
    sub_events = buffer.get_recent(200, EventType.SUBSCRIPTION)
    for event in sub_events:
        data = event["data"]
        if data.get("action") != "subscribe":
            continue
        edge = {
            "pattern": data.get("pattern", ""),
            "subscriber_id": data.get("subscriber_id", ""),
        }
        key = (edge["pattern"], edge["subscriber_id"])
        if key not in seen:
            seen.add(key)
            edges.append(edge)

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

    # Its startup event may be long evicted; the pipeline still declares it.
    declared, _ = _declared_topology(getattr(request.app.state, "bridge", None))
    if component_id in declared:
        return declared[component_id]

    raise HTTPException(status_code=404, detail=f"Component '{component_id}' not found")
