"""Unit tests for InMemoryBroker."""

import asyncio
from datetime import UTC, datetime

import pytest

from cod3s_data.broker import (
    HistoryMode,
    InMemoryBroker,
    InvalidChannelError,
    InvalidPatternError,
)
from cod3s_data.core.message import Message


def create_message(key: str = "temp", value: float = 42.0, **kwargs) -> Message:
    """Helper to create test messages."""
    return Message(
        key=key,
        timestamp=kwargs.get("timestamp", datetime.now(UTC)),
        value=value,
        tags=kwargs.get("tags", {}),
    )


class TestBasicPublishSubscribe:
    """Test basic publish/subscribe functionality."""

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        """Test basic message publication and subscription."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe
        broker.subscribe("test.channel", callback)

        # Publish
        msg = create_message()
        result = await broker.publish("test.channel", msg)

        # Wait for async delivery
        await asyncio.sleep(0.01)

        assert result.success
        assert result.subscriber_count == 1
        assert len(received) == 1
        assert received[0] == msg

        await broker.stop()

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self):
        """Test publishing to multiple subscribers."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received1 = []
        received2 = []

        async def callback1(msg: Message):
            received1.append(msg)

        async def callback2(msg: Message):
            received2.append(msg)

        # Subscribe with two callbacks
        broker.subscribe("test.channel", callback1)
        broker.subscribe("test.channel", callback2)

        # Publish
        msg = create_message()
        result = await broker.publish("test.channel", msg)

        await asyncio.sleep(0.01)

        assert result.subscriber_count == 2
        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0] == msg
        assert received2[0] == msg

        await broker.stop()

    @pytest.mark.asyncio
    async def test_publish_with_no_subscribers(self):
        """Test publishing with no subscribers."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        msg = create_message()
        result = await broker.publish("test.channel", msg)

        assert result.success
        assert result.subscriber_count == 0

        await broker.stop()


class TestWildcardSubscriptions:
    """Test wildcard subscription patterns."""

    @pytest.mark.asyncio
    async def test_single_level_wildcard(self):
        """Test single-level wildcard subscriptions."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe with wildcard
        broker.subscribe("sensors.*.temp", callback)

        # Publish to matching channels
        msg1 = create_message(value=1.0)
        await broker.publish("sensors.printer1.temp", msg1)

        msg2 = create_message(value=2.0)
        await broker.publish("sensors.printer2.temp", msg2)

        # Publish to non-matching channel
        msg3 = create_message(value=3.0)
        await broker.publish("sensors.temp", msg3)

        await asyncio.sleep(0.01)

        # Should receive only matching messages
        assert len(received) == 2
        assert received[0].value == 1.0
        assert received[1].value == 2.0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_multi_level_wildcard(self):
        """Test multi-level wildcard subscriptions."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe with multi-level wildcard
        broker.subscribe("sensors.**", callback)

        # Publish to various depths
        await broker.publish("sensors.temp", create_message(value=1.0))
        await broker.publish("sensors.printer1.temp", create_message(value=2.0))
        await broker.publish("sensors.printer1.zone1.temp", create_message(value=3.0))

        # Non-matching
        await broker.publish("alerts.temp", create_message(value=4.0))

        await asyncio.sleep(0.01)

        # Should receive all under sensors.**
        assert len(received) == 3

        await broker.stop()

    @pytest.mark.asyncio
    async def test_exact_and_wildcard_both_match(self):
        """Test that both exact and wildcard subscriptions receive messages."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        exact_received = []
        wildcard_received = []

        async def exact_callback(msg: Message):
            exact_received.append(msg)

        async def wildcard_callback(msg: Message):
            wildcard_received.append(msg)

        # Subscribe exact and wildcard
        broker.subscribe("sensors.printer1.temp", exact_callback)
        broker.subscribe("sensors.*.temp", wildcard_callback)

        # Publish
        msg = create_message()
        result = await broker.publish("sensors.printer1.temp", msg)

        await asyncio.sleep(0.01)

        assert result.subscriber_count == 2
        assert len(exact_received) == 1
        assert len(wildcard_received) == 1

        await broker.stop()


