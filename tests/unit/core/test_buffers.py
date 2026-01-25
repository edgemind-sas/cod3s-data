"""Unit tests for buffer classes."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from cod3s_data.core.buffers import (
    Cache,
    CountWindow,
    DestinationBuffer,
    HistoryBuffer,
    Latest,
    OverflowStrategy,
    TimeWindow,
)
from cod3s_data.core.message import Message


def create_message(key: str = "temp", value: float = 42.0, **kwargs) -> Message:
    """Helper to create test messages."""
    return Message(
        key=key,
        timestamp=kwargs.get("timestamp", datetime.now(timezone.utc)),
        value=value,
        tags=kwargs.get("tags", {}),
    )


class TestHistoryBuffer:
    """Test HistoryBuffer class."""

    def test_add_message(self):
        """Test adding messages to buffer."""
        buffer = HistoryBuffer(max_size=10)
        msg = create_message()

        buffer.add(msg)

        assert len(buffer) == 1

    def test_get_recent(self):
        """Test retrieving recent messages."""
        buffer = HistoryBuffer(max_size=10)

        # Add 5 messages
        for i in range(5):
            buffer.add(create_message(value=float(i)))

        # Get 3 most recent (newest first)
        recent = buffer.get_recent(3)

        assert len(recent) == 3
        # Newest first
        assert recent[0].value == 4.0
        assert recent[1].value == 3.0
        assert recent[2].value == 2.0

    def test_get_all(self):
        """Test getting all messages."""
        buffer = HistoryBuffer(max_size=10)

        for i in range(5):
            buffer.add(create_message(value=float(i)))

        all_msgs = buffer.get_all()

        assert len(all_msgs) == 5
        # Newest first
        assert all_msgs[0].value == 4.0

    def test_max_size_eviction(self):
        """Test that buffer evicts oldest when full."""
        buffer = HistoryBuffer(max_size=3)

        # Add 5 messages
        for i in range(5):
            buffer.add(create_message(value=float(i)))

        # Only last 3 should remain
        assert len(buffer) == 3

        all_msgs = buffer.get_all()
        assert all_msgs[0].value == 4.0  # Newest
        assert all_msgs[1].value == 3.0
        assert all_msgs[2].value == 2.0  # Oldest remaining

    def test_ttl_filtering(self):
        """Test TTL-based message filtering."""
        buffer = HistoryBuffer(max_size=10, ttl=timedelta(seconds=1))

        # Add old message
        old_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        buffer.add(create_message(value=1.0, timestamp=old_time))

        # Add recent message
        buffer.add(create_message(value=2.0))

        # Only recent message should be returned (TTL filtered)
        recent = buffer.get_recent(10)
        assert len(recent) == 1
        assert recent[0].value == 2.0

    def test_clear(self):
        """Test clearing buffer."""
        buffer = HistoryBuffer(max_size=10)

        for i in range(5):
            buffer.add(create_message(value=float(i)))

        buffer.clear()

        assert len(buffer) == 0
        assert len(buffer.get_all()) == 0


class TestDestinationBuffer:
    """Test DestinationBuffer class."""

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Test basic put and get operations."""
        buffer = DestinationBuffer(max_size=10)
        msg = create_message()

        await buffer.put(msg)
        retrieved = await buffer.get()

        assert retrieved == msg

    @pytest.mark.asyncio
    async def test_qsize(self):
        """Test queue size reporting."""
        buffer = DestinationBuffer(max_size=10)

        assert buffer.qsize() == 0

        await buffer.put(create_message())
        assert buffer.qsize() == 1

        await buffer.put(create_message())
        assert buffer.qsize() == 2

        await buffer.get()
        assert buffer.qsize() == 1

    @pytest.mark.asyncio
    async def test_is_empty(self):
        """Test empty check."""
        buffer = DestinationBuffer(max_size=10)

        assert buffer.is_empty()

        await buffer.put(create_message())
        assert not buffer.is_empty()

        await buffer.get()
        assert buffer.is_empty()

    @pytest.mark.asyncio
    async def test_is_full(self):
        """Test full check."""
        buffer = DestinationBuffer(max_size=3)

        assert not buffer.is_full()

        await buffer.put(create_message())
        await buffer.put(create_message())
        assert not buffer.is_full()

        await buffer.put(create_message())
        assert buffer.is_full()

    @pytest.mark.asyncio
    async def test_drop_oldest_strategy(self):
        """Test DROP_OLDEST overflow strategy."""
        buffer = DestinationBuffer(
            max_size=3, overflow_strategy=OverflowStrategy.DROP_OLDEST
        )

        # Fill buffer
        for i in range(3):
            await buffer.put(create_message(value=float(i)))

        # Add one more (should drop oldest)
        await buffer.put(create_message(value=3.0))

        # Should still have 3 messages
        assert buffer.qsize() == 3
        assert buffer.dropped_count == 1

        # Oldest should be dropped (0), newest should be present
        msgs = []
        while not buffer.is_empty():
            msgs.append(await buffer.get())

        values = [msg.value for msg in msgs]
        assert 0.0 not in values
        assert 3.0 in values

    @pytest.mark.asyncio
    async def test_drop_newest_strategy(self):
        """Test DROP_NEWEST overflow strategy."""
        buffer = DestinationBuffer(
            max_size=3, overflow_strategy=OverflowStrategy.DROP_NEWEST
        )

        # Fill buffer
        for i in range(3):
            await buffer.put(create_message(value=float(i)))

        # Try to add one more (should be dropped)
        await buffer.put(create_message(value=3.0))

        # Should still have 3 messages
        assert buffer.qsize() == 3
        assert buffer.dropped_count == 1

        # Newest should be dropped (3), oldest should remain
        msgs = []
        while not buffer.is_empty():
            msgs.append(await buffer.get())

        values = [msg.value for msg in msgs]
        assert 3.0 not in values
        assert 0.0 in values

    @pytest.mark.asyncio
    async def test_block_strategy(self):
        """Test BLOCK overflow strategy."""
        buffer = DestinationBuffer(max_size=3, overflow_strategy=OverflowStrategy.BLOCK)

        # Fill buffer
        for i in range(3):
            await buffer.put(create_message(value=float(i)))

        # Try to add another (should block)
        put_task = asyncio.create_task(buffer.put(create_message(value=3.0)))

        # Give put_task a chance to start
        await asyncio.sleep(0.01)

        # Should be blocked
        assert not put_task.done()

        # Get one message to make space
        await buffer.get()

        # Now put should complete
        await asyncio.wait_for(put_task, timeout=1.0)

        assert buffer.qsize() == 3


