# Sources Implementation and API

**Document**: TECH-04-SOURCES-API.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [04-SOURCES](../FUNCTIONAL_SPECIFICATION/04-SOURCES.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-03](TECH-03-BROKER-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-05 →](TECH-05-TRANSFORMATIONS-API.md) |

---

## Table of Contents

1. [Source Base Class](#source-base-class)
2. [Batch Modes](#batch-modes)
3. [Built-in Sources](#built-in-sources)
4. [Custom Source Development](#custom-source-development)
5. [Performance Considerations](#performance-considerations)

---

## Source Base Class

### Abstract Source Interface

```python
from abc import ABC, abstractmethod
from enum import Enum
from typing import AsyncIterator
import asyncio

class BatchMode(Enum):
    """Source batch mode"""
    BATCH = "batch"          # Finite dataset, process once
    REALTIME = "realtime"    # Continuous operation
    TRANSPOSE = "transpose"  # Timestamp-based replay

class Source(ABC):
    """
    Base class for all data sources.

    Responsibilities:
    - Acquire data from external systems
    - Convert to COD3S messages
    - Publish to broker via channel
    - Handle lifecycle (start, stop)

    Subclasses implement produce() to generate messages.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        batch_mode: BatchMode = BatchMode.BATCH,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE
    ):
        """
        Initialize source.

        Args:
            broker: Message broker for publishing
            channel: Target channel for messages
            batch_mode: Operating mode (BATCH, REALTIME, TRANSPOSE)
            delivery_guarantee: Message delivery guarantee
        """
        self.broker = broker
        self.channel = channel
        self.batch_mode = batch_mode
        self.delivery_guarantee = delivery_guarantee

        self._running = False
        self._paused = False
        self._message_count = 0

        self.logger = structlog.get_logger().bind(
            source=self.__class__.__name__,
            channel=channel
        )

    async def start(self):
        """
        Start producing messages.

        Calls produce() and publishes each message to broker.
        """
        self._running = True
        self.logger.info("source_starting", batch_mode=self.batch_mode.value)

        try:
            async for message in self.produce():
                if not self._running:
                    break

                # Handle pause
                while self._paused and self._running:
                    await asyncio.sleep(0.1)

                if not self._running:
                    break

                # Publish message
                await self._publish_message(message)
                self._message_count += 1

        except Exception as e:
            self.logger.error("source_error", error=str(e), exc_info=True)
            raise

        finally:
            self.logger.info("source_stopped", total_messages=self._message_count)

    async def stop(self):
        """Stop producing messages"""
        self.logger.info("source_stopping")
        self._running = False
        await self._on_stop()

    async def pause(self):
        """Pause message production (REALTIME mode only)"""
        if self.batch_mode != BatchMode.REALTIME:
            self.logger.warning("pause_not_supported",
                               batch_mode=self.batch_mode.value)
            return

        self._paused = True
        self.logger.info("source_paused")

    async def resume(self):
        """Resume message production"""
        self._paused = False
        self.logger.info("source_resumed")

    async def _publish_message(self, message: Message):
        """
        Publish message to broker.

        Handles delivery guarantees.
        """
        await self.broker.publish(
            self.channel,
            message,
            self.delivery_guarantee
        )

        # Emit progress metric
        if self._message_count % 100 == 0:
            await self.broker.publish(
                f"_metrics.source.{self.__class__.__name__}.produced",
                Message(
                    key="messages_produced",
                    timestamp=datetime.now(timezone.utc),
                    value=self._message_count,
                    tags={"channel": self.channel}
                )
            )

    @abstractmethod
    async def produce(self) -> AsyncIterator[Message]:
        """
        Generate messages (implemented by subclass).

        Yields:
            Message instances to publish

        Examples:
            >>> async def produce(self):
            ...     for i in range(10):
            ...         yield Message(
            ...             key="value",
            ...             timestamp=datetime.now(timezone.utc),
            ...             value=i,
            ...             tags={}
            ...         )
        """
        ...

    async def _on_stop(self):
        """Subclass-specific cleanup (optional)"""
        pass

    @property
    def is_running(self) -> bool:
        """Check if source is running"""
        return self._running

    @property
    def message_count(self) -> int:
        """Total messages produced"""
        return self._message_count
```

---

## Batch Modes

### BATCH Mode Implementation

```python
class CSVSource(Source):
    """
    Read CSV file (BATCH mode).

    Reads entire file, publishes all messages, then stops.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str,
        key_column: str = "key",
        timestamp_column: str = "timestamp",
        value_column: str = "value",
        tag_columns: list[str] | None = None
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.BATCH)
        self.file_path = file_path
        self.key_column = key_column
        self.timestamp_column = timestamp_column
        self.value_column = value_column
        self.tag_columns = tag_columns or []

    async def produce(self) -> AsyncIterator[Message]:
        """Read CSV and yield messages"""
        import polars as pl

        # Read CSV (use polars for performance)
        df = pl.read_csv(self.file_path)

        for row in df.iter_rows(named=True):
            # Extract fields
            key = row[self.key_column]
            timestamp_str = row[self.timestamp_column]
            value = row[self.value_column]

            # Parse timestamp
            timestamp = datetime.fromisoformat(timestamp_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Extract tags
            tags = {
                col: str(row[col])
                for col in self.tag_columns
                if col in row
            }

            yield Message(
                key=key,
                timestamp=timestamp,
                value=value,
                tags=tags
            )
```

### REALTIME Mode Implementation

```python
class RandomSource(Source):
    """
    Generate random values (REALTIME mode).

    Runs continuously until stopped.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        rate: float = 1.0,  # Messages per second
        min_value: float = 0.0,
        max_value: float = 100.0
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.REALTIME)
        self.rate = rate
        self.min_value = min_value
        self.max_value = max_value

    async def produce(self) -> AsyncIterator[Message]:
        """Generate random values at specified rate"""
        import random

        interval = 1.0 / self.rate

        while True:
            value = random.uniform(self.min_value, self.max_value)

            yield Message(
                key="random_value",
                timestamp=datetime.now(timezone.utc),
                value=value,
                tags={}
            )

            await asyncio.sleep(interval)
```

### TRANSPOSE Mode Implementation

```python
class TransposeCSVSource(Source):
    """
    Replay CSV with timestamp-based delays (TRANSPOSE mode).

    Preserves original timestamps but adjusts replay speed.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str,
        time_scale: float = 1.0,  # 1.0 = real-time, 10.0 = 10x faster
        **csv_args
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.TRANSPOSE)
        self.file_path = file_path
        self.time_scale = time_scale
        self.csv_args = csv_args

    async def produce(self) -> AsyncIterator[Message]:
        """Read CSV and replay with timing"""
        import polars as pl

        df = pl.read_csv(self.file_path)

        prev_timestamp = None

        for row in df.iter_rows(named=True):
            timestamp = datetime.fromisoformat(row["timestamp"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Calculate delay from previous message
            if prev_timestamp is not None:
                delay = (timestamp - prev_timestamp).total_seconds()
                scaled_delay = delay / self.time_scale
                if scaled_delay > 0:
                    await asyncio.sleep(scaled_delay)

            prev_timestamp = timestamp

            yield Message(
                key=row["key"],
                timestamp=timestamp,  # Original timestamp
                value=row["value"],
                tags={}
            )
```

---

## Built-in Sources

### SequenceSource

```python
class SequenceSource(Source):
    """
    Generate sequential integers (testing).

    Args:
        start: Starting value (inclusive)
        end: Ending value (exclusive)
        rate: Messages per second (0 = unlimited)
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        start: int = 0,
        end: int = 100,
        rate: float = 10.0
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.BATCH)
        self.start = start
        self.end = end
        self.rate = rate

    async def produce(self) -> AsyncIterator[Message]:
        interval = 1.0 / self.rate if self.rate > 0 else 0

        for i in range(self.start, self.end):
            yield Message(
                key="sequence",
                timestamp=datetime.now(timezone.utc),
                value=i,
                tags={}
            )

            if interval > 0:
                await asyncio.sleep(interval)
```

### FileSource

```python
class FileSource(Source):
    """
    Read text file line by line (BATCH mode).

    Each line becomes a message.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str,
        encoding: str = "utf-8"
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.BATCH)
        self.file_path = file_path
        self.encoding = encoding

    async def produce(self) -> AsyncIterator[Message]:
        import aiofiles

        async with aiofiles.open(self.file_path, 'r', encoding=self.encoding) as f:
            line_number = 0

            async for line in f:
                line_number += 1

                yield Message(
                    key="line",
                    timestamp=datetime.now(timezone.utc),
                    value=line.strip(),
                    tags={"line_number": str(line_number)}
                )
```

---

## Custom Source Development

### Example: HTTP Polling Source

```python
class HTTPPollingSource(Source):
    """
    Poll HTTP endpoint (REALTIME mode).

    Example custom source implementation.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        url: str,
        interval: float = 60.0,  # Poll interval in seconds
        headers: dict[str, str] | None = None
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.REALTIME)
        self.url = url
        self.interval = interval
        self.headers = headers or {}

    async def produce(self) -> AsyncIterator[Message]:
        """Poll HTTP endpoint at regular intervals"""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(self.url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()

                            yield Message(
                                key="http_data",
                                timestamp=datetime.now(timezone.utc),
                                value=data,
                                tags={"url": self.url, "status": str(response.status)}
                            )

                        else:
                            self.logger.warning("http_error",
                                               status=response.status,
                                               url=self.url)

                except Exception as e:
                    self.logger.error("http_request_failed",
                                     error=str(e),
                                     url=self.url)

                await asyncio.sleep(self.interval)
```

### Example: Sensor Simulator

```python
class SensorSimulator(Source):
    """
    Simulate sensor readings with noise.

    Useful for testing and demos.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        base_value: float = 100.0,
        noise_amplitude: float = 5.0,
        rate: float = 1.0,
        sensor_id: str = "SIM001"
    ):
        super().__init__(broker, channel, batch_mode=BatchMode.REALTIME)
        self.base_value = base_value
        self.noise_amplitude = noise_amplitude
        self.rate = rate
        self.sensor_id = sensor_id

    async def produce(self) -> AsyncIterator[Message]:
        import random
        import math

        interval = 1.0 / self.rate
        t = 0

        while True:
            # Sine wave + random noise
            noise = random.uniform(-self.noise_amplitude, self.noise_amplitude)
            value = self.base_value + 10 * math.sin(t / 10) + noise

            yield Message(
                key="sensor_reading",
                timestamp=datetime.now(timezone.utc),
                value=round(value, 2),
                tags={"sensor_id": self.sensor_id, "type": "simulated"}
            )

            await asyncio.sleep(interval)
            t += interval
```

---

## Performance Considerations

### Throughput Optimization

```python
class BatchedCSVSource(Source):
    """
    CSV source with batched publishing for higher throughput.
    """

    def __init__(self, broker, channel, file_path, batch_size=100):
        super().__init__(broker, channel)
        self.file_path = file_path
        self.batch_size = batch_size

    async def produce(self) -> AsyncIterator[Message]:
        import polars as pl

        df = pl.read_csv(self.file_path)

        # Process in batches for better performance
        for batch_start in range(0, len(df), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(df))
            batch = df[batch_start:batch_end]

            for row in batch.iter_rows(named=True):
                yield Message(
                    key=row["key"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    value=row["value"],
                    tags={}
                )

            # Yield control periodically
            await asyncio.sleep(0)  # Let event loop process other tasks
```

### Memory-Efficient Streaming

```python
class StreamingFileSource(Source):
    """
    Stream large files without loading entire file into memory.
    """

    async def produce(self) -> AsyncIterator[Message]:
        import aiofiles

        # Stream file line by line (memory-efficient)
        async with aiofiles.open(self.file_path, 'r') as f:
            async for line in f:
                # Parse line to message
                data = json.loads(line)

                yield Message(
                    key=data["key"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    value=data["value"],
                    tags=data.get("tags", {})
                )
```

### Performance Targets

| Source Type | Throughput Target | Typical |
|-------------|------------------|---------|
| **CSVSource** (polars) | > 10,000 rows/sec | 50,000 rows/sec |
| **FileSource** | > 5,000 lines/sec | 20,000 lines/sec |
| **RandomSource** | > 1,000 msgs/sec | 10,000 msgs/sec |
| **HTTPPollingSource** | Depends on endpoint | 10 requests/sec |

---

## References

- **Functional Spec**: [04-SOURCES](../FUNCTIONAL_SPECIFICATION/04-SOURCES.md)
- **QA Decisions**: [Q3.1-Q3.5](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) - Message class
  - [TECH-03-BROKER-API](TECH-03-BROKER-API.md) - Publishing messages

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-03](TECH-03-BROKER-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-05 →](TECH-05-TRANSFORMATIONS-API.md) |
