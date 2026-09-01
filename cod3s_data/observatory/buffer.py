"""Event buffer for Observatory - ring buffer with memory cap."""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of observatory events."""

    MESSAGE = "message"
    COMPONENT_STATE = "component_state"
    SUBSCRIPTION = "subscription"
    METRIC = "metric"
    ERROR = "error"
    DEBUG = "debug"
    PARAM = "param"


@dataclass
class ObservatoryEvent:
    """A single observatory event stored in the ring buffer."""

    type: EventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the event as a JSON-serialisable dictionary."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


class EventBuffer:
    """Fixed-size ring buffer for observatory events.

    Oldest events are evicted when capacity is reached.
    Memory cap provides a secondary limit.
    """

    def __init__(
        self,
        max_size: int = 1000,
        memory_limit_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self._buffer: deque[ObservatoryEvent] = deque(maxlen=max_size)
        self._memory_limit = memory_limit_bytes
        self._estimated_memory: int = 0

    def push(self, event: ObservatoryEvent) -> None:
        """Add an event to the buffer."""
        event_size = sys.getsizeof(event) + sys.getsizeof(event.data)

        # If deque is full, account for the item that will be evicted
        if len(self._buffer) == self._buffer.maxlen:
            old = self._buffer[0]
            self._estimated_memory -= sys.getsizeof(old) + sys.getsizeof(old.data)

        self._estimated_memory += event_size

        # Evict old events if over memory limit
        while self._estimated_memory > self._memory_limit and self._buffer:
            old = self._buffer.popleft()
            self._estimated_memory -= sys.getsizeof(old) + sys.getsizeof(old.data)

        self._buffer.append(event)

    def get_recent(
        self,
        limit: int = 100,
        event_type: EventType | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent events, optionally filtered by type."""
        if limit <= 0:
            return []
        # Walked backwards and stopped as soon as `limit` are in hand, rather
        # than filtering the whole buffer to keep its tail. `get_snapshot` asks
        # six times in a row, and each ask used to scan every retained event.
        selected: list[ObservatoryEvent] = []
        for event in reversed(self._buffer):
            if event_type is not None and event.type is not event_type:
                continue
            selected.append(event)
            if len(selected) == limit:
                break
        selected.reverse()
        return [e.to_dict() for e in selected]

    def get_channel_messages(self, channel: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent messages from a specific channel."""
        messages = [
            e.to_dict()
            for e in self._buffer
            if e.type == EventType.MESSAGE and e.data.get("channel") == channel
        ]
        return messages[-limit:]

    def get_snapshot(self) -> dict[str, Any]:
        """Get full state snapshot for late-connecting frontends."""
        return {
            "messages": self.get_recent(100, EventType.MESSAGE),
            "component_states": self.get_recent(50, EventType.COMPONENT_STATE),
            "metrics": self.get_recent(50, EventType.METRIC),
            "errors": self.get_recent(20, EventType.ERROR),
            "debug_events": self.get_recent(50, EventType.DEBUG),
            "params": self.get_recent(50, EventType.PARAM),
        }

    def clear(self) -> None:
        """Clear all events from the buffer."""
        self._buffer.clear()
        self._estimated_memory = 0

    @property
    def size(self) -> int:
        """How many events the ring buffer currently holds."""
        return len(self._buffer)

    @property
    def max_size(self) -> int:
        """The event count at which the oldest is evicted to make room."""
        return self._buffer.maxlen or 0

    @property
    def estimated_memory_mb(self) -> float:
        """Approximate size of the buffered events, in mebibytes.

        Estimated, and an undercount: it sums `sys.getsizeof()` of each event
        and of its `data` dict, which measures the containers rather than what
        they hold. Good enough to drive the secondary memory cap, not a figure
        to report as the buffer's true footprint.
        """
        return self._estimated_memory / (1024 * 1024)