class TestLatest:
    """Test Latest state helper."""

    def test_update_and_get(self):
        """Test updating and retrieving latest messages."""
        latest = Latest()
        msg1 = create_message(value=1.0)
        msg2 = create_message(value=2.0)

        latest.update("temp", msg1)
        latest.update("pressure", msg2)

        assert latest.get("temp") == msg1
        assert latest.get("pressure") == msg2

    def test_get_nonexistent(self):
        """Test getting nonexistent channel."""
        latest = Latest()

        assert latest.get("nonexistent") is None

    def test_update_overwrites(self):
        """Test that update overwrites previous value."""
        latest = Latest()
        msg1 = create_message(value=1.0)
        msg2 = create_message(value=2.0)

        latest.update("temp", msg1)
        latest.update("temp", msg2)

        assert latest.get("temp") == msg2

    def test_all(self):
        """Test getting all latest messages."""
        latest = Latest()
        msg1 = create_message(value=1.0)
        msg2 = create_message(value=2.0)

        latest.update("temp", msg1)
        latest.update("pressure", msg2)

        all_msgs = latest.all()

        assert len(all_msgs) == 2
        assert all_msgs["temp"] == msg1
        assert all_msgs["pressure"] == msg2

    def test_has_all(self):
        """Test checking if all channels have messages."""
        latest = Latest()

        assert not latest.has_all(["temp", "pressure"])

        latest.update("temp", create_message())
        assert not latest.has_all(["temp", "pressure"])

        latest.update("pressure", create_message())
        assert latest.has_all(["temp", "pressure"])


