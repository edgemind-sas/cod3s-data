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

**Parameters:**
- `file_path: str | Path` - Path to CSV file
- `key_column: str = "key"` - Column holding `message.key`
- `timestamp_column: str = "timestamp"` - Column holding `message.timestamp`
- `value_column: str = "value"` - Column holding a scalar `message.value`
- `value_columns: list[str] | None = None` - Use several columns; `message.value` becomes a dict
- `tag_columns: list[str] | None = None` - Columns to carry as `message.tags`
- `exclude_columns: list[str] | None = None` - Columns to ignore entirely
- `column_mapping: dict[str, str] | None = None` - Rename columns before mapping (`{"T0": "extruder"}`)
- `pack_remaining_as_value: bool = False` - Pack every column not otherwise used into a dict value
- `default_key: str | None = None` - Fixed key for every row, when the file has no key column
- `default_tags: dict[str, str] | None = None` - Tags added to every message
- `timestamp_mode: str = "iso"` - `"iso"` or `"epoch"` (seconds since epoch)
- `timestamp_microseconds_column: str | None = None` - Column adding sub-second precision to an epoch timestamp
- `rebase_timestamps: bool = False` - Shift the whole file so its first row lands at start time
- `delimiter: str = ","`, `encoding: str = "utf-8"`, `skip_rows: int = 0`, `has_header: bool = True`, `max_rows: int | None = None`
- `replay: bool = False` - Emit rows in temporal order, honouring the gaps between timestamps
- `speed_factor: float = 1.0` - Replay speed multiplier (`2.0` = twice as fast)

### CSVWatchSource

Follow a CSV file that is still being written (REALTIME mode). Reads the whole
file on start, then polls for appended lines.

```python
from cod3s_data.sources.file_sources import CSVWatchSource

source = CSVWatchSource(
    broker=broker,
    channel="sensors.live",
    file_path="/var/log/printer/telemetry.csv",
    poll_interval=0.5,
    value_columns=["extruder", "bed"],
    tag_columns=["printer_id"],
)
```

**Parameters:**
- `file_path: str | Path` - File to follow
- `poll_interval: float = 1.0` - Seconds between polls
- `key_column`, `timestamp_column`, `value_column`, `value_columns`, `tag_columns`,
  `delimiter`, `encoding`, `has_header` - Same meaning as `CSVSource`

Unlike `CSVSource`, which reads through polars and gets typed columns, this
source reads with `csv.reader` and gets strings. Any cell that parses as a
number is converted, so values reach numeric transformations as numbers;
anything else is left as a string. A column of zero-padded identifiers is
therefore read as numbers — carry it in `tag_columns`, which are always
strings, rather than in `value_columns`.

### DirectoryWatchSource

Watch a directory and emit one message per new file. Detection is by filename:
the source compares the set of names between polls.

```python
from cod3s_data.sources.file_sources import DirectoryWatchSource

source = DirectoryWatchSource(
    broker=broker,
    channel="jobs.incoming",
    directory="/var/spool/gcode",
    glob_pattern="*.gcode",
    poll_interval=2.0,
    emit_existing=False,
)
```

**Parameters:**
- `directory: str | Path` - Directory to watch
- `glob_pattern: str = "*"` - Filter, e.g. `"*.csv"`
- `poll_interval: float = 1.0` - Seconds between polls
- `emit_existing: bool = False` - Also emit files already present at startup

### ParamFileSource

