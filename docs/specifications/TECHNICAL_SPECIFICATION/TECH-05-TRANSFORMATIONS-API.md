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
2. [Built-in Stateless Transformations](#built-in-stateless-transformations)
3. [Custom Stateful Transformation Examples](#custom-stateful-transformation-examples)
4. [State Helpers](#state-helpers)
5. [Built-in Transformations Summary](#built-in-transformations-summary)

---

## Transformation Base Classes

### Base Transformation (ABC)

```python
from abc import ABC, abstractmethod

class Transformation(ABC):
    """
    Base class for all transformations.

    Each input message produces 0 or more output messages.
    Subclasses implement transform() to define the transformation logic.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str
    ):
        """
        Initialize transformation.

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

            if results is None:
                return  # Message filtered out

            if isinstance(results, Message):
                results = [results]

            for result in results:
                await self.broker.publish(self.output_channel, result)

        except Exception as e:
            self.logger.error("transform_error",
                            message_id=str(message.id),
                            error=str(e),
                            exc_info=True)

    @abstractmethod
    async def transform(self, message: Message) -> Message | list[Message] | None:
        """
        Transform one message into 0+ messages.

        Args:
            message: Input message

        Returns:
            A single Message, a list of Messages, or None to filter out.

        Examples:
            >>> async def transform(self, msg):
            ...     # Pass through
            ...     return msg
            ...
            >>> async def transform(self, msg):
            ...     # Filter
            ...     if msg.value > 50:
            ...         return msg
            ...     return None
            ...
            >>> async def transform(self, msg):
            ...     # 1-to-many
            ...     return [msg, msg.with_value(msg.value * 2)]
        """
        ...
```

### Stateful Transformation

```python
class StatefulTransform(Transformation):
    """
    Stateful transformation: maintains state across messages.

    Extends Transformation with a shared state dict and an asyncio lock
    for thread safety. Subclasses implement transform_with_state() instead
    of transform().

    Use for: aggregations, joins, windows, deduplication.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str
    ):
        """
        Initialize stateful transformation.

        Args:
            broker: Message broker
            input_channel: Channel pattern to subscribe
            output_channel: Channel to publish results
        """
        super().__init__(broker, input_channel, output_channel)
        self.state: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def transform(self, message: Message) -> Message | list[Message] | None:
        """
        Delegates to transform_with_state() under lock.
        """
        async with self._lock:
            return await self.transform_with_state(message, self.state)

    @abstractmethod
    async def transform_with_state(
        self, message: Message, state: dict
    ) -> Message | list[Message] | None:
        """
        Transform a message with access to shared state.

        Args:
            message: Input message
            state: Mutable state dict shared across invocations

        Returns:
            A single Message, a list of Messages, or None to filter out.
        """
        ...
```

---

## Built-in Stateless Transformations

### Filter Transformation

```python
class FilterTransform(Transformation):
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

    async def transform(self, message: Message) -> Message | None:
        """Keep message if predicate is True"""
        if self.predicate(message):
            return message
        return None  # Filter out

# Usage
filter_high_temp = FilterTransform(
    broker,
    "sensors.temp",
    "sensors.temp.high",
    predicate=lambda msg: msg.value > 100
)
```

### Map Transformation

```python
class MapTransform(Transformation):
    """
    Apply a mapping function to each message.

    Args:
        map_fn: Function that transforms a message into a new message
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        map_fn: Callable[[Message], Message]
    ):
        super().__init__(broker, input_channel, output_channel)
        self.map_fn = map_fn

    async def transform(self, message: Message) -> Message:
        """Apply mapping function"""
        return self.map_fn(message)

# Usage
double_value = MapTransform(
    broker,
    "sensors.temp",
    "sensors.temp.doubled",
    map_fn=lambda msg: Message(
        key=msg.key,
        timestamp=msg.timestamp,
        value=msg.value * 2,
        tags=msg.tags
    )
)
```

### Aggregate Transformation

```python
class AggregateTransform(StatefulTransform):
    """
    Aggregate values over a window using shared state.

    Args:
        aggregation: Aggregation function ("avg", "sum", "min", "max", "count")
        window_size: Number of messages to aggregate over
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        aggregation: str = "avg",
        window_size: int = 10
    ):
        super().__init__(broker, input_channel, output_channel)
        self.aggregation = aggregation
        self.window_size = window_size

    async def transform_with_state(
        self, message: Message, state: dict
    ) -> Message | None:
        """Accumulate values and emit aggregated result when window is full"""
        if "values" not in state:
            state["values"] = []

        state["values"].append(float(message.value))

        # Keep only window_size values
        if len(state["values"]) > self.window_size:
            state["values"] = state["values"][-self.window_size:]

        if len(state["values"]) < self.window_size:
            return None  # Window not yet full

        values = state["values"]

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

        return Message(
            key=f"{self.aggregation}_{message.key}",
            timestamp=message.timestamp,
            value=result_value,
            tags={"window_size": str(self.window_size)}
        )

# Usage
avg_temp = AggregateTransform(
    broker,
    "sensors.temp",
    "sensors.temp.avg",
    aggregation="avg",
    window_size=10
)
```

### Threshold Alert Transformation -- Planned (V1.x)

> **Note**: `ThresholdAlert` is not yet implemented as a built-in. The design below is aspirational for a future V1.x release. Similar behavior can be achieved using `FilterTransform` with a custom predicate.

```python
class ThresholdAlert(Transformation):
    """
    Emit alert when value crosses threshold.

    Status: Planned (V1.x) — not yet implemented.

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

    async def transform(self, message: Message) -> Message | None:
        """Check threshold and emit alert"""
        value = float(message.value)

        triggered = (
            (self.comparison == ">" and value > self.threshold) or
            (self.comparison == "<" and value < self.threshold)
        )

        if triggered:
            return Message(
                key="alert",
                timestamp=message.timestamp,
                value=f"{message.key} = {value} (threshold: {self.threshold})",
                tags={
                    **message.tags,
                    "alert_type": "threshold",
                    "threshold": str(self.threshold)
                }
            )

        return None

# Usage
alert = ThresholdAlert(broker, "sensors.temp", "alerts.critical", threshold=240)
```

### Unit Conversion -- Planned (V1.x)

> **Note**: `UnitConverter` is not yet implemented as a built-in. The design below is aspirational for a future V1.x release. Similar behavior can be achieved using `MapTransform` with a custom mapping function.

```python
class UnitConverter(Transformation):
    """
    Convert measurement units.

    Status: Planned (V1.x) — not yet implemented.

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

    async def transform(self, message: Message) -> Message:
        """Convert value"""
        converted_value = self.conversion_fn(float(message.value))

        return Message(
            key=self.new_key or message.key,
            timestamp=message.timestamp,
            value=converted_value,
            tags=message.tags
        )

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

## Custom Stateful Transformation Examples

### Example: Latest Combiner (Custom Pattern)

> **Note**: `LatestCombiner` is not a built-in transformation. It is shown here as an example of how to build a custom stateful transformation using the `StatefulTransform` base class.

```python
class LatestCombiner(StatefulTransform):
    """
    Combine latest values from multiple keys.

    Emits a combined message when all expected keys have at least one value.
    This is a custom example — not a built-in transformation.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        expected_keys: list[str]
    ):
        super().__init__(broker, input_channel, output_channel)
        self.expected_keys = expected_keys

    async def transform_with_state(
        self, message: Message, state: dict
    ) -> Message | None:
        """Update latest value for key and combine if all available"""
        if "latest" not in state:
            state["latest"] = {}

        state["latest"][message.key] = message

        # Check if all expected keys have values
        if all(k in state["latest"] for k in self.expected_keys):
            combined_value = {
                key: msg.value
                for key, msg in state["latest"].items()
            }

            return Message(
                key="combined",
                timestamp=datetime.now(timezone.utc),
                value=combined_value,
                tags={}
            )

        return None  # Not all keys have values yet
```

### Example: Time Window Aggregator (Custom Pattern)

> **Note**: Time-window-based aggregation can be partially achieved using the built-in `AggregateTransform` with a count-based window. The time-based variant below is a custom example showing how to extend `StatefulTransform` for more advanced use cases.

```python
class TimeWindowAggregator(StatefulTransform):
    """
    Aggregate values over time window.

    This is a custom example — not a built-in transformation.
    For simpler use cases, see the built-in AggregateTransform.

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
        super().__init__(broker, input_channel, output_channel)
        self.window_duration = window_duration
        self.aggregation = aggregation

    async def transform_with_state(
        self, message: Message, state: dict
    ) -> Message | None:
        """Add message to window and compute aggregation"""
        if "messages" not in state:
            state["messages"] = []

        state["messages"].append(message)

        # Evict expired messages
        cutoff = datetime.now(timezone.utc) - self.window_duration
        state["messages"] = [
            m for m in state["messages"] if m.timestamp >= cutoff
        ]

        if not state["messages"]:
            return None

        values = [float(m.value) for m in state["messages"]]

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

        return Message(
            key=f"{self.aggregation}_window",
            timestamp=datetime.now(timezone.utc),
            value=result_value,
            tags={"window_size": str(len(state["messages"]))}
        )
```

### Deduplicator -- Planned (V1.x)

> **Note**: `Deduplicator` is not yet implemented as a built-in. The design below is aspirational for a future V1.x release.

```python
class Deduplicator(StatefulTransform):
    """
    Remove duplicate messages within time window.

    Status: Planned (V1.x) — not yet implemented.

    Uses message value hash for duplicate detection.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        window_duration: timedelta = timedelta(minutes=1)
    ):
        super().__init__(broker, input_channel, output_channel)
        self.window_duration = window_duration

    async def transform_with_state(
        self, message: Message, state: dict
    ) -> Message | None:
        """Emit message only if not a duplicate within the window"""
        import hashlib

        if "cache" not in state:
            state["cache"] = {}  # hash -> expiry timestamp

        # Clean expired entries
        now = datetime.now(timezone.utc)
        state["cache"] = {
            k: v for k, v in state["cache"].items() if v > now
        }

        # Hash message value
        value_hash = hashlib.md5(
            str(message.value).encode()
        ).hexdigest()

        if value_hash not in state["cache"]:
            # Not a duplicate
            state["cache"][value_hash] = now + self.window_duration
            return message

        return None  # Duplicate — filter out
```

---

## State Helpers

See [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md#state-management-structures) for full implementations:

- **Latest**: Keep latest message per channel
- **TimeWindow**: Time-based sliding window
- **CountWindow**: Count-based sliding window
- **Cache**: Key-value cache with TTL

---

## Built-in Transformations Summary

| Transformation           | Type      | Status              | Description           | Use Case                 |
| ------------------------ | --------- | ------------------- | --------------------- | ------------------------ |
| **FilterTransform**      | Stateless | Implemented         | Filter by predicate   | Remove unwanted messages |
| **MapTransform**         | Stateless | Implemented         | Apply mapping function| Value conversion, enrichment |
| **AggregateTransform**   | Stateful  | Implemented         | Aggregate over window | Statistics, smoothing    |
| **ThresholdAlert**       | Stateless | Planned (V1.x)     | Alert on threshold    | Monitoring, alarms       |
| **UnitConverter**        | Stateless | Planned (V1.x)     | Convert units         | Normalize measurements   |
| **Deduplicator**         | Stateful  | Planned (V1.x)     | Remove duplicates     | Data quality             |

Custom examples shown in this document (not built-in):

| Pattern                  | Type      | Description                  | Notes                           |
| ------------------------ | --------- | ---------------------------- | ------------------------------- |
| **LatestCombiner**       | Stateful  | Combine latest values by key | Custom example pattern          |
| **TimeWindowAggregator** | Stateful  | Aggregate over time window   | Custom example; see AggregateTransform for simpler cases |

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
