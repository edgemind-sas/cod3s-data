"""Unit tests for observability."""

import asyncio
import logging
from io import StringIO

import pytest
import structlog

from cod3s_data.broker.in_memory import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.observability import (
    MetricsCollector,
    configure_logging,
    emit_metric,
    emit_metric_async,
    get_logger,
    get_metrics_broker,
    set_metrics_broker,
)


class TestLogging:
    def test_configure_logging_console_format(self):
        """Test console format configuration."""
        configure_logging(level="DEBUG", format="console", enable_colors=False)
        logger = get_logger(__name__)
        assert logger is not None

    def test_configure_logging_json_format(self):
        """Test JSON format configuration."""
        configure_logging(level="INFO", format="json")
        logger = get_logger(__name__)
        assert logger is not None

    def test_get_logger_with_name(self):
        """Test getting logger with name."""
        logger = get_logger("test_logger")
        assert logger is not None

    def test_get_logger_with_context(self):
        """Test getting logger with initial context."""
        logger = get_logger(__name__, component="test", node_id="node-1")
        assert logger is not None

    def test_logging_output_structure(self):
        """Test that logging produces structured output."""
        configure_logging(level="DEBUG", format="console")
        logger = get_logger(__name__)

        # Test that logging calls don't raise exceptions
        logger.info("test_message", key="value", count=42)
        # If we get here, logging works

    def test_logging_levels(self):
        """Test different logging levels."""
        configure_logging(level="DEBUG", format="console")
        logger = get_logger(__name__)

        # Test that all levels work without raising
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        # If we get here, all levels work


