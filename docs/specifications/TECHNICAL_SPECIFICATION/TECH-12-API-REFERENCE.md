# API Reference

**Document**: TECH-12-API-REFERENCE.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Purpose**: Complete API reference for all public classes and methods

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-11](TECH-11-DEPLOYMENT.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-99 →](TECH-99-IMPLEMENTATION-GUIDE.md) |

---

## Table of Contents

1. [Core Classes](#core-classes)
2. [Sources](#sources)
3. [Transformations](#transformations)
4. [Destinations](#destinations)
5. [Configuration](#configuration)
6. [Testing Utilities](#testing-utilities)

---

## Core Classes

### Framework

```python
class Framework:
    """
    Main framework coordinator.

    Manages broker, sources, transformations, and destinations.
    """

    def __init__(self, debug: bool = False):
        """
        Initialize framework.

        Args:
            debug: Enable debug mode (verbose logging, tracing)
        """

    @classmethod
    def from_yaml(cls, file_path: str) -> "Framework":
        """
        Load framework from YAML configuration.

        Args:
            file_path: Path to YAML configuration file

        Returns:
            Configured Framework instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValidationError: If configuration is invalid
        """

    async def run(self):
        """
        Run framework (main entry point).

        Starts all components and runs until completion or interrupted.
        """

    async def start(self):
        """Start framework components"""

    async def stop(self):
        """Stop framework gracefully"""
```

### Message

```python
class Message(BaseModel):
    """
    Core message structure.

    Attributes:
        key: Message identifier (what is measured)
        timestamp: When measurement was taken (UTC)
        value: Measurement value (any JSON-serializable type)
        tags: Metadata key-value pairs (all string values)
        id: Unique message identifier (UUID, auto-generated)
    """

    key: str
    timestamp: datetime
    value: Any
    tags: dict[str, str] = Field(default_factory=dict)
    id: UUID = Field(default_factory=uuid4)

    # Methods

    def to_json(self) -> str:
        """Serialize to JSON string"""

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Deserialize from JSON string"""

    def to_dict(self) -> dict:
        """Convert to dictionary"""

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Create from dictionary"""

    def with_tags(self, **new_tags: str) -> "Message":
        """Create new message with additional tags"""

    def with_value(self, new_value: Any) -> "Message":
        """Create new message with different value"""
```

### Broker (InMemoryBroker)

```python
class InMemoryBroker(Broker):
    """
    In-memory message broker.

    Thread-safe, single-process pub/sub.
    """

    def __init__(
        self,
        default_history_size: int = 100,
        enable_metrics: bool = True
    ):
        """
        Initialize broker.

        Args:
            default_history_size: History buffer size per channel
            enable_metrics: Emit metrics to _metrics.* channels
        """

    async def publish(
        self,
        channel: str,
        message: Message,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE
    ) -> PublishResult:
        """
        Publish message to channel.

        Args:
            channel: Target channel (e.g., "sensors.temp")
            message: Message to publish
            delivery_guarantee: Delivery guarantee level

        Returns:
            PublishResult with success and subscriber count
        """

    def subscribe(
        self,
        pattern: str,
        callback: Callable[[Message], Awaitable[None]],
        history: HistoryMode = HistoryMode.NONE,
        history_count: int = 100
    ) -> SubscriptionHandle:
        """
        Subscribe to channel pattern.

        Args:
            pattern: Channel pattern (exact or wildcard)
            callback: Async function for each message
            history: History replay mode
            history_count: Number of historical messages (if RECENT)

        Returns:
            SubscriptionHandle for managing subscription
        """

    def unsubscribe(self, handle: SubscriptionHandle):
        """Remove subscription"""

    def get_history(self, channel: str, count: int = 100) -> list[Message]:
        """Get recent messages from channel"""
```

---

## Sources

### Source (Base Class)

```python
class Source(ABC):
    """
    Base class for all sources.

    Subclasses implement produce() to generate messages.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        batch_mode: BatchMode = BatchMode.BATCH,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE
    ):
        """Initialize source"""

    async def start(self):
        """Start producing messages"""

    async def stop(self):
        """Stop producing messages"""

    @abstractmethod
    async def produce(self) -> AsyncIterator[Message]:
        """Generate messages (implement in subclass)"""
```

### Built-in Sources

#### CSVSource

```python
class CSVSource(Source):
    """Read CSV file"""

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
        """Initialize CSV source"""
```

#### RandomSource

```python
class RandomSource(Source):
    """Generate random values"""

    def __init__(
        self,
        broker: Broker,
        channel: str,
        rate: float = 1.0,
        min_value: float = 0.0,
        max_value: float = 100.0
    ):
        """Initialize random source"""
```

#### SequenceSource

```python
class SequenceSource(Source):
    """Generate sequential integers"""

    def __init__(
        self,
        broker: Broker,
        channel: str,
        start: int = 0,
        end: int = 100,
        rate: float = 10.0
    ):
        """Initialize sequence source"""
```

#### FileSource

```python
class FileSource(Source):
    """Read text file line by line"""

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str,
        encoding: str = "utf-8"
    ):
        """Initialize file source"""
```

---

## Transformations

### StatelessTransform (Base Class)

```python
class StatelessTransform(ABC):
    """
    Stateless transformation (1:N).

    Each input message produces 0+ output messages.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str
    ):
        """Initialize transformation"""

    async def start(self):
        """Start transformation"""

    async def stop(self):
        """Stop transformation"""

    @abstractmethod
    async def transform(self, message: Message) -> list[Message]:
        """Transform message (implement in subclass)"""
```

### StatefulTransform (Base Class)

```python
class StatefulTransform(ABC):
    """
    Stateful transformation (N:M).

    Maintains state across messages.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: list[str],
        output_channel: str
    ):
        """Initialize transformation"""

    @abstractmethod
    async def update_state(self, message: Message):
        """Update state with new message"""

    @abstractmethod
    async def transform(self) -> list[Message]:
        """Transform current state to messages"""
```

### Built-in Transformations

#### FilterTransform

```python
class FilterTransform(StatelessTransform):
    """Filter messages by predicate"""

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        predicate: Callable[[Message], bool]
    ):
        """Initialize filter"""
```

#### ThresholdAlert

```python
class ThresholdAlert(StatelessTransform):
    """Emit alert when value crosses threshold"""

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        threshold: float,
        comparison: str = ">"
    ):
        """Initialize threshold alert"""
```

---

## Destinations

### Destination (Base Class)

```python
class Destination(ABC):
    """
    Base class for all destinations.

    Subclasses implement write() to persist messages.
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
        """Initialize destination"""

    async def start(self):
        """Start destination"""

    async def stop(self):
        """Stop destination gracefully"""

    @abstractmethod
    async def write(self, message: Message):
        """Write message (implement in subclass)"""

    async def close(self):
        """Close resources (optional)"""
```

### Built-in Destinations

#### ConsoleDestination

```python
class ConsoleDestination(Destination):
    """Print messages to stdout"""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        format: str = "json"
    ):
        """Initialize console destination"""
```

#### FileDestination

```python
class FileDestination(Destination):
    """Append messages to file (JSON lines)"""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        file_path: str,
        **kwargs
    ):
        """Initialize file destination"""
```

---

## Configuration

### PipelineConfig

```python
class PipelineConfig(BaseModel):
    """
    Root configuration model.

    Validated by Pydantic.
    """

    sources: list[SourceConfig]
    transformations: list[TransformationConfig]
    destinations: list[DestinationConfig]
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
```

---

## Testing Utilities

### CollectDestination

```python
class CollectDestination(Destination):
    """
    Collect messages in memory (testing).

    Provides assertion helpers.
    """

    def __init__(self, broker: Broker, channel_pattern: str):
        """Initialize collector"""

    def get_all(self) -> list[Message]:
        """Get all collected messages"""

    def clear(self):
        """Clear collected messages"""

    def assert_count(self, expected: int):
        """Assert exact message count"""

    def assert_values(self, expected: list):
        """Assert message values match"""

    def assert_keys(self, expected: list[str]):
        """Assert message keys match"""
```

---

## Enums

### BatchMode

```python
class BatchMode(Enum):
    BATCH = "batch"          # Finite dataset
    REALTIME = "realtime"    # Continuous
    TRANSPOSE = "transpose"  # Timestamp-based replay
```

### DeliveryGuarantee

```python
class DeliveryGuarantee(Enum):
    AT_MOST_ONCE = "at_most_once"    # Fire-and-forget
    AT_LEAST_ONCE = "at_least_once"  # May duplicate
```

### HistoryMode

```python
class HistoryMode(Enum):
    NONE = "none"      # New messages only
    RECENT = "recent"  # Last N messages
    ALL = "all"        # Full replay
```

### OverflowStrategy

```python
class OverflowStrategy(Enum):
    DROP_OLDEST = "drop_oldest"  # Remove oldest
    DROP_NEWEST = "drop_newest"  # Discard new
    BLOCK = "block"              # Wait for space
```

### RetryStrategy

```python
class RetryStrategy(Enum):
    EXPONENTIAL = "exponential"  # 1s, 2s, 4s, ...
    FIXED = "fixed"              # 1s, 1s, 1s, ...
```

---

## References

Complete API specifications in respective technical documents:
- [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md)
- [TECH-03-BROKER-API](TECH-03-BROKER-API.md)
- [TECH-04-SOURCES-API](TECH-04-SOURCES-API.md)
- [TECH-05-TRANSFORMATIONS-API](TECH-05-TRANSFORMATIONS-API.md)
- [TECH-06-DESTINATIONS-API](TECH-06-DESTINATIONS-API.md)

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-11](TECH-11-DEPLOYMENT.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-99 →](TECH-99-IMPLEMENTATION-GUIDE.md) |
