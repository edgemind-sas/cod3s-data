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

**Constructor:**
- `Framework(config, plugins=None, observatory=False)` - Create framework
  - `config: PipelineConfig` - Pipeline configuration
  - `plugins: list[str] | None` - Extra plugin module paths (merged with `config.plugins`)
  - `observatory: bool | ObservatoryConfig = False` - Enable Observatory web UI. Pass `True` for defaults, an `ObservatoryConfig` instance for custom settings, or `False` to disable.

**Methods:**
- `async start()` - Load plugins, then start the pipeline (broker, destinations, transformations, sources)
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
- `id: UUID` - Unique message ID (auto-generated)

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
    min_value=20.0,
    max_value=30.0,
    max_messages=1000  # Optional limit
)
```

**Parameters:**
- `rate: float` - Messages per second
- `min_value: float = 0.0` - Minimum value
- `max_value: float = 100.0` - Maximum value
- `max_messages: int | None = None` - Stop after N messages (BATCH mode)

### FileSource

Read messages from JSON/JSONL files.

```python
from cod3s_data.sources.file_sources import FileSource

source = FileSource(
    broker=broker,
    channel="file.data",
    file_path="data.jsonl"
)
```

**Parameters:**
- `file_path: str | Path` - Path to file

> FileSource always operates in BATCH mode.

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

### CollectDestination

Collect messages with assertion helpers for testing.

```python
from cod3s_data.destinations.collect import CollectDestination

dest = CollectDestination(
    broker=broker,
    channel_pattern="test.**"
)

await dest.start()

# Wait for messages
await dest.wait_for_messages(count=10, timeout=5.0)

# Assertions
dest.assert_count(10)
dest.assert_min_count(5)

# Query
all_msgs = dest.get_all()
filtered = dest.filter_by(key="temperature", sensor="TH001")

# Reset
dest.clear()
```

**Methods:**
- `get_all()` - Get all collected messages
- `clear()` - Remove all collected messages
- `assert_count(expected)` - Assert exact message count
- `assert_min_count(minimum)` - Assert minimum message count
- `filter_by(key=None, **tags)` - Filter messages by key and/or tags
- `async wait_for_messages(count, timeout=5.0)` - Wait for N messages with timeout

## Pipeline State

```python
from cod3s_data.framework import PipelineState

# PipelineState enum values:
# IDLE     - Pipeline created but not started
# RUNNING  - Pipeline is active
# STOPPING - Pipeline is shutting down
# STOPPED  - Pipeline has stopped
# ERROR    - Pipeline encountered an error
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
    plugins=["my_package.my_plugin"],  # Optional plugin modules to load
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

## Plugins

The plugin system allows loading custom components (sources, transformations, destinations) from external modules.

### PluginError

```python
from cod3s_data import PluginError
```

Exception raised when a plugin fails to load or register.

### load_plugin

```python
from cod3s_data.plugins import load_plugin

load_plugin("my_package.my_plugin", factory)
```

Load a single plugin module and call its `register(factory)` function.
Falls back to `register_all(factory)` if `register` is not found.

**Raises:** `PluginError` if the module cannot be imported, has no register function, or the register function fails.

### load_plugins

```python
from cod3s_data.plugins import load_plugins

loaded = load_plugins(["plugin_a", "plugin_b"], factory, raise_on_error=True)
```

Load multiple plugins in declaration order.

**Parameters:**
- `module_paths: list[str]` - Dotted module paths to load
- `factory: ComponentFactory` - Factory to register components into
- `raise_on_error: bool = True` - If False, skip failed plugins and continue

**Returns:** List of successfully loaded module paths.

### Writing a Plugin

A plugin module must export a `register(factory)` function (or `register_all` as fallback):

```python
# my_plugin.py
from cod3s_data.config.factory import ComponentFactory
from cod3s_data.sources.base import Source

class MySource(Source):
    async def start(self):
        ...

def register(factory: ComponentFactory) -> None:
    factory.register_source("my_source", MySource)
```

### ComponentFactory Introspection

```python
factory.registered_source_types         # -> set[str], e.g. {"random", "sequence", "csv", "file"}
factory.registered_transformation_types # -> set[str], e.g. {"filter", "map", "aggregate"}
factory.registered_destination_types    # -> set[str], e.g. {"console", "file", "inmemory", "collect"}
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

## Buffer Helpers

Utility structures for stateful transformations and aggregations.

```python
from cod3s_data.core.buffers import Latest, TimeWindow, CountWindow, Cache
```

### Latest

Keep the latest message per channel. Useful for combining messages from multiple channels.

```python
latest = Latest()
latest.update("sensors.temp", msg)
latest.get("sensors.temp")       # -> Message | None
latest.all()                     # -> dict[str, Message]
latest.has_all(["sensors.temp", "sensors.pressure"])  # -> bool
```

### TimeWindow

Time-based sliding window for aggregations over time.

```python
from datetime import timedelta

window = TimeWindow(duration=timedelta(minutes=5))
window.add(msg)
window.all()      # -> list[Message] (within window)
window.count()    # -> int
window.values()   # -> list[Any] (extracted values)
```

### CountWindow

Count-based sliding window for aggregations over N messages.

```python
window = CountWindow(max_count=10)
window.add(msg)
window.all()       # -> list[Message]
window.count()     # -> int
window.is_full()   # -> bool
window.values()    # -> list[Any]
```

### Cache

Key-value cache with optional TTL.

```python
from datetime import timedelta

cache = Cache(ttl=timedelta(minutes=10))
cache.set("key", value)
cache.get("key")     # -> Any | None (None if expired)
cache.has("key")     # -> bool
cache.clear()
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
