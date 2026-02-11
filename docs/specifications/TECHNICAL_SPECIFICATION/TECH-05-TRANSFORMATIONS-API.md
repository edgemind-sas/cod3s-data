# Transformations Implementation and API

**Document**: TECH-05-TRANSFORMATIONS-API.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [05-TRANSFORMATIONS](../FUNCTIONAL_SPECIFICATION/05-TRANSFORMATIONS.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-04](TECH-04-SOURCES-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-06 →](TECH-06-DESTINATIONS-API.md) |

---

## Table of Contents

1. [Transformation Base Classes](#transformation-base-classes)
2. [Stateless Transformations](#stateless-transformations)
3. [Stateful Transformations](#stateful-transformations)
4. [State Helpers](#state-helpers)
5. [Built-in Transformations](#built-in-transformations)

---

## Transformation Base Classes

### Stateless Transformation (1:N)

```python
from abc import ABC, abstractmethod

class StatelessTransform(ABC):
    """
    Stateless transformation: each input → 0+ outputs.

    No state maintained between messages.
    Simple, efficient, easy to test.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str
    ):
        """
        Initialize stateless transformation.

        Args:
            broker: Message broker
            input_channel: Channel pattern to subscribe
            output_channel: Channel to publish results
        """
        self.broker = broker
        self.input_channel = input_channel
        self.output_channel = output_channel

        self._subscription_handle = None
        self.logger = structlog.get_logger().bind(
            transform=self.__class__.__name__,
            input=input_channel,
            output=output_channel
        )

    async def start(self):
        """Start transformation (subscribe to input)"""
        self._subscription_handle = self.broker.subscribe(
            self.input_channel,
            self._handle_message
        )

        self.logger.info("transform_started")

    async def stop(self):
        """Stop transformation (unsubscribe)"""
        if self._subscription_handle:
            self.broker.unsubscribe(self._subscription_handle)

        self.logger.info("transform_stopped")

    async def _handle_message(self, message: Message):
        """
        Internal message handler.

        Calls transform(), publishes results.
        """
        try:
            results = await self.transform(message)

            for result in results:
                await self.broker.publish(self.output_channel, result)

        except Exception as e:
            self.logger.error("transform_error",
                            message_id=str(message.id),
                            error=str(e),
                            exc_info=True)

    @abstractmethod
    async def transform(self, message: Message) -> list[Message]:
        """
        Transform one message into 0+ messages.

        Args:
            message: Input message

        Returns:
            List of output messages (empty list = filter out)

        Examples:
            >>> async def transform(self, msg):
            ...     # Pass through
            ...     return [msg]
            ...
            >>> async def transform(self, msg):
            ...     # Filter
            ...     if msg.value > 50:
            ...         return [msg]
            ...     return []
            ...
            >>> async def transform(self, msg):
            ...     # 1-to-many
            ...     return [msg, msg.with_value(msg.value * 2)]
        """
        ...
```

### Stateful Transformation (N:M)

```python
class StatefulTransform(ABC):
    """
    Stateful transformation: maintains state across messages.

    Use for: aggregations, joins, windows, deduplication.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: list[str],
        output_channel: str
    ):
        """
        Initialize stateful transformation.

        Args:
            broker: Message broker
            input_channels: List of channel patterns to subscribe
            output_channel: Channel to publish results
        """
        self.broker = broker
        self.input_channels = input_channels
        self.output_channel = output_channel

        self.state = {}  # Subclass manages state
        self._subscription_handles = []

        self.logger = structlog.get_logger().bind(
            transform=self.__class__.__name__,
            inputs=input_channels,
            output=output_channel
        )

    async def start(self):
        """Start transformation (subscribe to all inputs)"""
        for channel in self.input_channels:
            handle = self.broker.subscribe(channel, self._handle_message)
            self._subscription_handles.append(handle)

        self.logger.info("transform_started",
                        input_count=len(self.input_channels))

    async def stop(self):
        """Stop transformation"""
        for handle in self._subscription_handles:
            self.broker.unsubscribe(handle)

        self.logger.info("transform_stopped")

    async def _handle_message(self, message: Message):
        """
        Internal message handler.

        Updates state, calls transform(), publishes results.
        """
        try:
            # Update state (subclass-specific)
            await self.update_state(message)

            # Transform state into messages
            results = await self.transform()

            # Publish results
            for result in results:
                await self.broker.publish(self.output_channel, result)

        except Exception as e:
            self.logger.error("transform_error",
                            message_id=str(message.id),
                            error=str(e),
                            exc_info=True)

    @abstractmethod
    async def update_state(self, message: Message):
        """
        Update internal state with new message.

        Args:
            message: New message to incorporate into state
        """
        ...

    @abstractmethod
    async def transform(self) -> list[Message]:
        """
        Transform current state into output messages.

        Returns:
            List of output messages
        """
        ...
```

---

## Stateless Transformations

### Filter Transformation

```python
class FilterTransform(StatelessTransform):
    """
    Filter messages by predicate.

    Args:
        predicate: Function that returns True to keep message
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        predicate: Callable[[Message], bool]
    ):
        super().__init__(broker, input_channel, output_channel)
        self.predicate = predicate

    async def transform(self, message: Message) -> list[Message]:
        """Keep message if predicate is True"""
        if self.predicate(message):
            return [message]
        return []  # Filter out

# Usage
filter_high_temp = FilterTransform(
    broker,
    "sensors.temp",
    "sensors.temp.high",
    predicate=lambda msg: msg.value > 100
)
```

### Threshold Alert Transformation

```python
class ThresholdAlert(StatelessTransform):
    """
    Emit alert when value crosses threshold.

    Args:
        threshold: Alert threshold
        comparison: ">" or "<"
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        threshold: float,
        comparison: str = ">"
    ):
        super().__init__(broker, input_channel, output_channel)
        self.threshold = threshold
        self.comparison = comparison

    async def transform(self, message: Message) -> list[Message]:
        """Check threshold and emit alert"""
        value = float(message.value)

        triggered = (
            (self.comparison == ">" and value > self.threshold) or
            (self.comparison == "<" and value < self.threshold)
        )

        if triggered:
            alert = Message(
                key="alert",
                timestamp=message.timestamp,
                value=f"{message.key} = {value} (threshold: {self.threshold})",
                tags={
                    **message.tags,
                    "alert_type": "threshold",
                    "threshold": str(self.threshold)
                }
            )
            return [alert]

        return []

# Usage
alert = ThresholdAlert(broker, "sensors.temp", "alerts.critical", threshold=240)
```

### Unit Conversion

```python
class UnitConverter(StatelessTransform):
    """
    Convert measurement units.

    Example: Fahrenheit to Celsius
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        conversion_fn: Callable[[float], float],
        new_key: str | None = None
    ):
        super().__init__(broker, input_channel, output_channel)
        self.conversion_fn = conversion_fn
        self.new_key = new_key

    async def transform(self, message: Message) -> list[Message]:
        """Convert value"""
        converted_value = self.conversion_fn(float(message.value))

        return [Message(
            key=self.new_key or message.key,
            timestamp=message.timestamp,
            value=converted_value,
            tags=message.tags
        )]

# Usage
f_to_c = UnitConverter(
    broker,
    "sensors.temp.fahrenheit",
    "sensors.temp.celsius",
    conversion_fn=lambda f: (f - 32) * 5/9,
    new_key="temperature_celsius"
)
```

---

## Stateful Transformations

### Latest Combiner

```python
class LatestCombiner(StatefulTransform):
    """
    Combine latest values from multiple channels.

    Emits when all channels have at least one value.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: list[str],
        output_channel: str
    ):
        super().__init__(broker, input_channels, output_channel)
        self.latest = Latest()  # State helper from TECH-02

    async def update_state(self, message: Message):
        """Update latest value for channel"""
        # Determine which channel this message came from
        # (In practice, need to track in _handle_message)
        self.latest.update(message.key, message)

    async def transform(self) -> list[Message]:
        """Combine latest values if all available"""
        if self.latest.has_all([ch for ch in self.input_channels]):
            all_latest = self.latest.all()

            combined_value = {
                key: msg.value
                for key, msg in all_latest.items()
            }

            result = Message(
                key="combined",
                timestamp=datetime.now(timezone.utc),
                value=combined_value,
                tags={}
            )

            return [result]

        return []  # Not all channels have values yet
```

### Time Window Aggregator

```python
class TimeWindowAggregator(StatefulTransform):
    """
    Aggregate values over time window.

    Args:
        window_duration: Window size (e.g., timedelta(minutes=5))
        aggregation: "avg", "sum", "min", "max", "count"
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        window_duration: timedelta,
        aggregation: str = "avg"
    ):
        super().__init__(broker, [input_channel], output_channel)
        self.window = TimeWindow(window_duration)  # State helper
        self.aggregation = aggregation

    async def update_state(self, message: Message):
        """Add message to window"""
        self.window.add(message)

    async def transform(self) -> list[Message]:
        """Compute aggregation over window"""
        messages = self.window.all()

        if not messages:
            return []

        values = [float(m.value) for m in messages]

        if self.aggregation == "avg":
            result_value = sum(values) / len(values)
        elif self.aggregation == "sum":
            result_value = sum(values)
        elif self.aggregation == "min":
            result_value = min(values)
        elif self.aggregation == "max":
            result_value = max(values)
        elif self.aggregation == "count":
            result_value = len(values)
        else:
            raise ValueError(f"Unknown aggregation: {self.aggregation}")

        result = Message(
            key=f"{self.aggregation}_window",
            timestamp=datetime.now(timezone.utc),
            value=result_value,
            tags={"window_size": str(len(messages))}
        )

        return [result]
```

### Deduplicator

```python
class Deduplicator(StatefulTransform):
    """
    Remove duplicate messages within time window.

    Uses message value hash for duplicate detection.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        window_duration: timedelta = timedelta(minutes=1)
    ):
        super().__init__(broker, [input_channel], output_channel)
        self.cache = Cache(ttl=window_duration)  # State helper

    async def update_state(self, message: Message):
        """Check for duplicates"""
        # Hash message value
        import hashlib
        value_hash = hashlib.md5(
            str(message.value).encode()
        ).hexdigest()

        if not self.cache.has(value_hash):
            # Not a duplicate
            self.cache.set(value_hash, True)
            self._current_message = message
        else:
            # Duplicate
            self._current_message = None

    async def transform(self) -> list[Message]:
        """Emit non-duplicate"""
        if hasattr(self, '_current_message') and self._current_message:
            result = self._current_message
            self._current_message = None
            return [result]

        return []
```

---

## State Helpers

See [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md#state-management-structures) for full implementations:

- **Latest**: Keep latest message per channel
- **TimeWindow**: Time-based sliding window
- **CountWindow**: Count-based sliding window
- **Cache**: Key-value cache with TTL

---

## Built-in Transformations

| Transformation           | Type      | Description           | Use Case                 |
| ------------------------ | --------- | --------------------- | ------------------------ |
| **FilterTransform**      | Stateless | Filter by predicate   | Remove unwanted messages |
| **ThresholdAlert**       | Stateless | Alert on threshold    | Monitoring, alarms       |
| **UnitConverter**        | Stateless | Convert units         | Normalize measurements   |
| **LatestCombiner**       | Stateful  | Combine latest values | Multi-sensor aggregation |
| **TimeWindowAggregator** | Stateful  | Aggregate over time   | Statistics, smoothing    |
| **Deduplicator**         | Stateful  | Remove duplicates     | Data quality             |
|                          |           |                       |                          |

---

## References

- **Functional Spec**: [05-TRANSFORMATIONS](../FUNCTIONAL_SPECIFICATION/05-TRANSFORMATIONS.md)
- **QA Decisions**: [Q4.1-Q4.3](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) - State helpers
  - [TECH-03-BROKER-API](TECH-03-BROKER-API.md) - Pub/sub for transformations

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-04](TECH-04-SOURCES-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-06 →](TECH-06-DESTINATIONS-API.md) |
