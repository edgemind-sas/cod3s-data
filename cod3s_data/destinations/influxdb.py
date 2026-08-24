"""InfluxDB destination for COD3S Data Framework."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog

from cod3s_data.broker.base import Broker
from cod3s_data.core.buffers import OverflowStrategy
from cod3s_data.core.message import Message
from cod3s_data.destinations.base import Destination, RetryStrategy

_logger = structlog.get_logger()


def _flatten_fields(
    value: dict[str, Any], prefix: str = ""
) -> list[tuple[str, Any]]:
    """Flatten a (possibly nested) dict into [(key, scalar)] pairs.

    InfluxDB Point fields accept only scalars (int/float/bool/str). Nested
    dicts (e.g. alarm messages with ``original_value``) get flattened with
    dot-separated keys: ``{"original_value": {"actual": 1.0}}`` becomes
    ``[("original_value.actual", 1.0)]``.
    """
    out: list[tuple[str, Any]] = []
    for k, v in value.items():
        full_key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.extend(_flatten_fields(v, prefix=f"{full_key}."))
        else:
            out.append((full_key, v))
    return out


class InfluxDBDestination(Destination):
    """Write messages to InfluxDB 2.x as time-series data points.

    Each message is converted to an InfluxDB Point:
    - ``message.key`` becomes the measurement name (overridable via ``measurement``)
    - ``message.timestamp`` becomes the point timestamp
    - ``message.tags`` become InfluxDB tags (merged with ``extra_tags``)
    - ``message.value`` becomes one or more fields:
      - if dict: each key/value pair becomes a field
      - otherwise: stored as a single field named ``"value"``

    Requires the ``influxdb-client[async]`` package. Install with::

        pip install 'cod3s-data[influxdb]'

    Args:
        broker: Message broker instance.
        channel_pattern: Channel subscription pattern.
        url: InfluxDB server URL.
        token: Authentication token.
        org: InfluxDB organization.
        bucket: Target bucket name.
        measurement: Override measurement name (defaults to ``message.key``).
        extra_tags: Additional tags added to every point.
        buffer_size: Internal buffer capacity.
        overflow_strategy: What to do when buffer is full.
        retry_attempts: Number of write retry attempts.
        retry_strategy: Backoff strategy for retries.
        dlq_channel: Dead-letter queue channel for failed messages.
        batch_size: Number of messages per write batch.

    Example::

        dest = InfluxDBDestination(
            broker, "sensors.**",
            url="http://localhost:8086",
            token="my-token",
            org="cod3s",
            bucket="sensor_data",
            extra_tags={"printer": "gemini3d"},
        )
        await dest.start()
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        # --- InfluxDB connection ---
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "",
        bucket: str = "",
        # --- Mapping ---
        measurement: str | None = None,
        extra_tags: dict[str, str] | None = None,
        # --- Base class ---
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        retry_attempts: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        dlq_channel: str | None = None,
        batch_size: int = 100,
    ) -> None:
        try:
            from influxdb_client.client.influxdb_client_async import (
                InfluxDBClientAsync,  # noqa: F401
            )
        except ImportError:
            raise ImportError(
                "influxdb-client[async] is required for InfluxDBDestination. "
                "Install it with: pip install 'cod3s-data[influxdb]'"
            ) from None

        super().__init__(
            broker,
            channel_pattern,
            buffer_size,
            overflow_strategy,
            retry_attempts,
            retry_strategy,
            dlq_channel,
            batch_size,
        )
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.measurement = measurement
        self.extra_tags = extra_tags or {}
        self._client: Any = None
        self._write_api: Any = None

    def _message_to_point(self, message: Message) -> Any:
        """Convert a Message to an InfluxDB Point.

        Args:
            message: The message to convert.

        Returns:
            An ``influxdb_client.Point`` instance.
        """
        from influxdb_client import Point  # type: ignore[attr-defined]

        measurement_name = self.measurement or message.key
        point = Point(measurement_name)  # type: ignore[no-untyped-call]

        # Tags: message tags + extra_tags (extra_tags override message tags)
        all_tags = {**message.tags, **self.extra_tags}
        for tag_key, tag_value in all_tags.items():
            point.tag(tag_key, tag_value)  # type: ignore[no-untyped-call]

        # Fields: from message.value
        # InfluxDB fields only accept scalars, so nested dicts are flattened
        # with dot notation (e.g. {"original_value": {"actual": 1}} →
        # field "original_value.actual" = 1). Without this, alarm messages
        # whose value is a dict containing a sub-dict would fail to write.
        if isinstance(message.value, dict):
            for field_key, field_value in _flatten_fields(message.value):
                point.field(field_key, field_value)  # type: ignore[no-untyped-call]
        else:
            point.field("value", message.value)  # type: ignore[no-untyped-call]

        # Timestamp
        point.time(message.timestamp)  # type: ignore[no-untyped-call]

        return point

    async def _ensure_client(self) -> None:
        """Lazily initialize the async InfluxDB client."""
        from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

        self._client = InfluxDBClientAsync(url=self.url, token=self.token, org=self.org)
        self._write_api = self._client.write_api()

    async def write(self, message: Message) -> None:
        """Write a single message to InfluxDB.

        The client is lazily initialized on the first call.

        Args:
            message: The message to write.
        """
        if self._client is None:
            await self._ensure_client()
        point = self._message_to_point(message)
        await self._write_api.write(bucket=self.bucket, record=point)

    async def _write_batch_with_retry(self, batch: list[Message]) -> None:
        """Write a whole batch of messages in a single InfluxDB HTTP call.

        Overrides the per-message loop in :class:`Destination` so the writer
        keeps up with high-throughput streams (the per-message default does
        N sequential HTTP requests per batch and quickly becomes the
        bottleneck under bursty loads).
        """
        if not batch:
            return
        if self._client is None:
            await self._ensure_client()
        points = [self._message_to_point(msg) for msg in batch]
        for attempt in range(self.retry_attempts):
            try:
                await self._write_api.write(bucket=self.bucket, record=points)
                self._message_count += len(batch)
                return
            except Exception:
                if attempt >= self.retry_attempts - 1:
                    self._error_count += len(batch)
                    if self.dlq_channel:
                        for msg in batch:
                            with contextlib.suppress(Exception):
                                await self.broker.publish(self.dlq_channel, msg)
                    return
                await asyncio.sleep(self._calculate_backoff(attempt))

    async def close(self) -> None:
        """Close the InfluxDB client connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._write_api = None
