"""Message detail and journey stores for the Observatory Inspector."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class JourneyStep:
    """A single step in a message's journey through the pipeline.

    message_id identifies which specific message this step is about.
    parent_message_id links to the input message that caused this one
    (set when a transformation produces output from an input).
    Together they form a tree: fan-out at RECEIVED (multiple components
    receive the same message) and branching at PROCESSED (new child messages).
    """

    stage: str  # PUBLISHED, RECEIVED, PROCESSED, DELIVERED
    component_id: str
    component_type: str
    channel: str
    message_id: str = ""
    parent_message_id: str = ""
    label: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Return the journey step as a JSON-serialisable dictionary."""
        return asdict(self)


@dataclass
class _StoredDetail:
    """One cached message: its envelope, and its fields once someone asks.

    `fields` is the message rendered as a dictionary. Rendering it costs a full
    Pydantic `model_dump`, and it was paid on *every* published message for the
    handful that ever get opened in the Inspector — so the message is kept as it
    is and dumped on first read instead. Messages are frozen, so holding the
    object is both cheaper than a copy and just as faithful.
    """

    message_id: str
    channel: str
    trace_id: str
    subscriber_count: int
    observed_at: str
    message: Any = None
    fields: dict[str, Any] | None = None

    def rendered(self) -> dict[str, Any]:
        """The message's fields, dumped once and remembered."""
        if self.fields is None:
            message = self.message
            self.fields = (
                message.to_dict() if message is not None and hasattr(message, "to_dict") else {}
            )
            self.message = None
        return self.fields


class MessageDetailStore:
    """LRU cache for complete message details.

    Stores the full message data keyed by message_id, with LRU eviction
    when the cache exceeds max_entries.
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._max_entries = max_entries
        self._store: OrderedDict[str, _StoredDetail] = OrderedDict()

    def store(
        self,
        message_id: str,
        channel: str,
        message_dict: dict[str, Any],
        subscriber_count: int,
        trace_id: str,
        observed_at: str = "",
        message: Any = None,
    ) -> None:
        """Store a message's complete details.

        `observed_at` is when the pipeline published the message, as opposed to
        the message's own `timestamp`, which is when the source says the reading
        was taken. The Observatory is a debugging view of the pipeline, so it
        shows the former; the latter is what InfluxDB and Grafana index on, and
        the two diverge by design whenever a recorded session is replayed.

        Pass `message` rather than `message_dict` to have the fields rendered
        only if the message is ever opened — see `_StoredDetail`.
        """
        # Move to end if already exists (LRU update)
        if message_id in self._store:
            self._store.move_to_end(message_id)
        else:
            # Evict oldest if at capacity
            while len(self._store) >= self._max_entries:
                self._store.popitem(last=False)

        self._store[message_id] = _StoredDetail(
            message_id=message_id,
            channel=channel,
            trace_id=trace_id,
            subscriber_count=subscriber_count,
            observed_at=observed_at,
            message=message,
            fields=None if message is not None else dict(message_dict),
        )

    def get(self, message_id: str) -> dict[str, Any] | None:
        """Retrieve message details, updating LRU position."""
        if message_id not in self._store:
            return None
        self._store.move_to_end(message_id)
        entry = self._store[message_id]
        return {
            "message_id": entry.message_id,
            "channel": entry.channel,
            "trace_id": entry.trace_id,
            "subscriber_count": entry.subscriber_count,
            # After the spread: the message carries its own `timestamp`, which
            # must stay available and must not be overwritten by the envelope.
            **entry.rendered(),
            "observed_at": entry.observed_at,
        }

    @property
    def size(self) -> int:
        """How many messages the cache holds, at most `max_entries`."""
        return len(self._store)


class JourneyStore:
    """Stores journey steps keyed by trace_id.

    Each trace_id maps to a list of JourneyStep entries that record
    the message's path through the pipeline.
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._max_entries = max_entries
        self._store: OrderedDict[str, list[JourneyStep]] = OrderedDict()

    def add_step(self, trace_id: str, step: JourneyStep) -> None:
        """Add a journey step for a given trace."""
        if trace_id in self._store:
            self._store.move_to_end(trace_id)
            self._store[trace_id].append(step)
        else:
            # Evict oldest if at capacity
            while len(self._store) >= self._max_entries:
                self._store.popitem(last=False)
            self._store[trace_id] = [step]

    def get_journey(self, trace_id: str) -> list[dict[str, Any]] | None:
        """Retrieve journey steps for a trace_id, as dictionaries."""
        if trace_id not in self._store:
            return None
        self._store.move_to_end(trace_id)
        return [step.to_dict() for step in self._store[trace_id]]

    def get_steps(self, trace_id: str) -> list[JourneyStep]:
        """The trace's steps as dataclasses, without copying them.

        `get_journey` runs `asdict()` over every step, which recurses and copies;
        on the hot path — once per message received by every component — that
        rebuilt the whole accumulated trace just to read one field. This returns
        the live list instead. Read it, never mutate it: it is the store's own.
        """
        return self._store.get(trace_id, [])

    @property
    def size(self) -> int:
        """How many traces the store holds, at most `max_entries`.

        Traces, not steps: one trace is a whole journey through the pipeline,
        and eviction drops the least recently touched journey entire.
        """
        return len(self._store)
