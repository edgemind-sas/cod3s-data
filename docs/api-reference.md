# API Reference

## Core Components

### Framework

Main coordinator for managing pipeline lifecycle.

```python
from cod3s_data.framework import Framework
from cod3s_data.config import PipelineConfig

async def run_pipeline():
    config = PipelineConfig(...)

    async with Framework(config) as framework:
        await framework.run()
```

**Methods:**
- `async start()` - Start the pipeline (broker, destinations, transformations, sources)
- `async run()` - Run until completion or stopped
- `async stop()` - Graceful shutdown
- `is_running: bool` - Check if framework is running

### Message

Immutable data container for messages flowing through the pipeline.

```python
from cod3s_data.core.message import Message
from datetime import datetime, timezone

msg = Message(
    key="sensor_reading",
    timestamp=datetime.now(timezone.utc),
    value=25.3,
    tags={"sensor_id": "temp_01", "location": "room1"}
)
```

**Fields:**
- `key: str` - Message identifier
- `timestamp: datetime` - UTC timestamp (timezone-aware)
- `value: Any` - Message payload
- `tags: dict[str, str]` - Metadata tags
- `id: str` - Unique message ID (auto-generated)

**Methods:**
- `with_value(new_value)` - Create new message with different value
- `with_tags(**tags)` - Create new message with additional tags
- `to_json()` - Serialize to JSON string
- `to_dict()` - Convert to dictionary
- `from_json(json_str)` - Deserialize from JSON
- `from_dict(data)` - Create from dictionary

## Broker

### InMemoryBroker

Single-process pub/sub message broker.

```python
from cod3s_data.broker.in_memory import InMemoryBroker

broker = InMemoryBroker(
    default_history_size=100,
    enable_metrics=True
)

await broker.start()

# Publish
await broker.publish("channel.name", message)

# Subscribe
async def callback(msg: Message):
    print(msg)

handle = broker.subscribe("channel.*", callback)

# Unsubscribe
broker.unsubscribe(handle)

await broker.stop()
```

**Constructor Parameters:**
- `default_history_size: int = 100` - History buffer size per channel
- `enable_metrics: bool = True` - Emit metrics to `_metrics.*` channels

**Methods:**
- `async publish(channel, message, delivery_guarantee)` - Publish message
- `subscribe(pattern, callback, history, history_count)` - Subscribe to pattern
- `unsubscribe(handle)` - Remove subscription
- `get_history(channel, count)` - Get recent messages
- `get_metrics()` - Get broker metrics

## Sources

### SequenceSource

Generate sequential numbers.

```python
from cod3s_data.sources.test_sources import SequenceSource

source = SequenceSource(
    broker=broker,
    channel="numbers",
    start_value=0,
    end_value=100,
    rate=10.0  # 10 msg/s
)

await source.start()  # Runs until end_value
```

**Parameters:**
- `start_value: int` - First value (inclusive)
- `end_value: int` - Last value (exclusive)
- `rate: float` - Messages per second

### RandomSource

Generate random values.

```python
from cod3s_data.sources.test_sources import RandomSource

source = RandomSource(
    broker=broker,
    channel="sensors.temp",
    rate=10.0,
    value_min=20.0,
    value_max=30.0,
    max_messages=1000  # Optional limit
)
```

**Parameters:**
- `rate: float` - Messages per second
- `value_min: float = 0.0` - Minimum value
- `value_max: float = 100.0` - Maximum value
- `max_messages: int | None = None` - Stop after N messages (BATCH mode)

### FileSource

Read messages from JSON/JSONL files.

```python
from cod3s_data.sources.file_sources import FileSource

source = FileSource(
    broker=broker,
    channel="file.data",
    file_path="data.jsonl",
    batch_mode="batch"  # or "transpose"
)
```

**Parameters:**
- `file_path: str | Path` - Path to file
- `batch_mode: str = "batch"` - "batch" or "transpose" (for timestamp-based replay)

### CSVSource

Read from CSV files using Polars.

```python
from cod3s_data.sources.file_sources import CSVSource

source = CSVSource(
    broker=broker,
    channel="csv.data",
    file_path="data.csv",
    timestamp_column="timestamp",  # Optional
    value_column="value",
    key_column="key"
)
```

## Transformations

### FilterTransform

Filter messages by predicate.

```python
from cod3s_data.transformations.builtin import FilterTransform

transform = FilterTransform(
    broker=broker,
    input_channels="input",
    output_channel="filtered",
    predicate=lambda msg: msg.value > 10
)

await transform.start()
```

**YAML Configuration:**
```yaml
type: filter
input_channels: input
output_channel: filtered
params:
  predicate_code: "lambda msg: msg.value > 10"
```

### MapTransform

Transform message values.

```python
from cod3s_data.transformations.builtin import MapTransform

transform = MapTransform(
    broker=broker,
    input_channels="input",
    output_channel="mapped",
    map_fn=lambda x: x * 2
)
```

