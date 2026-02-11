"""Pydantic models for Observatory WebSocket commands."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WebSocketCommand(BaseModel):
    """Base model for WebSocket commands from clients."""

    type: str
    payload: dict[str, Any] = {}


class DebugPauseCommand(BaseModel):
    """Payload for debug.pause command."""


class DebugResumeCommand(BaseModel):
    """Payload for debug.resume command."""


class DebugStepCommand(BaseModel):
    """Payload for debug.step command."""

    granularity: str = "message"


class DebugSetGranularityCommand(BaseModel):
    """Payload for debug.set_granularity command."""

    granularity: str


class DebugSetSlowMotionCommand(BaseModel):
    """Payload for debug.set_slow_motion command."""

    enabled: bool
    delay_ms: int = 500
