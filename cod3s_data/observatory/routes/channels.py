"""Channel history API endpoints for Observatory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/channels/{channel_name:path}/history")
async def channel_history(
    channel_name: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
) -> dict[str, Any]:
    """Return recent messages from a channel."""
    buffer = request.app.state.buffer
    messages = buffer.get_channel_messages(channel_name, limit)
    return {"channel": channel_name, "messages": messages, "count": len(messages)}
