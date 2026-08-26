"""Debug API endpoints for Observatory."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from cod3s_data.observatory.debug import DebugController

router = APIRouter()


def _controller(request: Request) -> DebugController:
    """Return the debug controller, or refuse the request if debug is off.

    This router is mounted unconditionally, but `debug_controller` is None
    unless the pipeline was started with debug enabled — the default. Without
    this guard every route here raised AttributeError and answered 500. The
    wording matches what the WebSocket handler already returned for a
    `debug.*` command in the same situation.
    """
    debug: DebugController | None = request.app.state.debug_controller
    if debug is None:
        raise HTTPException(status_code=404, detail="Debug mode is not enabled")
    return debug


class BreakpointCreate(BaseModel):
    channel_pattern: str
    condition: str | None = None
    component_id: str | None = None


@router.get("/breakpoints")
async def list_breakpoints(request: Request) -> list[dict[str, Any]]:
    """List all breakpoints."""
    return _controller(request).breakpoint_evaluator.list_all()


@router.post("/breakpoints", status_code=201)
async def create_breakpoint(body: BreakpointCreate, request: Request) -> dict[str, str]:
    """Create a new breakpoint."""
    debug = _controller(request)
    bp_id = f"bp-{uuid.uuid4().hex[:8]}"
    try:
        debug.breakpoint_evaluator.add(
            breakpoint_id=bp_id,
            channel_pattern=body.channel_pattern,
            condition=body.condition,
            component_id=body.component_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"breakpoint_id": bp_id}


@router.delete("/breakpoints/{breakpoint_id}", status_code=204)
async def delete_breakpoint(breakpoint_id: str, request: Request) -> None:
    """Delete a breakpoint."""
    debug = _controller(request)
    try:
        debug.breakpoint_evaluator.remove(breakpoint_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Breakpoint not found") from e


@router.get("/state")
async def debug_state(request: Request) -> dict[str, Any]:
    """Return current debug state."""
    return _controller(request).get_state_dict()
