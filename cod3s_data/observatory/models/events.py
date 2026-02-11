"""Pydantic models for Observatory WebSocket events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebSocketEvent(BaseModel):
    """Base model for WebSocket events sent to clients."""

    type: str
    id: str
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class MessagePublishedEvent(BaseModel):
    """Event payload for message.published."""

    channel: str
    key: str | None = None
    value_preview: str = ""
    tags: dict[str, str] = Field(default_factory=dict)
    subscriber_count: int = 0


class ComponentStateEvent(BaseModel):
    """Event payload for component.state."""

    component_id: str
    component_type: str
    old_state: str
    new_state: str


class SubscriptionEvent(BaseModel):
    """Event payload for topology.update."""

    pattern: str
    action: str  # "subscribe" or "unsubscribe"
    subscriber_id: str


class MetricEvent(BaseModel):
    """Event payload for metric.update."""

    metric_name: str
    value: float | dict[str, Any]
    tags: dict[str, str] = Field(default_factory=dict)


class ErrorEvent(BaseModel):
    """Event payload for error.occurred."""

    component_id: str
    error_type: str
    error_message: str
    context: dict[str, str] = Field(default_factory=dict)