class TestUnsubscribe:
    """Test unsubscribe functionality."""

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing from a channel."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe
        handle = broker.subscribe("test.channel", callback)

        # Publish
        await broker.publish("test.channel", create_message(value=1.0))
        await asyncio.sleep(0.01)

        assert len(received) == 1

        # Unsubscribe
        broker.unsubscribe(handle)

        # Publish again
        await broker.publish("test.channel", create_message(value=2.0))
        await asyncio.sleep(0.01)

        # Should not receive second message
        assert len(received) == 1

        await broker.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_one_of_many(self):
        """Test unsubscribing one of multiple subscribers."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received1 = []
        received2 = []

        async def callback1(msg: Message):
            received1.append(msg)

        async def callback2(msg: Message):
            received2.append(msg)

        # Subscribe twice
        handle1 = broker.subscribe("test.channel", callback1)
        broker.subscribe("test.channel", callback2)

        # Publish
        await broker.publish("test.channel", create_message(value=1.0))
        await asyncio.sleep(0.01)

        assert len(received1) == 1
        assert len(received2) == 1

        # Unsubscribe first
        broker.unsubscribe(handle1)

        # Publish again
        await broker.publish("test.channel", create_message(value=2.0))
        await asyncio.sleep(0.01)

        # First should not receive, second should
        assert len(received1) == 1
        assert len(received2) == 2

        await broker.stop()


class TestHistory:
    """Test message history functionality."""

    @pytest.mark.asyncio
    async def test_get_history(self):
        """Test retrieving message history."""
        broker = InMemoryBroker(enable_metrics=False, default_history_size=10)
        await broker.start()

        # Publish messages
        for i in range(5):
            await broker.publish("test.channel", create_message(value=float(i)))

        # Get history
        history = broker.get_history("test.channel", count=10)

        assert len(history) == 5
        # Newest first
        assert history[0].value == 4.0
        assert history[4].value == 0.0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_history_limited_by_count(self):
        """Test that history is limited by count parameter."""
        broker = InMemoryBroker(enable_metrics=False, default_history_size=10)
        await broker.start()

        # Publish many messages
        for i in range(10):
            await broker.publish("test.channel", create_message(value=float(i)))

        # Get limited history
        history = broker.get_history("test.channel", count=3)

        assert len(history) == 3
        # Should get newest 3
        assert history[0].value == 9.0
        assert history[1].value == 8.0
        assert history[2].value == 7.0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_history_buffer_size_limit(self):
        """Test that history buffer respects size limit."""
        broker = InMemoryBroker(enable_metrics=False, default_history_size=3)
        await broker.start()

        # Publish more than buffer size
        for i in range(5):
            await broker.publish("test.channel", create_message(value=float(i)))

        # Get all history
        history = broker.get_history("test.channel", count=100)

        # Should only have last 3
        assert len(history) == 3
        assert history[0].value == 4.0
        assert history[2].value == 2.0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_history_nonexistent_channel(self):
        """Test getting history from nonexistent channel."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        history = broker.get_history("nonexistent.channel")

        assert len(history) == 0

        await broker.stop()