**YAML Configuration:**
```yaml
type: map
input_channels: input
output_channel: mapped
params:
  map_fn_code: "lambda x: x * 2"
```

### AggregateTransform

Aggregate over time or count windows.

```python
from cod3s_data.transformations.builtin import AggregateTransform

transform = AggregateTransform(
    broker=broker,
    input_channels="input",
    output_channel="aggregated",
    window_type="count",
    window_size=10,
    aggregation_fn=lambda msgs: sum(m.value for m in msgs) / len(msgs)
)
```

**YAML Configuration:**
```yaml
type: aggregate
input_channels: input
output_channel: aggregated
params:
  window_type: count  # or "time"
  window_size: 10     # for count windows
  window_duration: 5.0  # for time windows (seconds)
  aggregation_fn_code: "lambda msgs: sum(m.value for m in msgs) / len(msgs)"
```

## Destinations

### ConsoleDestination

Print messages to stdout.

```python
from cod3s_data.destinations.core import ConsoleDestination

dest = ConsoleDestination(
    broker=broker,
    channel_pattern="sensor.**"
)

await dest.start()
```

### FileDestination

Write messages to files.

```python
from cod3s_data.destinations.core import FileDestination

dest = FileDestination(
    broker=broker,
    channel_pattern="data.**",
    file_path="output.jsonl",
    batch_size=100
)
```

### InMemoryDestination

Store messages in memory (for testing).

```python
from cod3s_data.destinations.core import InMemoryDestination

dest = InMemoryDestination(
    broker=broker,
    channel_pattern="test.**"
)

await dest.start()

# Get messages
messages = dest.get_all()
```

## Configuration

### PipelineConfig

Top-level pipeline configuration.

```python
from cod3s_data.config import (
    PipelineConfig,
    SourceConfig,
    TransformConfig,
    DestinationConfig,
    BrokerConfig
)

config = PipelineConfig(
    name="my_pipeline",
    broker=BrokerConfig(
        enable_metrics=True,
        history_size=100
    ),
    sources=[
        SourceConfig(
            type="sequence",
            channel="numbers",
            params={"start_value": 1, "end_value": 100}
        )
    ],
    transformations=[
        TransformConfig(
            type="filter",
            input_channels="numbers",
            output_channel="evens",
            params={"predicate_code": "lambda msg: msg.value % 2 == 0"}
        )
    ],
    destinations=[
        DestinationConfig(
            type="console",
            channel_pattern="evens",
            params={}
        )
    ]
)
```

### Load from YAML

```python
from cod3s_data.config.loaders import load_yaml

config = load_yaml("pipeline.yaml")
```

## Observability

### Logging

```python
from cod3s_data.observability import configure_logging, get_logger

# Configure logging
configure_logging(
    level="INFO",
    format="json",  # or "console"
    enable_colors=True
)

# Get logger
logger = get_logger(__name__, component="my_source")
logger.info("processing_message", message_id="123", count=42)
```

### Metrics

```python
from cod3s_data.observability import emit_metric, MetricsCollector

# Emit single metric
emit_metric("messages.processed", 1, tags={"channel": "sensors"})

# Use collector for batching
collector = MetricsCollector("source", tags={"source_id": "src-1"})
collector.increment("messages_produced", 5)
collector.set("queue_size", 42)
await collector.flush()
```

## Channel Patterns

### Exact Match
`sensors.temp` matches only `sensors.temp`

### Single-Level Wildcard
`sensors.*` matches:
- `sensors.temp` ✓
- `sensors.pressure` ✓
- `sensors.room1.temp` ✗

### Multi-Level Wildcard
`sensors.**` matches:
- `sensors.temp` ✓
- `sensors.pressure` ✓
- `sensors.room1.temp` ✓
- `sensors.room1.rack2.temp` ✓

## Error Handling

### Retry Configuration

```python
from cod3s_data.destinations.base import RetryStrategy

dest = FileDestination(
    broker=broker,
    channel_pattern="data",
    file_path="output.jsonl",
    retry_attempts=3,
    retry_strategy=RetryStrategy.EXPONENTIAL,
    dlq_channel="dlq.failed"  # Dead Letter Queue
)
```

### Dead Letter Queue

Failed messages are sent to the DLQ channel after retry exhaustion:

```python
# Subscribe to DLQ
dlq_dest = InMemoryDestination(
    broker=broker,
    channel_pattern="dlq.**"
)
```

## Performance Tuning

### Buffer Sizes

```python
dest = FileDestination(
    broker=broker,
    channel_pattern="data",
    file_path="output.jsonl",
    buffer_size=10000,  # Increase for high throughput
    overflow_strategy=OverflowStrategy.DROP_OLDEST
)
```

### History Limits

```python
broker = InMemoryBroker(
    default_history_size=1000,  # Increase for more history
    enable_metrics=False  # Disable for lower overhead
)
```

### Batch Sizes

```python
dest = FileDestination(
    broker=broker,
    channel_pattern="data",
    file_path="output.jsonl",
    batch_size=1000  # Write in larger batches
)
```
