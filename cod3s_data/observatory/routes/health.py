"""Health check endpoint for Observatory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Return Observatory health status."""
    buffer = request.app.state.buffer
    ws = request.app.state.ws_manager
    bridge = request.app.state.bridge

    return {
        "status": "ok",
        "version": "1.0.0",
        "buffer_size": buffer.size,
        "buffer_memory_mb": round(buffer.estimated_memory_mb, 2),
        "connected_clients": ws.client_count,
        "pipeline_state": bridge.get_pipeline_state(),
    }
