"""Buffer structures for history management and destination buffering."""

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from cod3s_data.core.message import Message


class OverflowStrategy(Enum):
    """
    Strategy for handling buffer overflow.
    """

    DROP_OLDEST = "drop_oldest"  # Remove oldest message, add new
    DROP_NEWEST = "drop_newest"  # Discard new message
    BLOCK = "block"  # Wait until space available (backpressure)


# History Buffer


class HistoryBuffer:
    """
    Fixed-size ring buffer for channel message history.

    Performance:
    - Append: O(1)
    - Get recent: O(n) where n = requested count
    - Memory: O(max_size * message_size)

    Typical memory: 100 messages * 1KB = 100KB per channel
    """

    def __init__(self, max_size: int = 100, ttl: timedelta | None = None) -> None:
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

    def add(self, message: Message) -> None:
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

    def clear(self) -> None:
        """Clear all messages from buffer."""
        self._buffer.clear()

    def __len__(self) -> int:
        """Number of messages currently in buffer."""
        if self._ttl:
            cutoff = datetime.now(timezone.utc) - self._ttl
            return sum(1 for m in self._buffer if m.timestamp >= cutoff)
        return len(self._buffer)


# Destination Buffer


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
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
    ) -> None:
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
        self._queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=max_size)
        self._overflow_strategy = overflow_strategy
        self._max_size = max_size
        self._dropped_count = 0  # Metrics

    async def put(self, message: Message) -> None:
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
        """Check if buffer is at capacity."""
        return self._queue.qsize() >= self._max_size

    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self._queue.empty()

    @property
    def dropped_count(self) -> int:
        """Number of messages dropped due to overflow."""
        return self._dropped_count


# State Management Structures


class Latest:
    """
    Keep latest message per channel.

    Use for: Combining messages from multiple channels.
    """

    def __init__(self) -> None:
        """Initialize the Latest state helper."""
        self._latest: dict[str, Message] = {}

    def update(self, channel: str, message: Message) -> None:
        """
        Update latest message for channel.

        Args:
            channel: Channel name
            message: Latest message
        """
        self._latest[channel] = message

    def get(self, channel: str) -> Message | None:
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


class TimeWindow:
    """
    Time-based sliding window for messages.

    Use for: Aggregations over time (last 5 minutes, etc.)
    """

    def __init__(self, duration: timedelta) -> None:
        """
        Initialize time window.

        Args:
            duration: Window duration (e.g., timedelta(minutes=5))
        """
        self._duration = duration
        self._messages: deque[Message] = deque()

    def add(self, message: Message) -> None:
        """
        Add message to window.

        Automatically evicts messages older than duration.

        Args:
            message: Message to add
        """
        self._messages.append(message)
        self._evict_old(message.timestamp)

    def _evict_old(self, now: datetime) -> None:
        """Remove messages older than window duration."""
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
        """Number of messages in window."""
        return len(self._messages)

    def values(self) -> list[Any]:
        """Extract values from all messages in window."""
        return [m.value for m in self._messages]


class CountWindow:
    """
    Count-based sliding window for messages.

    Use for: Aggregations over N messages (last 10 readings, etc.)
    """

    def __init__(self, max_count: int) -> None:
        """
        Initialize count window.

        Args:
            max_count: Maximum messages to keep
        """
        self._buffer: deque[Message] = deque(maxlen=max_count)

    def add(self, message: Message) -> None:
        """Add message (auto-evicts oldest if full)."""
        self._buffer.append(message)

    def all(self) -> list[Message]:
        """Get all messages in window."""
        return list(self._buffer)

    def count(self) -> int:
        """Number of messages in window."""
        return len(self._buffer)

    def is_full(self) -> bool:
        """Check if window has max_count messages."""
        return len(self._buffer) == self._buffer.maxlen

    def values(self) -> list[Any]:
        """Extract values from all messages."""
        return [m.value for m in self._buffer]


class Cache:
    """
    Simple key-value cache with optional TTL.

    Use for: Caching computed values, deduplication state, etc.
    """

    def __init__(self, ttl: timedelta | None = None) -> None:
        """
        Initialize cache.

        Args:
            ttl: Optional time-to-live for entries
        """
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = ttl

    def set(self, key: str, value: Any) -> None:
        """
        Set cache value.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = (value, datetime.now(timezone.utc))

    def get(self, key: str) -> Any | None:
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
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()
