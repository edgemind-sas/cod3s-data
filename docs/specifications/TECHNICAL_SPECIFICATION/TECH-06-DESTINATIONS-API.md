# Destinations Implementation and API

**Document**: TECH-06-DESTINATIONS-API.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [06-DESTINATIONS](../FUNCTIONAL_SPECIFICATION/06-DESTINATIONS.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-05](TECH-05-TRANSFORMATIONS-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-07 →](TECH-07-CONFIGURATION-API.md) |

---

## Table of Contents

1. [Destination Base Class](#destination-base-class)
2. [Buffer Management](#buffer-management)
3. [Retry Logic](#retry-logic)
4. [Built-in Destinations](#built-in-destinations)
5. [Custom Destination Development](#custom-destination-development)

---

## Destination Base Class

### Abstract Destination Interface

```python
from abc import ABC, abstractmethod
import asyncio

class RetryStrategy(Enum):
    """Retry backoff strategy"""
    EXPONENTIAL = "exponential"  # 1s, 2s, 4s, 8s, ...
    FIXED = "fixed"              # 1s, 1s, 1s, ...

class Destination(ABC):
    """
    Base class for all destinations.

    Destinations are passive consumers that:
    - Subscribe to channel patterns
    - Buffer incoming messages
    - Write to external systems
    - Handle retries and errors
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        retry_attempts: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        dlq_channel: str | None = None,
        batch_size: int = 1
    ):
        """
        Initialize destination.

        Args:
            broker: Message broker
            channel_pattern: Channel pattern to subscribe (supports wildcards)
            buffer_size: Maximum messages to buffer
            overflow_strategy: How to handle buffer overflow
            retry_attempts: Number of retry attempts on write failure
            retry_strategy: Backoff strategy for retries
            dlq_channel: Dead letter queue channel (for failed messages)
            batch_size: Number of messages to batch before writing
        """
        self.broker = broker
        self.channel_pattern = channel_pattern
        self.batch_size = batch_size
        self.retry_attempts = retry_attempts
        self.retry_strategy = retry_strategy
        self.dlq_channel = dlq_channel

        # Buffer (see TECH-02-DATA-STRUCTURES)
        self.buffer = DestinationBuffer(buffer_size, overflow_strategy)

        self._running = False
        self._subscription_handle = None
        self._writer_task = None

        self.logger = structlog.get_logger().bind(
            destination=self.__class__.__name__,
            pattern=channel_pattern
        )

    async def start(self):
        """
        Start destination.

        1. Subscribe to channel pattern
        2. Start writer loop
        """
        self._running = True

        # Subscribe to broker
        self._subscription_handle = self.broker.subscribe(
            self.channel_pattern,
            self._enqueue_message
        )

        # Start writer task
        self._writer_task = asyncio.create_task(self._writer_loop())

        self.logger.info("destination_started")

    async def stop(self):
        """
        Stop destination (graceful shutdown).

        1. Unsubscribe from broker
        2. Flush remaining messages
        3. Close resources
        """
        self.logger.info("destination_stopping")
        self._running = False

        # Unsubscribe
        if self._subscription_handle:
            self.broker.unsubscribe(self._subscription_handle)

        # Wait for writer to finish
        if self._writer_task:
            await self._writer_task

        # Flush any remaining messages
        await self._flush_buffer()

        # Close resources
        await self.close()

        self.logger.info("destination_stopped")

    async def _enqueue_message(self, message: Message):
        """
        Callback for broker subscription.

        Adds message to buffer.
        """
        await self.buffer.put(message)

    async def _writer_loop(self):
        """
        Main writer loop.

        Retrieves messages from buffer and writes them.
        """
        batch = []

        while self._running or not self.buffer.is_empty():
            try:
                # Get message from buffer (with timeout)
                try:
                    message = await asyncio.wait_for(
                        self.buffer.get(),
                        timeout=0.1  # 100ms timeout for batching
                    )
                    batch.append(message)

                except asyncio.TimeoutError:
                    # Timeout: flush partial batch
                    if batch:
                        await self._write_batch_with_retry(batch)
                        batch = []
                    continue

                # Write when batch is full
                if len(batch) >= self.batch_size:
                    await self._write_batch_with_retry(batch)
                    batch = []

            except Exception as e:
                self.logger.error("writer_loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(1)  # Back off

        # Final flush
        if batch:
            await self._write_batch_with_retry(batch)

    async def _flush_buffer(self):
        """Flush remaining messages in buffer"""
        batch = []
        while not self.buffer.is_empty():
            try:
                message = await asyncio.wait_for(self.buffer.get(), timeout=0.1)
                batch.append(message)

                if len(batch) >= self.batch_size:
                    await self._write_batch_with_retry(batch)
                    batch = []

            except asyncio.TimeoutError:
                break

        if batch:
            await self._write_batch_with_retry(batch)

    async def _write_batch_with_retry(self, batch: list[Message]):
        """Write batch with retry logic"""
        for message in batch:
            success = await self._write_with_retry(message)

            if not success and self.dlq_channel:
                # Send to DLQ
                try:
                    await self.broker.publish(self.dlq_channel, message)
                except Exception as e:
                    self.logger.error("dlq_publish_failed", error=str(e))

    async def _write_with_retry(self, message: Message) -> bool:
        """
        Write message with retry logic.

        Returns:
            True if successful, False if all retries exhausted
        """
        for attempt in range(self.retry_attempts):
            try:
                await self.write(message)
                return True

            except Exception as e:
                self.logger.error("write_failed",
                                 attempt=attempt + 1,
                                 max_attempts=self.retry_attempts,
                                 error=str(e))

                # Last attempt failed
                if attempt >= self.retry_attempts - 1:
                    return False

                # Backoff before retry
                backoff = self._calculate_backoff(attempt)
                await asyncio.sleep(backoff)

        return False

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate retry backoff delay"""
        if self.retry_strategy == RetryStrategy.EXPONENTIAL:
            return min(2 ** attempt, 60)  # Max 60s
        else:  # FIXED
            return 1.0

    @abstractmethod
    async def write(self, message: Message):
        """
        Write single message (implemented by subclass).

        Args:
            message: Message to write

        Raises:
            Exception: On write failure (triggers retry)
        """
        ...

    async def close(self):
        """Close resources (optional, override in subclass)"""
        pass
```

---

## Buffer Management

See [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md#destination-buffers) for DestinationBuffer implementation.

### Overflow Strategies

```python
# DROP_OLDEST: Remove oldest, add new
dest = ConsoleDestination(
    broker, "alerts.**",
    buffer_size=100,
    overflow_strategy=OverflowStrategy.DROP_OLDEST
)

# DROP_NEWEST: Discard new message
dest = FileDestination(
    broker, "logs.**",
    buffer_size=1000,
    overflow_strategy=OverflowStrategy.DROP_NEWEST
)

# BLOCK: Wait for space (backpressure)
dest = DatabaseDestination(
    broker, "critical.**",
    buffer_size=500,
    overflow_strategy=OverflowStrategy.BLOCK
)
```

---

## Retry Logic

### Exponential Backoff

```python
# Exponential: 1s, 2s, 4s, 8s, 16s, ...
dest = FileDestination(
    broker, "data.**",
    retry_attempts=5,
    retry_strategy=RetryStrategy.EXPONENTIAL
)
```

### Fixed Backoff

```python
# Fixed: 1s, 1s, 1s, ...
dest = ConsoleDestination(
    broker, "debug.**",
    retry_attempts=3,
    retry_strategy=RetryStrategy.FIXED
)
```

### Dead Letter Queue

```python
# Send failed messages to DLQ
dest = DatabaseDestination(
    broker, "sensor.**",
    retry_attempts=3,
    dlq_channel="_dlq.database_failures"
)

# Monitor DLQ
async def handle_dlq(msg: Message):
    logger.warning("message_failed", message_id=str(msg.id))

broker.subscribe("_dlq.**", handle_dlq)
```

---

## Built-in Destinations

### ConsoleDestination

```python
class ConsoleDestination(Destination):
    """
    Print messages to stdout (debugging).

    Args:
        format: Output format ("json" or "text")
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        format: str = "json"
    ):
        super().__init__(broker, channel_pattern)
        self.format = format

    async def write(self, message: Message):
        """Print to stdout"""
        if self.format == "json":
            print(message.to_json())
        else:
            print(f"[{message.timestamp.isoformat()}] "
                  f"{message.key}={message.value} {message.tags}")
```

### FileDestination

```python
class FileDestination(Destination):
    """
    Append messages to file (JSON lines format).
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        file_path: str,
        **kwargs
    ):
        super().__init__(broker, channel_pattern, **kwargs)
        self.file_path = file_path
        self._file = None

    async def start(self):
        """Open file for writing"""
        import aiofiles
        self._file = await aiofiles.open(self.file_path, 'a')
        await super().start()

    async def write(self, message: Message):
        """Append JSON line to file"""
        await self._file.write(message.to_json() + '\n')
        await self._file.flush()

    async def close(self):
        """Close file"""
        if self._file:
            await self._file.close()
```

### InMemoryDestination / CollectDestination

```python
class CollectDestination(Destination):
    """
    Collect messages in memory (testing).

    Useful for assertions in tests.
    """

    def __init__(self, broker: Broker, channel_pattern: str):
        super().__init__(broker, channel_pattern)
        self.messages: list[Message] = []

    async def write(self, message: Message):
        """Store in memory"""
        self.messages.append(message)

    def get_all(self) -> list[Message]:
        """Retrieve all collected messages"""
        return self.messages.copy()

    def clear(self):
        """Clear collected messages"""
        self.messages.clear()

    def assert_count(self, expected: int):
        """Assert message count"""
        assert len(self.messages) == expected, \
            f"Expected {expected} messages, got {len(self.messages)}"

    def assert_values(self, expected: list):
        """Assert message values"""
        actual = [m.value for m in self.messages]
        assert actual == expected, f"Expected {expected}, got {actual}"
```

---

## Custom Destination Development

### Example: Database Destination

```python
class PostgreSQLDestination(Destination):
    """
    Write messages to PostgreSQL database.

    Example custom destination.
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        connection_string: str,
        table_name: str,
        **kwargs
    ):
        super().__init__(broker, channel_pattern, batch_size=100, **kwargs)
        self.connection_string = connection_string
        self.table_name = table_name
        self._pool = None

    async def start(self):
        """Create connection pool"""
        import asyncpg

        self._pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=10
        )

        await super().start()

    async def write(self, message: Message):
        """Insert message into database"""
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self.table_name}
                (id, key, timestamp, value, tags)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(message.id),
                message.key,
                message.timestamp,
                json.dumps(message.value),
                json.dumps(message.tags)
            )

    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
```

### Example: HTTP POST Destination

```python
class HTTPDestination(Destination):
    """
    POST messages to HTTP endpoint.
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs
    ):
        super().__init__(broker, channel_pattern, **kwargs)
        self.url = url
        self.headers = headers or {}
        self._session = None

    async def start(self):
        """Create HTTP session"""
        import aiohttp
        self._session = aiohttp.ClientSession()
        await super().start()

    async def write(self, message: Message):
        """POST message to endpoint"""
        async with self._session.post(
            self.url,
            json=message.to_dict(),
            headers=self.headers
        ) as response:
            response.raise_for_status()  # Raise on 4xx/5xx

    async def close(self):
        """Close HTTP session"""
        if self._session:
            await self._session.close()
```

---

## References

- **Functional Spec**: [06-DESTINATIONS](../FUNCTIONAL_SPECIFICATION/06-DESTINATIONS.md)
- **QA Decisions**: [Q5.1-Q5.4](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) - DestinationBuffer
  - [TECH-03-BROKER-API](TECH-03-BROKER-API.md) - Subscribing to channels

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-05](TECH-05-TRANSFORMATIONS-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-07 →](TECH-07-CONFIGURATION-API.md) |
