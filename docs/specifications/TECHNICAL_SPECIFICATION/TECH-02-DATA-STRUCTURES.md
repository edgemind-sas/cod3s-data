# Core Data Structures

**Document**: TECH-02-DATA-STRUCTURES.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [03-MESSAGES](../FUNCTIONAL_SPECIFICATION/03-MESSAGES.md), [08-BROKER](../FUNCTIONAL_SPECIFICATION/08-BROKER.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-01](TECH-01-ARCHITECTURE.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-03 →](TECH-03-BROKER-API.md) |

---

## Table of Contents

1. [Message Class](#message-class)
2. [Subscription Registry](#subscription-registry)
3. [History Buffers](#history-buffers)
4. [Destination Buffers](#destination-buffers)
5. [State Management Structures](#state-management-structures)

---

## Message Class

### Pydantic Model Implementation

**Design Decision**: Use Pydantic v2 for automatic validation, serialization, and type safety.

See [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-2-pydantic-v2-for-data-models)

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

class Message(BaseModel):
    """
    Core message structure for COD3S Data Framework.

    All messages flowing through the framework use this structure,
    regardless of source or destination.

    Attributes:
        key: Identifies what is being measured (e.g., "temperature")
        timestamp: When the measurement was taken (UTC, timezone-aware)
        value: The actual measurement (flexible type)
        tags: Optional metadata for filtering/routing (all string values)
        id: Unique message identifier (auto-generated if not provided)

    Examples:
        >>> from datetime import datetime, timezone
        >>> msg = Message(
        ...     key="temperature",
        ...     timestamp=datetime.now(timezone.utc),
        ...     value=42.5,
        ...     tags={"sensor": "TH001", "location": "warehouse_A"}
        ... )
        >>> msg.key
        'temperature'
        >>> msg.value
        42.5
    """

    # Required fields
    key: str = Field(
        ...,
        description="Identifier for what is being measured",
        min_length=1,
        max_length=255
    )

    timestamp: datetime = Field(
        ...,
        description="When the measurement was taken (must be timezone-aware UTC)"
    )

    value: Any = Field(
        ...,
        description="The actual measurement (any JSON-serializable type)"
    )

    # Optional fields
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Metadata for filtering and routing (all values are strings)"
    )

    id: UUID = Field(
        default_factory=uuid4,
        description="Unique message identifier (auto-generated)"
    )

    # Internal metadata (excluded from serialization)
    _trace_id: str | None = Field(
        default=None,
        exclude=True,
        description="Trace ID for distributed tracing (internal use)"
    )

    _retry_count: int = Field(
        default=0,
        exclude=True,
        description="Number of retry attempts (internal use)"
    )

    _source_timestamp: datetime | None = Field(
        default=None,
        exclude=True,
        description="Original source timestamp before any transformations"
    )

    # Configuration
    model_config = {
        "frozen": True,  # Immutable after creation (thread-safe)
        "validate_assignment": True,  # Validate if reassignment attempted
        "arbitrary_types_allowed": True,  # Allow any type in 'value' field
        "json_schema_extra": {
            "examples": [
                {
                    "key": "temperature_extruder",
                    "timestamp": "2024-01-15T10:30:45Z",
                    "value": 235.7,
                    "tags": {
                        "location": "warehouse_A",
                        "sensor_id": "TH001"
                    }
                }
            ]
        }
    }

    # Validators

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp_tz(cls, v: datetime) -> datetime:
        """
        Ensure timestamp is timezone-aware and in UTC.

        Args:
            v: Timestamp to validate

        Returns:
            Validated timestamp (guaranteed UTC)

        Raises:
            ValueError: If timestamp is naive (no timezone)
        """
        if v.tzinfo is None:
            raise ValueError(
                "Timestamp must be timezone-aware. "
                "Use datetime.now(timezone.utc) instead of datetime.now()"
            )

        # Convert to UTC if not already
        if v.tzinfo != timezone.utc:
            v = v.astimezone(timezone.utc)

        return v

    @field_validator('tags')
    @classmethod
    def validate_tags_strings(cls, v: dict[str, str]) -> dict[str, str]:
        """
        Ensure all tag values are strings.

        Automatically converts numbers and booleans to strings.

        Args:
            v: Tags dictionary

        Returns:
            Tags with all values as strings
        """
        return {k: str(val) for k, val in v.items()}

    @field_validator('key')
    @classmethod
    def validate_key_not_empty(cls, v: str) -> str:
        """
        Ensure key is not empty or whitespace-only.

        Args:
            v: Key string

        Returns:
            Validated key

        Raises:
            ValueError: If key is empty or whitespace-only
        """
        if not v.strip():
            raise ValueError("Key cannot be empty or whitespace-only")
        return v.strip()

    # Serialization

    def to_json(self) -> str:
        """
        Serialize to JSON string.

        Uses Pydantic's built-in JSON serialization (Rust-based, fast).

        Returns:
            JSON string representation

        Examples:
            >>> msg.to_json()
            '{"key":"temperature","timestamp":"2024-01-15T10:30:45Z",...}'
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """
        Deserialize from JSON string.

        Args:
            json_str: JSON string to deserialize

        Returns:
            Message instance

        Raises:
            ValidationError: If JSON is invalid or doesn't match schema

        Examples:
            >>> json_str = '{"key":"temp","timestamp":"2024-01-15T10:30:45Z","value":42}'
            >>> msg = Message.from_json(json_str)
            >>> msg.key
            'temp'
        """
        return cls.model_validate_json(json_str)

    def to_dict(self) -> dict:
        """
        Convert to Python dictionary (excludes internal fields).

        Returns:
            Dictionary representation (JSON-serializable)
        """
        return self.model_dump(mode='json')

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """
        Create message from dictionary.

        Args:
            data: Dictionary with message fields

        Returns:
            Message instance

        Raises:
            ValidationError: If data is invalid
        """
        return cls.model_validate(data)

    # Utility methods

    def with_tags(self, **new_tags: str) -> "Message":
        """
        Create a new message with additional tags.

        Since messages are immutable, this creates a new instance.

        Args:
            **new_tags: Additional tags to add

        Returns:
            New message with merged tags

        Examples:
            >>> msg2 = msg.with_tags(priority="high", alert="yes")
            >>> "priority" in msg2.tags
            True
        """
        merged_tags = {**self.tags, **new_tags}
        return self.model_copy(update={"tags": merged_tags})

    def with_value(self, new_value: Any) -> "Message":
        """
        Create a new message with a different value.

        Useful for transformations.

        Args:
            new_value: New value to set

        Returns:
            New message with updated value

        Examples:
            >>> celsius_msg = fahrenheit_msg.with_value(celsius_value)
        """
        return self.model_copy(update={"value": new_value})

    def __repr__(self) -> str:
        """String representation for debugging"""
        return (
            f"Message(key={self.key!r}, "
            f"timestamp={self.timestamp.isoformat()}, "
            f"value={self.value!r}, "
            f"tags={self.tags}, "
            f"id={self.id})"
        )
```

### Performance Characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| **Creation** | O(1) | Pydantic validation overhead (~1-2 μs) |
| **Validation** | O(n) | n = number of tags (typically small) |
| **JSON serialization** | O(n) | Rust-based pydantic-core (~200k msgs/sec) |
| **JSON deserialization** | O(n) | Rust-based pydantic-core |
| **Memory size** | ~1 KB | Typical message with 5 tags |

### Error Messages

Pydantic provides clear, actionable error messages:

```python
# Missing required field
>>> Message(key="temp", value=42)
ValidationError: 1 validation error for Message
timestamp
  field required (type=value_error.missing)

# Invalid timestamp (not timezone-aware)
>>> from datetime import datetime
>>> Message(key="temp", timestamp=datetime.now(), value=42)
ValidationError: 1 validation error for Message
timestamp
  Timestamp must be timezone-aware. Use datetime.now(timezone.utc)

# Empty key
>>> Message(key="", timestamp=datetime.now(timezone.utc), value=42)
ValidationError: 1 validation error for Message
key
  Key cannot be empty or whitespace-only
```

---

## Subscription Registry

### Purpose

Efficiently match channel names to subscribed callbacks.

**Requirements**:
- O(1) lookup for exact matches (common case)
- Support wildcard patterns (`sensors.*.temp`, `sensors.**`)
- Thread-safe (used from async callbacks)

### Implementation

```python
import re
from typing import Callable, Awaitable
from collections import defaultdict

# Type alias for callback function
Callback = Callable[[Message], Awaitable[None]]

class SubscriptionRegistry:
    """
    Efficient channel pattern matching for pub/sub.

    Performance:
    - Exact matches: O(1)
    - Single-level wildcards: O(n) where n = number of * patterns
    - Multi-level wildcards: O(m) where m = number of ** patterns

    Typical: <1ms for 100 subscriptions
    """

    def __init__(self):
        # Exact matches: O(1) lookup
        self._exact_matches: dict[str, list[Callback]] = defaultdict(list)

        # Single-level wildcards: sensors.*.temp
        self._single_wildcards: dict[re.Pattern, list[Callback]] = {}

        # Multi-level wildcards: sensors.**
        self._multi_wildcards: list[tuple[re.Pattern, Callback]] = []

    def add_subscription(self, pattern: str, callback: Callback):
        """
        Register a subscription with channel pattern.

        Args:
            pattern: Channel pattern (exact or with wildcards)
                - Exact: "sensors.temp"
                - Single-level: "sensors.*.temp" (one level only)
                - Multi-level: "sensors.**" (zero or more levels)
            callback: Async function to call when channel matches

        Examples:
            >>> async def my_callback(msg: Message):
            ...     print(f"Received: {msg.value}")
            >>> registry.add_subscription("sensors.temp", my_callback)
            >>> registry.add_subscription("sensors.*.temp", my_callback)
            >>> registry.add_subscription("alerts.**", my_callback)
        """
        if '*' not in pattern:
            # Exact match: store in dictionary
            self._exact_matches[pattern].append(callback)

        elif '**' in pattern:
            # Multi-level wildcard
            regex = self._compile_multi_wildcard(pattern)
            self._multi_wildcards.append((regex, callback))

        else:
            # Single-level wildcard
            regex = self._compile_single_wildcard(pattern)
            if regex not in self._single_wildcards:
                self._single_wildcards[regex] = []
            self._single_wildcards[regex].append(callback)

    def match_channel(self, channel: str) -> list[Callback]:
        """
        Return all callbacks matching this channel.

        Args:
            channel: Exact channel name (e.g., "sensors.printer1.temp")

        Returns:
            List of callbacks to invoke (may be empty)

        Performance:
            - Best case (exact match): O(1)
            - Worst case (no exact, check wildcards): O(n + m)
              where n = single wildcards, m = multi wildcards
            - Typical: <1ms for 100 subscriptions

        Examples:
            >>> callbacks = registry.match_channel("sensors.printer1.temp")
            >>> for cb in callbacks:
            ...     await cb(message)
        """
        callbacks = []

        # 1. Check exact match first (fast path)
        if channel in self._exact_matches:
            callbacks.extend(self._exact_matches[channel])

        # 2. Check single-level wildcards
        for pattern, cbs in self._single_wildcards.items():
            if pattern.fullmatch(channel):
                callbacks.extend(cbs)

        # 3. Check multi-level wildcards
        for pattern, cb in self._multi_wildcards:
            if pattern.fullmatch(channel):
                callbacks.append(cb)

        return callbacks

    def remove_subscription(self, pattern: str, callback: Callback):
        """
        Remove a specific subscription.

        Args:
            pattern: Original pattern used in add_subscription
            callback: Exact callback to remove

        Examples:
            >>> registry.remove_subscription("sensors.temp", my_callback)
        """
        if '*' not in pattern:
            if pattern in self._exact_matches:
                try:
                    self._exact_matches[pattern].remove(callback)
                    if not self._exact_matches[pattern]:
                        del self._exact_matches[pattern]
                except ValueError:
                    pass  # Callback not found

        elif '**' in pattern:
            regex = self._compile_multi_wildcard(pattern)
            self._multi_wildcards = [
                (p, cb) for p, cb in self._multi_wildcards
                if not (p == regex and cb == callback)
            ]

        else:
            regex = self._compile_single_wildcard(pattern)
            if regex in self._single_wildcards:
                try:
                    self._single_wildcards[regex].remove(callback)
                    if not self._single_wildcards[regex]:
                        del self._single_wildcards[regex]
                except ValueError:
                    pass

    @staticmethod
    def _compile_single_wildcard(pattern: str) -> re.Pattern:
        """
        Compile single-level wildcard pattern to regex.

        Pattern: "sensors.*.temp"
        Regex: ^sensors\.[^.]+\.temp$

        Args:
            pattern: Pattern with single-level wildcards (*)

        Returns:
            Compiled regex pattern
        """
        # Escape special regex characters except *
        escaped = re.escape(pattern)

        # Replace \* with [^.]+ (one or more non-dot characters)
        regex_pattern = escaped.replace(r'\*', r'[^.]+')

        # Anchor to full string
        regex_pattern = f'^{regex_pattern}$'

        return re.compile(regex_pattern)

    @staticmethod
    def _compile_multi_wildcard(pattern: str) -> re.Pattern:
        """
        Compile multi-level wildcard pattern to regex.

        Pattern: "sensors.**"
        Regex: ^sensors\..*$

        Pattern: "**.temp"
        Regex: ^.*\.temp$

        Args:
            pattern: Pattern with multi-level wildcards (**)

        Returns:
            Compiled regex pattern
        """
        # Escape special regex characters except **
        escaped = re.escape(pattern)

        # Replace \*\* with .* (zero or more of any character)
        regex_pattern = escaped.replace(r'\*\*', r'.*')

        # Anchor to full string
        regex_pattern = f'^{regex_pattern}$'

        return re.compile(regex_pattern)

    def get_all_patterns(self) -> list[str]:
        """
        Get all registered patterns (for debugging).

        Returns:
            List of all channel patterns
        """
        patterns = list(self._exact_matches.keys())

        for regex in self._single_wildcards.keys():
            patterns.append(regex.pattern)

        for regex, _ in self._multi_wildcards:
            patterns.append(regex.pattern)

        return patterns

    def count_subscriptions(self) -> int:
        """
        Total number of subscriptions.

        Returns:
            Count of all subscriptions
        """
        count = sum(len(cbs) for cbs in self._exact_matches.values())
        count += sum(len(cbs) for cbs in self._single_wildcards.values())
        count += len(self._multi_wildcards)
        return count
```

### Usage Example

```python
registry = SubscriptionRegistry()

# Add subscriptions
async def handle_temp(msg: Message):
    print(f"Temperature: {msg.value}")

async def handle_all_sensors(msg: Message):
    print(f"Sensor data: {msg.key} = {msg.value}")

registry.add_subscription("sensors.printer1.temp", handle_temp)
registry.add_subscription("sensors.**.temp", handle_all_sensors)

# Match channel
callbacks = registry.match_channel("sensors.printer1.temp")
# Returns: [handle_temp, handle_all_sensors] (both match)

for callback in callbacks:
    await callback(message)
```

---

## History Buffers

### Purpose

Store recent messages per channel for "history replay" on subscription.

**Requirements**:
- Fixed-size buffer (bounded memory)
- FIFO eviction (oldest messages discarded)
- Optional TTL (time-to-live)
- Fast append and retrieval

### Implementation

```python
from collections import deque
from datetime import timedelta
from typing import Optional

class HistoryBuffer:
    """
    Fixed-size ring buffer for channel message history.

    Performance:
    - Append: O(1)
    - Get recent: O(n) where n = requested count
    - Memory: O(max_size * message_size)

    Typical memory: 100 messages * 1KB = 100KB per channel
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl: Optional[timedelta] = None
    ):
        """
        Initialize history buffer.

        Args:
            max_size: Maximum number of messages to retain
            ttl: Optional time-to-live for messages (evict older)

        Examples:
            >>> buffer = HistoryBuffer(max_size=100)  # Keep last 100
            >>> buffer = HistoryBuffer(max_size=1000, ttl=timedelta(hours=1))
        """
        self._buffer: deque[Message] = deque(maxlen=max_size)
        self._ttl = ttl
        self._max_size = max_size

    def add(self, message: Message):
        """
        Add message to buffer.

        Automatically evicts oldest if buffer is full.

        Args:
            message: Message to add

        Performance: O(1)
        """
        self._buffer.append(message)

    def get_recent(self, count: int) -> list[Message]:
        """
        Get last N messages, newest first.

        Respects TTL if configured (filters expired messages).

        Args:
            count: Number of messages to retrieve

        Returns:
            List of messages (newest first), may be fewer than count

        Performance: O(n) where n = count

        Examples:
            >>> recent = buffer.get_recent(10)  # Last 10 messages
            >>> len(recent) <= 10
            True
        """
        if self._ttl:
            # Filter by TTL
            cutoff = datetime.now(timezone.utc) - self._ttl
            valid = [m for m in self._buffer if m.timestamp >= cutoff]
            # Return newest first
            return list(reversed(valid[-count:]))
        else:
            # No TTL, just return last N
            return list(reversed(list(self._buffer)[-count:]))

    def get_all(self) -> list[Message]:
        """
        Get all messages in buffer, newest first.

        Returns:
            All messages (newest first)
        """
        return self.get_recent(len(self._buffer))

    def clear(self):
        """Clear all messages from buffer"""
        self._buffer.clear()

    def __len__(self) -> int:
        """Number of messages currently in buffer"""
        if self._ttl:
            cutoff = datetime.now(timezone.utc) - self._ttl
            return sum(1 for m in self._buffer if m.timestamp >= cutoff)
        return len(self._buffer)
```

### Memory Management

**Per-channel overhead**:
```
100 messages * ~1KB/message = ~100KB per channel
10 channels = ~1MB total for history
```

**TTL eviction** (optional):
```python
# Keep only last hour of messages
buffer = HistoryBuffer(max_size=10000, ttl=timedelta(hours=1))

# Older messages filtered out on retrieval (lazy eviction)
recent = buffer.get_recent(100)  # Only returns messages < 1 hour old
```

---

## Destination Buffers

### Purpose

Bounded queue for destination message buffering with overflow strategies.

**Requirements**:
- Configurable max size
- Overflow strategies (drop oldest, drop newest, block)
- Async-compatible (asyncio.Queue)
- Backpressure support

### Implementation

```python
import asyncio
from enum import Enum

class OverflowStrategy(Enum):
    """
    Strategy for handling buffer overflow.
    """
    DROP_OLDEST = "drop_oldest"  # Remove oldest message, add new
    DROP_NEWEST = "drop_newest"  # Discard new message
    BLOCK = "block"              # Wait until space available (backpressure)

class DestinationBuffer:
    """
    Bounded queue for destination message buffering.

    Handles overflow according to configured strategy.

    Performance:
    - Put (no overflow): O(1)
    - Put (with overflow): O(1) for drop, O(?) for block
    - Get: O(1)
    - Memory: O(max_size * message_size)
    """

    def __init__(
        self,
        max_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST
    ):
        """
        Initialize destination buffer.

        Args:
            max_size: Maximum messages to buffer
            overflow_strategy: How to handle overflow

        Examples:
            >>> buffer = DestinationBuffer(max_size=1000)
            >>> buffer = DestinationBuffer(
            ...     max_size=500,
            ...     overflow_strategy=OverflowStrategy.BLOCK
            ... )
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._overflow_strategy = overflow_strategy
        self._max_size = max_size
        self._dropped_count = 0  # Metrics

    async def put(self, message: Message):
        """
        Add message to buffer.

        Behavior depends on overflow strategy:
        - DROP_OLDEST: Remove oldest, add new
        - DROP_NEWEST: Discard new message
        - BLOCK: Wait until space available

        Args:
            message: Message to buffer

        Examples:
            >>> await buffer.put(message)  # May block or drop
        """
        try:
            # Try non-blocking put
            self._queue.put_nowait(message)

        except asyncio.QueueFull:
            # Buffer full: apply overflow strategy

            if self._overflow_strategy == OverflowStrategy.DROP_NEWEST:
                # Discard this message
                self._dropped_count += 1
                # logger.warning("buffer_overflow_drop_newest",
                #               dropped_count=self._dropped_count)

            elif self._overflow_strategy == OverflowStrategy.DROP_OLDEST:
                # Remove oldest message
                try:
                    self._queue.get_nowait()
                    self._dropped_count += 1
                except asyncio.QueueEmpty:
                    pass

                # Add new message
                try:
                    self._queue.put_nowait(message)
                except asyncio.QueueFull:
                    # Race condition: queue filled again
                    pass

            elif self._overflow_strategy == OverflowStrategy.BLOCK:
                # Wait until space available (backpressure)
                await self._queue.put(message)

    async def get(self) -> Message:
        """
        Retrieve next message from buffer.

        Blocks if buffer is empty.

        Returns:
            Next message in buffer

        Examples:
            >>> message = await buffer.get()
        """
        return await self._queue.get()

    def qsize(self) -> int:
        """
        Current number of messages in buffer.

        Returns:
            Queue size (may be approximate on some platforms)
        """
        return self._queue.qsize()

    def is_full(self) -> bool:
        """Check if buffer is at capacity"""
        return self._queue.qsize() >= self._max_size

    def is_empty(self) -> bool:
        """Check if buffer is empty"""
        return self._queue.empty()

    @property
    def dropped_count(self) -> int:
        """Number of messages dropped due to overflow"""
        return self._dropped_count
```

---

## State Management Structures

### State Helpers for Transformations

Stateful transformations need to maintain state across messages.

### Latest State Helper

```python
class Latest:
    """
    Keep latest message per channel.

    Use for: Combining messages from multiple channels.
    """

    def __init__(self):
        self._latest: dict[str, Message] = {}

    def update(self, channel: str, message: Message):
        """
        Update latest message for channel.

        Args:
            channel: Channel name
            message: Latest message
        """
        self._latest[channel] = message

    def get(self, channel: str) -> Optional[Message]:
        """
        Get latest message for channel.

        Args:
            channel: Channel name

        Returns:
            Latest message or None if no message received
        """
        return self._latest.get(channel)

    def all(self) -> dict[str, Message]:
        """
        Get all latest messages.

        Returns:
            Dictionary of channel -> latest message
        """
        return self._latest.copy()

    def has_all(self, channels: list[str]) -> bool:
        """
        Check if we have received at least one message from all channels.

        Args:
            channels: List of required channels

        Returns:
            True if all channels have at least one message
        """
        return all(channel in self._latest for channel in channels)
```

### Time Window Helper

```python
from collections import deque

class TimeWindow:
    """
    Time-based sliding window for messages.

    Use for: Aggregations over time (last 5 minutes, etc.)
    """

    def __init__(self, duration: timedelta):
        """
        Initialize time window.

        Args:
            duration: Window duration (e.g., timedelta(minutes=5))
        """
        self._duration = duration
        self._messages: deque[Message] = deque()

    def add(self, message: Message):
        """
        Add message to window.

        Automatically evicts messages older than duration.

        Args:
            message: Message to add
        """
        self._messages.append(message)
        self._evict_old(message.timestamp)

    def _evict_old(self, now: datetime):
        """Remove messages older than window duration"""
        cutoff = now - self._duration
        while self._messages and self._messages[0].timestamp < cutoff:
            self._messages.popleft()

    def all(self) -> list[Message]:
        """
        Get all messages in current window.

        Returns:
            List of messages within time window
        """
        return list(self._messages)

    def count(self) -> int:
        """Number of messages in window"""
        return len(self._messages)

    def values(self) -> list[Any]:
        """Extract values from all messages in window"""
        return [m.value for m in self._messages]
```

### Count Window Helper

```python
class CountWindow:
    """
    Count-based sliding window for messages.

    Use for: Aggregations over N messages (last 10 readings, etc.)
    """

    def __init__(self, max_count: int):
        """
        Initialize count window.

        Args:
            max_count: Maximum messages to keep
        """
        self._buffer: deque[Message] = deque(maxlen=max_count)

    def add(self, message: Message):
        """Add message (auto-evicts oldest if full)"""
        self._buffer.append(message)

    def all(self) -> list[Message]:
        """Get all messages in window"""
        return list(self._buffer)

    def count(self) -> int:
        """Number of messages in window"""
        return len(self._buffer)

    def is_full(self) -> bool:
        """Check if window has max_count messages"""
        return len(self._buffer) == self._buffer.maxlen

    def values(self) -> list[Any]:
        """Extract values from all messages"""
        return [m.value for m in self._buffer]
```

### Cache Helper

```python
class Cache:
    """
    Simple key-value cache with optional TTL.

    Use for: Caching computed values, deduplication state, etc.
    """

    def __init__(self, ttl: Optional[timedelta] = None):
        """
        Initialize cache.

        Args:
            ttl: Optional time-to-live for entries
        """
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = ttl

    def set(self, key: str, value: Any):
        """
        Set cache value.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = (value, datetime.now(timezone.utc))

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]

        # Check TTL
        if self._ttl:
            if datetime.now(timezone.utc) - timestamp > self._ttl:
                # Expired
                del self._cache[key]
                return None

        return value

    def has(self, key: str) -> bool:
        """Check if key exists and is not expired"""
        return self.get(key) is not None

    def clear(self):
        """Clear all entries"""
        self._cache.clear()
```

---

## References

- **Functional Spec**:
  - [03-MESSAGES](../FUNCTIONAL_SPECIFICATION/03-MESSAGES.md) - Message structure
  - [08-BROKER](../FUNCTIONAL_SPECIFICATION/08-BROKER.md) - Subscription requirements
- **QA Decisions**:
  - [Q2.1-Q2.6](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md) - Message design decisions
  - [Q6.2](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md) - Wildcard matching
- **Related Tech Specs**:
  - [TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md) - Concurrency model
  - [TECH-03-BROKER-API](TECH-03-BROKER-API.md) - Broker usage of these structures

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-01](TECH-01-ARCHITECTURE.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-03 →](TECH-03-BROKER-API.md) |
