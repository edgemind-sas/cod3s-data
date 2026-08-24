"""Unit tests for destinations."""

import asyncio
import tempfile
from datetime import UTC
from pathlib import Path

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.buffers import OverflowStrategy
from cod3s_data.core.message import Message
from cod3s_data.destinations import (
    CollectDestination,
    FileDestination,
    InMemoryDestination,
    RetryStrategy,
)
from cod3s_data.sources import SequenceSource


def create_message(key: str = "test", value: float = 42.0) -> Message:
    from datetime import datetime

    return Message(key=key, timestamp=datetime.now(UTC), value=value, tags={})


class TestInMemoryDestination:
    @pytest.mark.asyncio
    async def test_collects_messages(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = InMemoryDestination(broker, "test.channel")
        await dest.start()

        await broker.publish("test.channel", create_message(value=1.0))
        await broker.publish("test.channel", create_message(value=2.0))
        await asyncio.sleep(0.05)

        assert len(dest.get_all()) == 2
        assert dest.get_all()[0].value == 1.0

        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = InMemoryDestination(broker, "test.**")
        await dest.start()

        await broker.publish("test.channel1", create_message(value=1.0))
        await broker.publish("test.channel2", create_message(value=2.0))
        await asyncio.sleep(0.05)

        assert len(dest.get_all()) == 2

        await dest.stop()
        await broker.stop()


class TestFileDestination:
    @pytest.mark.asyncio
    async def test_writes_to_file(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            file_path = Path(f.name)

        try:
            dest = FileDestination(broker, "test.channel", file_path, batch_size=1)
            await dest.start()

            await broker.publish("test.channel", create_message(value=1.0))
            await broker.publish("test.channel", create_message(value=2.0))
            await asyncio.sleep(0.1)

            await dest.stop()

            content = file_path.read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2

        finally:
            file_path.unlink()
            await broker.stop()

    @pytest.mark.asyncio
    async def test_append_mode(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
            file_path = Path(f.name)
            f.write('{"existing":"line"}\n')

        try:
            dest = FileDestination(broker, "test.channel", file_path, append=True, batch_size=1)
            await dest.start()

            await broker.publish("test.channel", create_message(value=1.0))
            await asyncio.sleep(0.1)

            await dest.stop()

            content = file_path.read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2
            assert "existing" in lines[0]

        finally:
            file_path.unlink()
            await broker.stop()


class TestCollectDestination:
    @pytest.mark.asyncio
    async def test_collect_and_assert(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "test.channel")
        await dest.start()

        await broker.publish("test.channel", create_message(value=1.0))
        await broker.publish("test.channel", create_message(value=2.0))
        await asyncio.sleep(0.05)

        dest.assert_count(2)
        dest.assert_min_count(1)

        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_filter_by(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "test.channel")
        await dest.start()

        from datetime import datetime

        msg1 = Message(key="temp", timestamp=datetime.now(UTC), value=1.0, tags={"sensor": "A"})
        msg2 = Message(key="temp", timestamp=datetime.now(UTC), value=2.0, tags={"sensor": "B"})
        msg3 = Message(key="pressure", timestamp=datetime.now(UTC), value=3.0, tags={"sensor": "A"})

        await broker.publish("test.channel", msg1)
        await broker.publish("test.channel", msg2)
        await broker.publish("test.channel", msg3)
        await asyncio.sleep(0.05)

        temp_msgs = dest.filter_by(key="temp")
        assert len(temp_msgs) == 2

        sensor_a = dest.filter_by(sensor="A")
        assert len(sensor_a) == 2

        await dest.stop()
        await broker.stop()


class TestDestinationBuffering:
    @pytest.mark.asyncio
    async def test_buffer_overflow_drop_oldest(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = InMemoryDestination(
            broker, "test.channel", buffer_size=5, overflow_strategy=OverflowStrategy.DROP_OLDEST
        )
        await dest.start()

        for i in range(10):
            await broker.publish("test.channel", create_message(value=float(i)))

        await asyncio.sleep(0.1)
        await dest.stop()

        messages = dest.get_all()
        assert len(messages) <= 5

        await broker.stop()


class TestDestinationRetry:
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        class FailingDestination(InMemoryDestination):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.attempt_count = 0

            async def write(self, message: Message) -> None:
                self.attempt_count += 1
                if self.attempt_count < 3:
                    raise RuntimeError("Temporary failure")
                await super().write(message)

        dest = FailingDestination(
            broker, "test.channel", retry_attempts=5, retry_strategy=RetryStrategy.FIXED
        )
        await dest.start()

        await broker.publish("test.channel", create_message(value=1.0))
        await asyncio.sleep(4.0)  # Need time for retries with 1s fixed backoff

        assert dest.attempt_count >= 3
        assert len(dest.get_all()) == 1

        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_dlq_on_exhausted_retries(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dlq_messages = []

        async def dlq_callback(msg: Message):
            dlq_messages.append(msg)

        broker.subscribe("dlq.channel", dlq_callback)

        class AlwaysFailingDestination(InMemoryDestination):
            async def write(self, message: Message) -> None:
                raise RuntimeError("Always fails")

        dest = AlwaysFailingDestination(
            broker,
            "test.channel",
            retry_attempts=2,
            retry_strategy=RetryStrategy.FIXED,
            dlq_channel="dlq.channel",
        )
        await dest.start()

        await broker.publish("test.channel", create_message(value=1.0))
        await asyncio.sleep(3.0)  # Need time for retries: 1s + 1s for 2 attempts

        assert len(dlq_messages) == 1
        assert dest.error_count == 1

        await dest.stop()
        await broker.stop()


class TestDestinationLifecycle:
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = InMemoryDestination(broker, "test.channel")
        await dest.start()

        await broker.publish("test.channel", create_message(value=1.0))
        await broker.publish("test.channel", create_message(value=2.0))

        await dest.stop()

        messages = dest.get_all()
        assert len(messages) == 2
        assert not dest.is_running

        await broker.stop()

    @pytest.mark.asyncio
    async def test_message_count_tracking(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = InMemoryDestination(broker, "test.channel")
        await dest.start()

        for i in range(5):
            await broker.publish("test.channel", create_message(value=float(i)))

        await asyncio.sleep(0.1)

        assert dest.message_count == 5

        await dest.stop()
        await broker.stop()


class TestDestinationIntegration:
    @pytest.mark.asyncio
    async def test_source_to_destination_pipeline(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = InMemoryDestination(broker, "test.channel")
        await dest.start()

        source = SequenceSource(broker, "test.channel", start_value=0, end_value=5, rate=100.0)

        await source.start()
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 5
        assert [m.value for m in messages] == [0, 1, 2, 3, 4]

        await dest.stop()
        await broker.stop()
