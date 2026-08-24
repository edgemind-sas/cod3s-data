"""Debug API endpoints for Observatory."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class BreakpointCreate(BaseModel):
    channel_pattern: str
    condition: str | None = None
    component_id: str | None = None


@router.get("/breakpoints")
async def list_breakpoints(request: Request) -> list[dict[str, Any]]:
    """List all breakpoints."""
    debug = request.app.state.debug_controller
    return debug.breakpoint_evaluator.list_all()


@router.post("/breakpoints", status_code=201)
async def create_breakpoint(body: BreakpointCreate, request: Request) -> dict[str, str]:
    """Create a new breakpoint."""
    debug = request.app.state.debug_controller
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
    debug = request.app.state.debug_controller
    try:
        debug.breakpoint_evaluator.remove(breakpoint_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Breakpoint not found") from e


@router.get("/state")
async def debug_state(request: Request) -> dict[str, Any]:
    """Return current debug state."""
    debug = request.app.state.debug_controller
    return debug.get_state_dict()
