"""Unit tests for test sources (RandomSource, SequenceSource)."""

import asyncio
from datetime import datetime, timezone

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.sources import BatchMode, RandomSource, SequenceSource


class TestRandomSource:
    """Test RandomSource."""

    @pytest.mark.asyncio
    async def test_random_source_generates_messages(self):
        """Test that RandomSource generates messages."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create source with max_messages
        source = RandomSource(
            broker=broker,
            channel="test.channel",
            rate=100.0,  # Fast rate for testing
            min_value=0.0,
            max_value=10.0,
            max_messages=5,
        )

        # Run source
        await source.start()

        await asyncio.sleep(0.1)

        # Should have received 5 messages
        assert len(received) == 5

        # Check message values
        for msg in received:
            assert 0.0 <= msg.value <= 10.0
            assert msg.key == "random_value"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_random_source_respects_rate(self):
        """Test that RandomSource respects the rate parameter."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create source with slow rate
        source = RandomSource(
            broker=broker,
            channel="test.channel",
            rate=10.0,  # 10 messages per second
            max_messages=3,
        )

        start_time = datetime.now(timezone.utc)
        await source.start()
        end_time = datetime.now(timezone.utc)

        # Should take at least 0.2 seconds for 3 messages at 10/sec
        elapsed = (end_time - start_time).total_seconds()
        assert elapsed >= 0.2

        await broker.stop()

    @pytest.mark.asyncio
    async def test_random_source_custom_key(self):
        """Test that RandomSource uses custom key."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        source = RandomSource(
            broker=broker,
            channel="test.channel",
            key="custom_key",
            max_messages=2,
        )

        await source.start()
        await asyncio.sleep(0.05)

        assert all(msg.key == "custom_key" for msg in received)

        await broker.stop()

    @pytest.mark.asyncio
    async def test_random_source_can_stop(self):
        """Test that RandomSource can be stopped."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        # Create REALTIME source (no max_messages)
        source = RandomSource(
            broker=broker,
            channel="test.channel",
            rate=100.0,
        )

        # Start source in background
        source_task = asyncio.create_task(source.start())

        await asyncio.sleep(0.05)

        # Stop source
        await source.stop()

        # Wait for task to complete
        await asyncio.wait_for(source_task, timeout=1.0)

        assert not source.is_running

        await broker.stop()


class TestSequenceSource:
    """Test SequenceSource."""

    @pytest.mark.asyncio
    async def test_sequence_source_generates_sequence(self):
        """Test that SequenceSource generates sequential numbers."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create sequence source
        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=5,
            step_value=1,
            rate=100.0,
        )

        await source.start()
        await asyncio.sleep(0.1)

        # Should have 5 messages (0, 1, 2, 3, 4)
        assert len(received) == 5

        # Check sequence
        assert [msg.value for msg in received] == [0, 1, 2, 3, 4]

        await broker.stop()

    @pytest.mark.asyncio
    async def test_sequence_source_with_step(self):
        """Test SequenceSource with custom step."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create sequence with step=2
        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=10,
            step_value=2,
            rate=100.0,
        )

        await source.start()
        await asyncio.sleep(0.1)

        # Should have messages (0, 2, 4, 6, 8)
        assert [msg.value for msg in received] == [0, 2, 4, 6, 8]

        await broker.stop()

    @pytest.mark.asyncio
    async def test_sequence_source_negative_step(self):
        """Test SequenceSource with negative step."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        # Create sequence counting down (no end for negative step to work properly in realtime mode)
        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=5,
            end_value=None,  # Unlimited for realtime mode
            step_value=-1,
            rate=100.0,
        )

        # Run for short time
        source_task = asyncio.create_task(source.start())
        await asyncio.sleep(0.1)
        await source.stop()
        await asyncio.wait_for(source_task, timeout=1.0)

        # Should have counted down
        assert len(received) > 0
        assert received[0].value == 5
        if len(received) > 1:
            assert received[1].value == 4

        await broker.stop()

    @pytest.mark.asyncio
    async def test_sequence_source_tags(self):
        """Test that SequenceSource adds tags."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=2,
            rate=100.0,
        )

        await source.start()
        await asyncio.sleep(0.05)

        # Check tags
        assert "sequence_value" in received[0].tags
        assert received[0].tags["sequence_value"] == "0"
        assert received[1].tags["sequence_value"] == "1"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_sequence_source_batch_mode(self):
        """Test that SequenceSource with end is BATCH mode."""
        broker = InMemoryBroker(enable_metrics=False)

        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=10,
        )

        assert source.batch_mode == BatchMode.BATCH

    @pytest.mark.asyncio
    async def test_sequence_source_realtime_mode(self):
        """Test that SequenceSource without end is REALTIME mode."""
        broker = InMemoryBroker(enable_metrics=False)

        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=None,
        )

        assert source.batch_mode == BatchMode.REALTIME


class TestSourceLifecycle:
    """Test source lifecycle management."""

    @pytest.mark.asyncio
    async def test_source_message_count(self):
        """Test that source tracks message count."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        source = SequenceSource(
            broker=broker,
            channel="test.channel",
            start_value=0,
            end_value=5,
            rate=100.0,
        )

        await source.start()

        assert source.message_count == 5

        await broker.stop()

    @pytest.mark.asyncio
    async def test_source_is_running(self):
        """Test source running state."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        source = RandomSource(
            broker=broker,
            channel="test.channel",
            rate=100.0,
        )

        assert not source.is_running

        # Start in background
        source_task = asyncio.create_task(source.start())

        await asyncio.sleep(0.01)
        assert source.is_running

        await source.stop()
        await asyncio.wait_for(source_task, timeout=1.0)

        assert not source.is_running

        await broker.stop()

    @pytest.mark.asyncio
    async def test_source_pause_resume(self):
        """Test source pause and resume."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received = []

        async def callback(msg: Message):
            received.append(msg)

        broker.subscribe("test.channel", callback)

        source = RandomSource(
            broker=broker,
            channel="test.channel",
            rate=50.0,  # 50 msg/sec
        )

        # Start source
        source_task = asyncio.create_task(source.start())

        # Let it run for a bit
        await asyncio.sleep(0.05)
        count_before_pause = len(received)

        # Pause
        await source.pause()
        await asyncio.sleep(0.1)

        # Should not receive new messages while paused
        count_after_pause = len(received)
        assert count_after_pause == count_before_pause

        # Resume
        await source.resume()
        await asyncio.sleep(0.05)

        # Should receive new messages
        count_after_resume = len(received)
        assert count_after_resume > count_after_pause

        await source.stop()
        await asyncio.wait_for(source_task, timeout=1.0)

        await broker.stop()
