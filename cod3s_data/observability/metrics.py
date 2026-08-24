"""Metrics-as-messages system for COD3S Data Framework.

Metrics are published as regular messages to _metrics.* channels.
This allows treating metrics like any other data stream - you can
subscribe, transform, and route them through the pipeline.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from cod3s_data.broker.base import Broker, DeliveryGuarantee
from cod3s_data.core.message import Message

# Global broker reference for metrics (set by framework)
_metrics_broker: Broker | None = None


def set_metrics_broker(broker: Broker) -> None:
    """Set the global broker for metrics emission.

    This is typically called by the Framework during initialization.

    Args:
        broker: The broker to use for metrics
    """
    global _metrics_broker
    _metrics_broker = broker


def get_metrics_broker() -> Broker | None:
    """Get the current metrics broker.

    Returns:
        The metrics broker, or None if not set
    """
    return _metrics_broker


def emit_metric(
    metric_name: str,
    value: float | int,
    *,
    tags: dict[str, Any] | None = None,
    channel_prefix: str = "_metrics",
) -> None:
    """Emit a metric as a message.

    This is a synchronous wrapper that schedules the async publish.
    Metrics are published to {channel_prefix}.{metric_name}.

    Args:
        metric_name: Name of the metric (e.g., "broker.published", "source.rate")
        value: Metric value
        tags: Optional tags for the metric (e.g., {"component": "source", "channel": "sensors.temp"})
        channel_prefix: Channel prefix for metrics (default: "_metrics")

    Examples:
        >>> emit_metric("messages.processed", 1, tags={"channel": "sensors.temp"})
        >>> emit_metric("pipeline.latency_ms", 42.5, tags={"stage": "transformation"})

    Note:
        If no broker is set (via set_metrics_broker), this is a no-op.
        Metrics are published with AT_MOST_ONCE delivery guarantee.
    """
    if _metrics_broker is None:
        return

    # Create metric message
    metric_msg = Message(
        key=metric_name,
        timestamp=datetime.now(UTC),
        value=value,
        tags=tags or {},
    )

    # Schedule async publish
    channel = f"{channel_prefix}.{metric_name}"
    asyncio.create_task(
        _metrics_broker.publish(
            channel,
            metric_msg,
            DeliveryGuarantee.AT_MOST_ONCE,
        )
    )


async def emit_metric_async(
    metric_name: str,
    value: float | int,
    *,
    tags: dict[str, Any] | None = None,
    channel_prefix: str = "_metrics",
    broker: Broker | None = None,
) -> None:
    """Emit a metric as a message (async version).

    Use this when you're already in an async context and want to await the publish.

    Args:
        metric_name: Name of the metric
        value: Metric value
        tags: Optional tags for the metric
        channel_prefix: Channel prefix for metrics (default: "_metrics")
        broker: Optional broker to use (defaults to global metrics broker)

    Examples:
        >>> await emit_metric_async("messages.processed", 1, tags={"channel": "sensors.temp"})
    """
    target_broker = broker or _metrics_broker
    if target_broker is None:
        return

    # Create metric message
    metric_msg = Message(
        key=metric_name,
        timestamp=datetime.now(UTC),
        value=value,
        tags=tags or {},
    )

    # Publish
    channel = f"{channel_prefix}.{metric_name}"
    await target_broker.publish(
        channel,
        metric_msg,
        DeliveryGuarantee.AT_MOST_ONCE,
    )


class MetricsCollector:
    """Helper class for collecting and emitting metrics.

    This is useful when you want to batch multiple metrics or
    compute derived metrics before emission.

    Examples:
        >>> collector = MetricsCollector("source", tags={"source_id": "src-1"})
        >>> collector.increment("messages_produced")
        >>> collector.set("queue_size", 42)
        >>> await collector.flush()
    """

    def __init__(
        self,
        namespace: str,
        *,
        tags: dict[str, Any] | None = None,
        broker: Broker | None = None,
    ) -> None:
        """Initialize metrics collector.

        Args:
            namespace: Namespace for metrics (e.g., "source", "broker", "transform")
            tags: Default tags to apply to all metrics
            broker: Optional broker to use (defaults to global metrics broker)
        """
        self.namespace = namespace
        self.default_tags = tags or {}
        self.broker = broker or _metrics_broker
        self._counters: dict[str, int | float] = {}
        self._gauges: dict[str, int | float] = {}

    def increment(self, metric_name: str, value: int | float = 1) -> None:
        """Increment a counter metric.

        Args:
            metric_name: Name of the counter
            value: Amount to increment by (default: 1)
        """
        self._counters[metric_name] = self._counters.get(metric_name, 0) + value

    def set(self, metric_name: str, value: int | float) -> None:
        """Set a gauge metric.

        Args:
            metric_name: Name of the gauge
            value: Value to set
        """
        self._gauges[metric_name] = value

    async def flush(self, *, extra_tags: dict[str, Any] | None = None) -> None:
        """Emit all collected metrics and reset.

        Args:
            extra_tags: Additional tags to apply to this flush
        """
        if self.broker is None:
            self._counters.clear()
            self._gauges.clear()
            return

        # Merge tags
        tags = {**self.default_tags, **(extra_tags or {})}

        # Emit counters
        for metric_name, value in self._counters.items():
            full_name = f"{self.namespace}.{metric_name}"
            await emit_metric_async(full_name, value, tags=tags, broker=self.broker)

        # Emit gauges
        for metric_name, value in self._gauges.items():
            full_name = f"{self.namespace}.{metric_name}"
            await emit_metric_async(full_name, value, tags=tags, broker=self.broker)

        # Reset
        self._counters.clear()
        self._gauges.clear()

    def reset(self) -> None:
        """Reset all metrics without emitting."""
        self._counters.clear()
        self._gauges.clear()