class TestTimeWindow:
    """Test TimeWindow state helper."""

    def test_add_and_count(self):
        """Test adding messages and counting."""
        window = TimeWindow(duration=timedelta(minutes=5))

        msg = create_message()
        window.add(msg)

        assert window.count() == 1

    def test_time_based_eviction(self):
        """Test that old messages are evicted."""
        window = TimeWindow(duration=timedelta(seconds=1))

        # Add old message
        old_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        window.add(create_message(value=1.0, timestamp=old_time))

        # Add recent message (triggers eviction)
        window.add(create_message(value=2.0))

        # Only recent message should remain
        assert window.count() == 1
        assert window.all()[0].value == 2.0

    def test_all_messages(self):
        """Test getting all messages in window."""
        window = TimeWindow(duration=timedelta(minutes=5))

        for i in range(3):
            window.add(create_message(value=float(i)))

        all_msgs = window.all()

        assert len(all_msgs) == 3

    def test_values(self):
        """Test extracting values from window."""
        window = TimeWindow(duration=timedelta(minutes=5))

        for i in range(3):
            window.add(create_message(value=float(i)))

        values = window.values()

        assert values == [0.0, 1.0, 2.0]


class TestCountWindow:
    """Test CountWindow state helper."""

    def test_add_and_count(self):
        """Test adding messages and counting."""
        window = CountWindow(max_count=5)

        for i in range(3):
            window.add(create_message(value=float(i)))

        assert window.count() == 3

    def test_max_count_eviction(self):
        """Test that oldest messages are evicted when max reached."""
        window = CountWindow(max_count=3)

        # Add 5 messages
        for i in range(5):
            window.add(create_message(value=float(i)))

        # Only last 3 should remain
        assert window.count() == 3

        values = window.values()
        assert values == [2.0, 3.0, 4.0]

    def test_is_full(self):
        """Test full check."""
        window = CountWindow(max_count=3)

        assert not window.is_full()

        window.add(create_message())
        window.add(create_message())
        assert not window.is_full()

        window.add(create_message())
        assert window.is_full()

    def test_all_messages(self):
        """Test getting all messages."""
        window = CountWindow(max_count=5)

        for i in range(3):
            window.add(create_message(value=float(i)))

        all_msgs = window.all()

        assert len(all_msgs) == 3

    def test_values(self):
        """Test extracting values."""
        window = CountWindow(max_count=5)

        for i in range(3):
            window.add(create_message(value=float(i)))

        values = window.values()

        assert values == [0.0, 1.0, 2.0]


class TestCache:
    """Test Cache helper."""

    def test_set_and_get(self):
        """Test setting and getting cache values."""
        cache = Cache()

        cache.set("key1", "value1")
        cache.set("key2", 42)

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == 42

    def test_get_nonexistent(self):
        """Test getting nonexistent key."""
        cache = Cache()

        assert cache.get("nonexistent") is None

    def test_overwrite(self):
        """Test that setting same key overwrites."""
        cache = Cache()

        cache.set("key", "value1")
        cache.set("key", "value2")

        assert cache.get("key") == "value2"

    def test_has(self):
        """Test checking if key exists."""
        cache = Cache()

        assert not cache.has("key")

        cache.set("key", "value")
        assert cache.has("key")

    def test_ttl_expiration(self):
        """Test TTL-based expiration."""
        import time

        cache = Cache(ttl=timedelta(milliseconds=100))

        cache.set("key", "value")
        assert cache.get("key") == "value"

        # Wait for expiration
        time.sleep(0.2)

        # Should be expired
        assert cache.get("key") is None
        assert not cache.has("key")

    def test_clear(self):
        """Test clearing cache."""
        cache = Cache()

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_ttl_per_entry(self):
        """Test that TTL is checked per entry."""
        import time

        cache = Cache(ttl=timedelta(milliseconds=100))

        cache.set("key1", "value1")
        time.sleep(0.06)  # 60ms
        cache.set("key2", "value2")

        # After 120ms total (60ms + 60ms), key1 should be expired but key2 should still be valid
        time.sleep(0.06)  # Another 60ms

        assert cache.get("key1") is None  # key1 age: 120ms > 100ms TTL
        assert cache.get("key2") == "value2"  # key2 age: 60ms < 100ms TTL