Publish the contents of a YAML/JSON file as parameter messages, one per entry.
Each parameter is published on its own sub-channel `{channel}.{key}`, which is
what a [`ParamRef`](#dynamic-parameters-paramref) subscribes to.

```python
from cod3s_data.sources.param_file import ParamFileSource

source = ParamFileSource(
    broker=broker,
    channel="params",
    file_path="jobs/PLA.yaml",
)
```

Given `jobs/PLA.yaml`:

```yaml
extruder:
  setpoint: 210.0
  tolerance: 5.0
bed:
  setpoint: 60.0
```

the source publishes `params.extruder.setpoint`, `params.extruder.tolerance`
and `params.bed.setpoint`.

**Parameters:**
- `file_path: str | Path` - YAML or JSON file, with a mapping at the top level
- `flatten: bool = True` - Flatten nested mappings into dotted keys. With
  `flatten=False`, each top-level entry is published whole, as a dict value.

> ParamFileSource operates in BATCH mode: it publishes once, at start.

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

### AlarmTransform

Monitor a numeric stream against fixed thresholds. Emits **only on state
transitions** (OK → ALARM, ALARM → OK), so a value that stays out of range
produces one message, not one per sample.

```python
from cod3s_data.transformations.builtin import AlarmTransform

transform = AlarmTransform(
    broker=broker,
    input_channels="sensors.extruder",
    output_channel="alarms",
    min_value=190.0,
    max_value=230.0,
)
```

**Parameters:**
- `min_value: float | None = None` - Lower threshold
- `max_value: float | None = None` - Upper threshold

The output message has key `{input_key}.alarm` and a dict value:

```python
{"original_value": 235.1, "alarm_type": "max", "threshold": 230.0, "status": "ACTIVE"}
```

`status` is `"ACTIVE"` on entry and `"CLEARED"` on return to range.

```yaml
type: alarm
input_channels: sensors.extruder
output_channel: alarms
params:
  min_value: 190.0
  max_value: 230.0
```

### RelativeAlarmTransform

Alarm on deviation from a setpoint rather than on absolute bounds:
`|value - setpoint| > tolerance`. State is tracked **per message key**, so one
transform on a wildcard channel handles every sensor independently.

```python
from cod3s_data.transformations.builtin import RelativeAlarmTransform

transform = RelativeAlarmTransform(
    broker=broker,
    input_channels="sensors.smoothed.*",
    output_channel="alarms",
    setpoint={"extruder": 210.0, "bed": 60.0},
    tolerance_pct=5.0,
)
```

**Parameters:**
- `setpoint: float | dict[str, float]` - Target value, global or per key. Messages
  whose key has no setpoint are ignored.
- `tolerance_pct: float | None = None` - Tolerance as a percentage of the setpoint
- `tolerance_abs: float | None = None` - Tolerance in absolute units
- `alarm_type_label: str = "relative_threshold"` - Value written to `alarm_type`

Exactly one of `tolerance_pct` or `tolerance_abs` must be given. The output
message has key `{input_key}.alarm`, inherits the input tags, and carries:

```python
{
    "status": "ACTIVE",          # or "CLEARED"
    "alarm_type": "relative_threshold",
    "direction": "OVER",         # or "UNDER"; empty on CLEARED
    "original_value": {
        "actual": 224.0,
        "setpoint": 210.0,
        "deviation": 14.0,
        "tolerance": 10.5,
        "deviation_pct": 6.6667,  # only when tolerance_pct is used
    },
}
```

### ThrottleTransform

Rate-limit a stream: forward the first message, then suppress everything until
`interval` seconds have passed.

```python
from cod3s_data.transformations.builtin import ThrottleTransform

transform = ThrottleTransform(
    broker=broker,
    input_channels="sensors.**",
    output_channel="sensors.downsampled",
    interval=0.1,
    per_key=True,
)
```

**Parameters:**
- `interval: float = 1.0` - Minimum seconds between two emitted messages
- `per_key: bool = False` - Throttle each `message.key` on its own clock. Use this
  on a wildcard subscription, where a single shared clock would let the busiest
  sensor starve the others.

### UnpackTransform

Explode a dict-valued message into one message per entry, each published on its
own sub-channel `{output_channel}.{key}`. Timestamp and tags are inherited;
non-dict values pass through unchanged on `output_channel`.

```python
from cod3s_data.transformations.builtin import UnpackTransform

transform = UnpackTransform(
    broker=broker,
    input_channels="csv.rows",
    output_channel="sensors",
)
```

A message valued `{"extruder": 210.0, "bed": 60.0}` becomes two messages, on
`sensors.extruder` and `sensors.bed`. This is the usual bridge between a CSV
source reading wide rows and per-sensor transforms downstream.

### MovingAverageTransform

Sliding-window mean, **per key**. Emits one smoothed message per input message
once `min_samples` values are buffered — unlike `AggregateTransform`, which uses
a tumbling window shared across keys and emits once per closed window.

```python
from cod3s_data.transformations.builtin import MovingAverageTransform

transform = MovingAverageTransform(
    broker=broker,
    input_channels="sensors.*",
    output_channel="sensors.smoothed",
    window_type="count",
    window_size=10,
    min_samples=3,
    key_suffix="_avg",
)
```

**Parameters:**
- `window_type: str = "count"` - `"count"` or `"time"`
- `window_size: int | None = None` - Number of samples, for count windows
- `window_duration: float | None = None` - Seconds, for time windows
- `min_samples: int = 1` - Emit nothing until this many samples are buffered
- `key_suffix: str = ""` - Appended to the output `message.key`, and the message is
  re-published on `{output_channel}.{new_key}`. Lets a smoothed signal coexist with
  its raw counterpart in a sink that keys by `message.key`, such as InfluxDB.

### MedianFilterTransform

Same as `MovingAverageTransform`, but takes the median of the window — more
robust to isolated spikes. Same parameters.

```python
from cod3s_data.transformations.builtin import MedianFilterTransform

transform = MedianFilterTransform(
    broker=broker,
    input_channels="sensors.*",
    output_channel="sensors.filtered",
    window_size=5,
)
```

### DeviationFilterTransform

Reject or clip values that stray from a setpoint by more than a tolerance.
Stateless. Messages whose key has no setpoint, and non-numeric values, pass
through unchanged.

```python
from cod3s_data.transformations.builtin import DeviationFilterTransform

transform = DeviationFilterTransform(
    broker=broker,
    input_channels="sensors.*",
    output_channel="sensors.clean",
    setpoint={"extruder": 210.0},
    tolerance_pct=10.0,
    mode="clip",
)
```

**Parameters:**
- `setpoint: float | dict[str, float]` - Target value, global or per key
- `tolerance_pct: float | None = None` - Tolerance as a percentage of the setpoint
- `tolerance_abs: float | None = None` - Tolerance in absolute units
- `mode: str = "reject"` - `"reject"` drops out-of-band messages; `"clip"` clamps
  them to `[setpoint - tol, setpoint + tol]`
- `key_suffix: str = ""` - Appended to the output `message.key`

Exactly one of `tolerance_pct` or `tolerance_abs` must be given.

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

### InfluxDBDestination

Write messages to InfluxDB 2.x as time-series points. Requires the optional
dependency:

```bash
pip install 'cod3s-data[influxdb]'
```

```python
from cod3s_data.destinations.influxdb import InfluxDBDestination

dest = InfluxDBDestination(
    broker=broker,
    channel_pattern="sensors.**",
    url="http://localhost:8086",
    token="my-token",
    org="cod3s",
    bucket="sensor_data",
    extra_tags={"printer": "gemini3d"},
    batch_size=100,
)
```

**Message to point mapping:**
- `message.key` becomes the measurement name, unless `measurement` overrides it
- `message.timestamp` becomes the point timestamp
- `message.tags`, merged with `extra_tags`, become InfluxDB tags
- `message.value` becomes the fields: a dict contributes one field per entry
  (nested dicts are flattened into dotted field names), any other value is
  stored in a single field named `value`

**Parameters:**
- `url: str = "http://localhost:8086"` - Server URL
- `token: str = ""` - Authentication token
- `org: str = ""` - Organization
- `bucket: str = ""` - Target bucket
- `measurement: str | None = None` - Fixed measurement name
- `extra_tags: dict[str, str] | None = None` - Tags added to every point
- `buffer_size`, `overflow_strategy`, `retry_attempts`, `retry_strategy`,
  `dlq_channel`, `batch_size` - Inherited from `Destination`

```yaml
type: influxdb
channel_pattern: sensors.**
params:
  url: http://localhost:8086
  token: my-token
  org: cod3s
  bucket: sensor_data
  extra_tags:
    printer: gemini3d
```

> InfluxDB rejects a field that changes type between points. Keep a given
> measurement's field types stable across the pipeline.

A local server for development and for the integration tests:

```bash
docker compose -f docker-compose.influxdb.yml up -d
```

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

### Component type names

The `type:` field of a YAML component resolves against the `ComponentFactory`
registry. Built-ins:

| Kind | `type:` | Class |
|---|---|---|
| Source | `random` | `RandomSource` |
| Source | `sequence` | `SequenceSource` |
| Source | `file` | `FileSource` |
| Source | `csv` | `CSVSource` |
| Source | `csv_watch` | `CSVWatchSource` |
| Source | `directory_watch` | `DirectoryWatchSource` |
| Source | `param_file` | `ParamFileSource` |
| Source | `csv_directory` | `CSVDirectorySource` |
| Source | `mqtt` | `MQTTSource` (needs the `mqtt` extra) |
| Transformation | `filter` | `FilterTransform` |
| Transformation | `map` | `MapTransform` |
| Transformation | `aggregate` | `AggregateTransform` |
| Transformation | `alarm` | `AlarmTransform` |
| Transformation | `relative_alarm` | `RelativeAlarmTransform` |
| Transformation | `bounds_alarm` | `BoundsAlarmTransform` |
| Transformation | `alarm_gate` | `AlarmGateTransform` |
| Transformation | `throttle` | `ThrottleTransform` |
| Transformation | `unpack` | `UnpackTransform` |
| Transformation | `moving_average` | `MovingAverageTransform` |
| Transformation | `median_filter` | `MedianFilterTransform` |
| Transformation | `deviation_filter` | `DeviationFilterTransform` |
| Destination | `console` | `ConsoleDestination` |
| Destination | `file` | `FileDestination` |
| Destination | `inmemory` | `InMemoryDestination` |
| Destination | `collect` | `CollectDestination` |
| Destination | `influxdb` | `InfluxDBDestination` |

Plugins add their own names to the same registry — see [Plugins](#plugins).

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

### Pipeline display metadata

Fields that exist only to make a pipeline legible in the
[Observatory](observatory.md) UI. They never affect routing or behaviour.

```yaml
name: extruder_monitoring          # identifier, used in logs and metrics
display_name: Extruder monitoring  # title shown in the Observatory header
subtitle: Line 3, PLA job          # second line under the title

sources:
  - type: csv
    label: Telemetry file          # node name in the topology graph
    description: >                 # shown when hovering the node
      Reads the printer's telemetry export, one row per second.
    channel: sensors.raw
    params:
      file_path: telemetry.csv
```

- `display_name: str | None` and `subtitle: str | None` on the pipeline
- `label: str | None` and `description: str | None` on every source,
  transformation and destination

All four default to empty. Without a `label`, a component shows as its
component id (`src-0`, `tfm-1`, `dst-0`).

### Observatory configuration

The optional `observatory:` section configures the web UI. It is only read when
the Observatory is enabled, and is documented in full in
[Observatory → Configuration](observatory.md#configuration).

```yaml
observatory:
  port: 8765
  debug:
    enabled: true
  sampling:
    strategy: every_nth
    rate: 10
```

### Environment variables

`load_yaml()` and `load_dict()` apply these overrides after reading the file and
before validation. An unset variable changes nothing.

| Variable | Overrides | Type |
|---|---|---|
| `COD3S_PIPELINE_NAME` | `name` | str |
| `COD3S_BROKER_ENABLE_METRICS` | `broker.enable_metrics` | bool |
| `COD3S_BROKER_HISTORY_SIZE` | `broker.history_size` | int |
| `COD3S_OBSERVATORY_ENABLED` | `observatory.enabled` | bool |
| `COD3S_OBSERVATORY_HOST` | `observatory.host` | str |
| `COD3S_OBSERVATORY_PORT` | `observatory.port` | int |
| `COD3S_OBSERVATORY_BUFFER_SIZE` | `observatory.buffer_size` | int |
| `COD3S_OBSERVATORY_MEMORY_LIMIT_MB` | `observatory.memory_limit_mb` | int |
| `COD3S_OBSERVATORY_DEBUG` | `observatory.debug.enabled` | bool |
| `COD3S_OBSERVATORY_DEBUG_GRANULARITY` | `observatory.debug.granularity` | str |
| `COD3S_OBSERVATORY_DEBUG_AUTO_PAUSE` | `observatory.debug.auto_pause` | bool |
| `COD3S_OBSERVATORY_SAMPLING_STRATEGY` | `observatory.sampling.strategy` | str |
| `COD3S_OBSERVATORY_SAMPLING_RATE` | `observatory.sampling.rate` | int |
| `COD3S_OBSERVATORY_SAMPLING_INTERVAL_MS` | `observatory.sampling.interval_ms` | int |

Booleans read as true for `true`, `1` or `yes`, case-insensitive; anything else
is false. A value that cannot be parsed as its declared type raises at load
time — except `COD3S_BROKER_HISTORY_SIZE`, which is silently ignored when
unparsable.

```bash
COD3S_PIPELINE_NAME=staging COD3S_BROKER_HISTORY_SIZE=5000 \
  cod3s-data run pipeline.yaml
```

### Dynamic parameters (ParamRef)

Any component parameter can be sourced from a broker channel instead of being
fixed in the configuration. Replace the value with a `ref` mapping:

```yaml
transformations:
  - type: relative_alarm
    input_channels: sensors.smoothed.*
    output_channel: alarms
    params:
      setpoint:
        ref: params.extruder.setpoint
        default: 210.0
      tolerance_pct:
        ref: params.extruder
        key: tolerance_pct
        default: 5.0
```

**Fields:**
- `ref: str` - Channel publishing this parameter's value
- `default: Any = None` - Value used until the first message arrives on `ref`
- `key: str | None = None` - When the channel publishes dict-valued messages,
  extract this key from the dict

At construction the factory substitutes `default` and attaches a
`ParameterStore` to the component. The store subscribes to `ref` and rebinds
the attribute on every new message; it also reads the channel's history at
`start()`, so a transform that starts after the parameter was published is
hydrated before its first data message arrives. Parameter references work on
sources, transformations and destinations alike, and nest one level deep — a
`ParamRef` must appear as a direct value in `params`, not inside a nested dict
or list.

Values usually come from a [`ParamFileSource`](#paramfilesource), which turns a
YAML job file into one message per parameter. They can also be published by any
other source, or updated at runtime.

**Reading and updating at runtime** — the Observatory exposes the parameter
plane over HTTP and WebSocket, and the *Parameters* page of the UI is built on
it:

```bash
# List every parameter declared via ParamRef, with its current value
curl http://localhost:8765/api/params

# Publish a new value; every store subscribed to that channel rebinds
curl -X POST http://localhost:8765/api/params/params.extruder.setpoint \
     -H 'Content-Type: application/json' \
     -d '{"value": 215.0}'
```

The same operation over the Observatory WebSocket:

```json
{"type": "param.update", "payload": {"channel": "params.extruder.setpoint", "value": 215.0}}
```

Pass `"key"` alongside `"value"` to update a single entry of a dict-valued
parameter channel.

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
factory.registered_source_types          # -> set[str], the "type:" names usable in YAML
factory.registered_transformation_types
factory.registered_destination_types
```

See [Component type names](#component-type-names) for the built-in registry.

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

The message arrives with its key, timestamp and value unchanged, plus tags
saying why it is there. Without them it would be indistinguishable from
ordinary traffic on any consumer reading both.

| Tag | Contents |
|---|---|
| `dlq_error_type` | Exception class, e.g. `ConnectionRefusedError` |
| `dlq_error` | Exception message, truncated to 200 characters; the class name when the exception carries no message |
| `dlq_destination` | Class of the destination that gave up, e.g. `InfluxDBDestination` |
| `dlq_channel_pattern` | Pattern that destination subscribes to |
| `dlq_attempts` | Attempts spent — always the full `retry_attempts` budget, since a message only reaches the DLQ once it is exhausted |
| `dlq_component_id` | Component id, present only for a pipeline built from a configuration file |

`dlq_channel_pattern` is the pattern, not the channel the message was published
on: the broker knows that channel but drops it before calling the subscriber.

Tags rather than a wrapper around the value, so a consumer can read the
dead-letter channel as an ordinary stream. Original tags are preserved, and the
message published on the input channel is untouched — `Message` is immutable
and the DLQ gets a copy.

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
