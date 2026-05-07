"""Parameter API endpoints for Observatory.

Exposes the ``ParamRef`` plane: list editable params and publish updates.
The ``ParameterStore`` attached to each component (see
``cod3s_data/transformations/param_store.py``) reacts to publishes on its
channel and rebinds the component attribute.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/params")
async def list_params(request: Request) -> dict[str, Any]:
    """List all parameters declared via ``ParamRef`` across the pipeline."""
    bridge = request.app.state.bridge
    params = bridge.get_editable_params()
    return {"params": params, "count": len(params)}


@router.post("/params/{channel:path}")
async def update_param(channel: str, request: Request) -> dict[str, Any]:
    """Publish a new value on a parameter channel."""
    body = await request.json()
    if "value" not in body:
        raise HTTPException(status_code=400, detail="Body must contain 'value'")
    bridge = request.app.state.bridge
    result: dict[str, Any] = await bridge.update_param(channel, body["value"], body.get("key"))
    if result.get("status") != "ok":
        raise HTTPException(status_code=500, detail=result.get("message", "publish failed"))
    return result