class TestMetrics:
    @pytest.mark.asyncio
    async def test_set_get_metrics_broker(self):
        """Test setting and getting metrics broker."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        set_metrics_broker(broker)
        assert get_metrics_broker() is broker

        await broker.stop()

    @pytest.mark.asyncio
    async def test_emit_metric_without_broker(self):
        """Test that emit_metric without broker doesn't crash."""
        set_metrics_broker(None)
        emit_metric("test.metric", 1.0, tags={"key": "value"})
        # Should not raise

    @pytest.mark.asyncio
    async def test_emit_metric_async(self):
        """Test async metric emission."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        set_metrics_broker(broker)

        # Subscribe to metrics channel
        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        # Emit metric
        await emit_metric_async("test.counter", 42, tags={"source": "test"})

        # Wait for message
        await asyncio.sleep(0.1)

        # Check message received
        assert len(messages) == 1
        assert messages[0].key == "test.counter"
        assert messages[0].value == 42
        assert messages[0].tags["source"] == "test"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_emit_metric_sync(self):
        """Test sync metric emission."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        set_metrics_broker(broker)

        # Subscribe to metrics channel
        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        # Emit metric (sync wrapper)
        emit_metric("test.gauge", 3.14, tags={"unit": "radians"})

        # Wait for async task to complete
        await asyncio.sleep(0.1)

        # Check message received
        assert len(messages) == 1
        assert messages[0].key == "test.gauge"
        assert messages[0].value == 3.14
        assert messages[0].tags["unit"] == "radians"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_emit_metric_custom_channel_prefix(self):
        """Test metric emission with custom channel prefix."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        # Subscribe to custom metrics channel
        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("custom_metrics.**", collect_metrics)

        # Emit with custom prefix
        await emit_metric_async(
            "test.metric",
            100,
            channel_prefix="custom_metrics",
            broker=broker,
        )

        await asyncio.sleep(0.1)

        assert len(messages) == 1
        assert messages[0].value == 100

        await broker.stop()


class TestMetricsCollector:
    @pytest.mark.asyncio
    async def test_metrics_collector_increment(self):
        """Test incrementing counters."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        collector = MetricsCollector("test", broker=broker)
        collector.increment("requests")
        collector.increment("requests")
        collector.increment("requests", 3)

        await collector.flush()
        await asyncio.sleep(0.1)

        # Should have one message with value=5 (1+1+3)
        assert len(messages) == 1
        assert messages[0].key == "test.requests"
        assert messages[0].value == 5

        await broker.stop()

    @pytest.mark.asyncio
    async def test_metrics_collector_set(self):
        """Test setting gauges."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        collector = MetricsCollector("test", broker=broker)
        collector.set("queue_size", 10)
        collector.set("queue_size", 20)  # Overwrite

        await collector.flush()
        await asyncio.sleep(0.1)

        assert len(messages) == 1
        assert messages[0].key == "test.queue_size"
        assert messages[0].value == 20

        await broker.stop()

    @pytest.mark.asyncio
    async def test_metrics_collector_with_default_tags(self):
        """Test collector with default tags."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        collector = MetricsCollector(
            "source",
            tags={"component": "random_source", "node": "node-1"},
            broker=broker,
        )
        collector.increment("messages_produced")

        await collector.flush()
        await asyncio.sleep(0.1)

        assert len(messages) == 1
        assert messages[0].tags["component"] == "random_source"
        assert messages[0].tags["node"] == "node-1"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_metrics_collector_with_extra_tags(self):
        """Test flush with extra tags."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        collector = MetricsCollector("test", tags={"base": "tag"}, broker=broker)
        collector.increment("counter")

        await collector.flush(extra_tags={"extra": "tag"})
        await asyncio.sleep(0.1)

        assert len(messages) == 1
        assert messages[0].tags["base"] == "tag"
        assert messages[0].tags["extra"] == "tag"

        await broker.stop()

    @pytest.mark.asyncio
    async def test_metrics_collector_reset(self):
        """Test reset without emitting."""
        collector = MetricsCollector("test")
        collector.increment("counter", 10)
        collector.set("gauge", 42)

        collector.reset()

        # After reset, flush should emit nothing (if broker was set)
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        collector.broker = broker

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        await collector.flush()
        await asyncio.sleep(0.1)

        assert len(messages) == 0

        await broker.stop()

    @pytest.mark.asyncio
    async def test_metrics_collector_flush_without_broker(self):
        """Test flush without broker doesn't crash."""
        collector = MetricsCollector("test", broker=None)
        collector.increment("counter")
        collector.set("gauge", 42)

        await collector.flush()  # Should not raise

    @pytest.mark.asyncio
    async def test_metrics_collector_multiple_metrics(self):
        """Test collector with multiple counters and gauges."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        collector = MetricsCollector("pipeline", broker=broker)
        collector.increment("messages_in", 100)
        collector.increment("messages_out", 95)
        collector.increment("errors", 5)
        collector.set("latency_ms", 42.5)
        collector.set("queue_depth", 10)

        await collector.flush()
        await asyncio.sleep(0.1)

        # Should have 5 metrics
        assert len(messages) == 5

        # Check all metrics present
        keys = {msg.key for msg in messages}
        assert "pipeline.messages_in" in keys
        assert "pipeline.messages_out" in keys
        assert "pipeline.errors" in keys
        assert "pipeline.latency_ms" in keys
        assert "pipeline.queue_depth" in keys

        await broker.stop()

    @pytest.mark.asyncio
    async def test_metrics_collector_namespace(self):
        """Test collector namespace."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        messages: list[Message] = []

        async def collect_metrics(msg: Message) -> None:
            messages.append(msg)

        broker.subscribe("_metrics.**", collect_metrics)

        # Different namespaces
        collector1 = MetricsCollector("source", broker=broker)
        collector2 = MetricsCollector("transform", broker=broker)

        collector1.increment("count")
        collector2.increment("count")

        await collector1.flush()
        await collector2.flush()
        await asyncio.sleep(0.1)

        assert len(messages) == 2
        keys = [msg.key for msg in messages]
        assert "source.count" in keys
        assert "transform.count" in keys

        await broker.stop()