class TestHistoryReplay:
    """Test history replay on subscription."""

    @pytest.mark.asyncio
    async def test_subscribe_with_history_none(self):
        """Test subscribing with no history replay."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        # Publish before subscription
        await broker.publish("test.channel", create_message(value=1.0))

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe with NONE history
        broker.subscribe("test.channel", callback, history=HistoryMode.NONE)

        await asyncio.sleep(0.01)

        # Should not receive historical messages
        assert len(received) == 0

        # Publish after subscription
        await broker.publish("test.channel", create_message(value=2.0))
        await asyncio.sleep(0.01)

        # Should receive new message
        assert len(received) == 1
        assert received[0].value == 2.0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_subscribe_with_history_recent(self):
        """Test subscribing with recent history replay."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        # Publish historical messages
        for i in range(5):
            await broker.publish("test.channel", create_message(value=float(i)))

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe with RECENT history (last 3)
        broker.subscribe("test.channel", callback, history=HistoryMode.RECENT, history_count=3)

        await asyncio.sleep(0.05)

        # Should receive last 3 in chronological order (oldest first in replay)
        assert len(received) == 3
        assert received[0].value == 2.0  # Oldest of the 3
        assert received[2].value == 4.0  # Newest of the 3

        await broker.stop()

    @pytest.mark.asyncio
    async def test_subscribe_with_history_all(self):
        """Test subscribing with all history replay."""
        broker = InMemoryBroker(enable_metrics=False, default_history_size=10)
        await broker.start()

        # Publish historical messages
        for i in range(5):
            await broker.publish("test.channel", create_message(value=float(i)))

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Subscribe with ALL history
        broker.subscribe("test.channel", callback, history=HistoryMode.ALL)

        await asyncio.sleep(0.05)

        # Should receive all 5 messages
        assert len(received) == 5
        assert received[0].value == 0.0
        assert received[4].value == 4.0

        await broker.stop()


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_invalid_channel_name(self):
        """Test that empty channel names raise error."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        with pytest.raises(InvalidChannelError):
            await broker.publish("", create_message())

        with pytest.raises(InvalidChannelError):
            await broker.publish("   ", create_message())

        await broker.stop()

    @pytest.mark.asyncio
    async def test_invalid_pattern(self):
        """Test that empty patterns raise error."""
        broker = InMemoryBroker(enable_metrics=False)

        async def callback(msg: Message):
            pass

        with pytest.raises(InvalidPatternError):
            broker.subscribe("", callback)

        with pytest.raises(InvalidPatternError):
            broker.subscribe("   ", callback)

    @pytest.mark.asyncio
    async def test_callback_error_does_not_crash_broker(self):
        """Test that errors in callbacks don't crash the broker."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        good_received = []

        async def bad_callback(msg: Message):
            raise ValueError("Callback error")

        async def good_callback(msg: Message):
            good_received.append(msg)

        # Subscribe with both callbacks
        broker.subscribe("test.channel", bad_callback)
        broker.subscribe("test.channel", good_callback)

        # Publish
        msg = create_message()
        result = await broker.publish("test.channel", msg)

        await asyncio.sleep(0.01)

        # Both callbacks should be notified despite error
        assert result.subscriber_count == 2

        # Good callback should still receive message
        assert len(good_received) == 1

        await broker.stop()


class TestMetrics:
    """Test metrics functionality."""

    @pytest.mark.asyncio
    async def test_metrics_enabled(self):
        """Test that metrics are published when enabled."""
        broker = InMemoryBroker(enable_metrics=True)
        await broker.start()

        metric_received = []

        async def callback(msg: Message):
            metric_received.append(msg)

        # Subscribe to metrics channel
        broker.subscribe("_metrics.**", callback)

        # Publish a message (should generate metrics)
        await broker.publish("test.channel", create_message())

        await asyncio.sleep(0.05)

        # Should receive metrics messages
        assert len(metric_received) > 0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting broker metrics."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        async def callback(msg: Message):
            pass

        broker.subscribe("test.channel", callback)

        # Publish some messages
        for _ in range(3):
            await broker.publish("test.channel", create_message())

        await asyncio.sleep(0.01)

        metrics = broker.get_metrics()

        assert metrics["publish_count"] == 3
        assert metrics["notify_count"] == 3
        assert metrics["subscription_count"] == 1
        assert metrics["channel_count"] == 1

        await broker.stop()


class TestConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_publishes(self):
        """Test concurrent message publishing."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Publish concurrently
        tasks = []
        for i in range(100):
            task = broker.publish("test.channel", create_message(value=float(i)))
            tasks.append(task)

        await asyncio.gather(*tasks)
        await asyncio.sleep(0.1)

        # Should receive all messages
        assert len(received) == 100

        await broker.stop()

    @pytest.mark.asyncio
    async def test_subscribe_during_publish(self):
        """Test subscribing while messages are being published."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        # Start publishing
        async def publish_loop():
            for i in range(10):
                await broker.publish("test.channel", create_message(value=float(i)))
                await asyncio.sleep(0.01)

        publish_task = asyncio.create_task(publish_loop())

        # Subscribe after a few messages
        await asyncio.sleep(0.03)
        broker.subscribe("test.channel", callback)

        await publish_task
        await asyncio.sleep(0.05)

        # Should receive messages published after subscription
        assert len(received) > 0
        assert len(received) < 10

        await broker.stop()
