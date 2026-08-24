# Quick Start Guide

This guide will help you create and run your first COD3S data pipeline in 5 minutes.

## Your First Pipeline

### 1. Create a Configuration File

Create a file named `my_pipeline.yaml`:

```yaml
name: my_first_pipeline

sources:
  - type: sequence
    channel: numbers
    params:
      start_value: 1
      end_value: 11
      rate: 2.0

destinations:
  - type: console
    channel_pattern: numbers
    params: {}
```

### 2. Run the Pipeline

```bash
cod3s-data run my_pipeline.yaml
```

You should see numbers 1-10 printed to the console at 2 messages per second!

## Understanding the Pipeline

Let's break down what happened:

1. **Source**: A `sequence` source generates numbers 1-10
2. **Channel**: Messages are published to the `numbers` channel
3. **Destination**: A `console` destination subscribes to `numbers` and prints messages

## Adding Transformations

Let's add a transformation to filter even numbers:

```yaml
name: filtering_pipeline

sources:
  - type: sequence
    channel: input
    params:
      start_value: 1
      end_value: 21
      rate: 5.0

transformations:
  - type: filter
    input_channels: input
    output_channel: evens
    params:
      predicate_code: "lambda msg: msg.value % 2 == 0"

destinations:
  - type: console
    channel_pattern: evens
    params: {}
```

Run it:

```bash
cod3s-data run filtering_pipeline.yaml
```

Now you'll only see even numbers: 2, 4, 6, 8, ..., 20

## Programmatic API

You can also create pipelines programmatically in Python:

```python
import asyncio
from cod3s_data.config import PipelineConfig, SourceConfig, DestinationConfig
from cod3s_data.framework import Framework

async def main():
    config = PipelineConfig(
        name="programmatic_pipeline",
        sources=[
            SourceConfig(
                type="sequence",
                channel="numbers",
                params={"start_value": 1, "end_value": 11, "rate": 2.0}
            )
        ],
        destinations=[
            DestinationConfig(
                type="console",
                channel_pattern="numbers",
                params={}
            )
        ]
    )

    async with Framework(config) as framework:
        await framework.run()

asyncio.run(main())
```

## Key Concepts

### Sources

Sources generate or read data and publish to channels:
- **sequence**: Sequential numbers
- **random**: Random values
- **file**: Read from JSON/JSONL files
- **csv**: Read from CSV files
- **csv_watch**: Follow a CSV file as it is written
- **directory_watch**: Emit a message per new file in a directory
- **param_file**: Publish a YAML/JSON job file as parameter messages

### Channels

Channels route messages from sources to destinations:
- **Exact match**: `sensors.temp` matches only `sensors.temp`
- **Single-level wildcard**: `sensors.*` matches `sensors.temp`, `sensors.pressure`
- **Multi-level wildcard**: `sensors.**` matches `sensors.temp`, `sensors.room1.temp`, etc.

### Transformations

Transformations process messages:
- **filter**: Keep messages matching a predicate
- **map**: Transform message values
- **aggregate**: Aggregate messages over tumbling windows
- **unpack**: Explode a dict-valued message into one message per key
- **throttle**: Rate-limit a stream, globally or per key
- **moving_average** / **median_filter**: Sliding-window smoothing, per key
- **deviation_filter**: Reject or clip values that stray from a setpoint
- **alarm** / **relative_alarm**: Threshold and setpoint alarms, emitted on state change only

### Destinations

Destinations consume messages:
- **console**: Print to stdout
- **file**: Write to files
- **inmemory**: Store in memory (for testing)
- **collect**: Collect messages with assertion helpers (for testing)
- **influxdb**: Write time-series points to InfluxDB 2.x

Every parameter of every component is listed in the
[API Reference](api-reference.md#component-type-names).

### Dynamic Parameters

A component parameter can be read from a channel instead of being fixed in the
file, which makes it editable while the pipeline runs:

```yaml
params:
  max_value:
    ref: params.temperature.max
    default: 30.0
```

See [Dynamic parameters](api-reference.md#dynamic-parameters-paramref).

## Using Plugins

Plugins let you add custom components (sources, transformations, destinations) that integrate seamlessly with YAML configuration and the CLI.

### Creating a Plugin

A plugin is a Python module that exports a `register(factory)` function:

```python
# my_plugins.py
from cod3s_data.config.factory import ComponentFactory
from cod3s_data.transformations.base import StatefulTransform
from cod3s_data.core.message import Message

class MyCustomTransform(StatefulTransform):
    async def transform_with_state(self, msg: Message, state: dict) -> Message | None:
        # Your custom logic here
        return msg.with_value(msg.value * 2)

def register(factory: ComponentFactory) -> None:
    factory.register_transformation("my_custom", MyCustomTransform)
```

### Using Plugins in YAML

Declare plugins at the top of your pipeline configuration:

```yaml
name: my_pipeline_with_plugins

plugins:
  - my_plugins

sources:
  - type: sequence
    channel: input
    params:
      start_value: 1
      end_value: 11
      rate: 2.0

transformations:
  - type: my_custom       # Type registered by the plugin
    input_channels: input
    output_channel: output
    params: {}

destinations:
  - type: console
    channel_pattern: output
    params: {}
```

### Using Plugins via CLI

You can also load plugins with the `--plugin` / `-p` flag:

```bash
# Load a plugin at runtime
cod3s-data run my_pipeline.yaml --plugin my_plugins

# Multiple plugins
cod3s-data run my_pipeline.yaml -p my_plugins -p another_plugin

# Validate with plugins (checks that custom types are registered)
cod3s-data validate my_pipeline.yaml --plugin my_plugins
```

### Programmatic Plugin Loading

```python
from cod3s_data.config import PipelineConfig
from cod3s_data.framework import Framework

config = PipelineConfig(
    plugins=["my_plugins"],
    sources=[...],
    destinations=[...],
)

# Plugins are loaded automatically when the Framework starts
async with Framework(config) as framework:
    await framework.run()

# Or pass extra plugins via the constructor
async with Framework(config, plugins=["another_plugin"]) as framework:
    await framework.run()
```

## Common Patterns

### Multi-Sensor Monitoring

```yaml
name: multi_sensor

sources:
  - type: random
    channel: sensors.temperature
    params: {rate: 10.0, min_value: 20.0, max_value: 30.0}

  - type: random
    channel: sensors.pressure
    params: {rate: 10.0, min_value: 1000.0, max_value: 1030.0}

destinations:
  - type: console
    channel_pattern: sensors.**
    params: {}
```

### Data Aggregation

```yaml
transformations:
  - type: aggregate
    input_channels: sensor.data
    output_channel: stats.average
    params:
      window_type: count
      window_size: 10
      aggregation_fn_code: "lambda msgs: sum(m.value for m in msgs) / len(msgs)"
```

### Chained Transformations

```yaml
transformations:
  # Step 1: Filter
  - type: filter
    input_channels: raw
    output_channel: filtered
    params:
      predicate_code: "lambda msg: msg.value > 0"

  # Step 2: Transform
  - type: map
    input_channels: filtered
    output_channel: transformed
    params:
      map_fn_code: "lambda x: x * 2"
```

## Validating Configuration

Before running, validate your configuration:

```bash
cod3s-data validate my_pipeline.yaml
```

This checks:
- YAML syntax
- Required fields
- Type validation
- Configuration structure

## Command-Line Options

### Run Command

```bash
cod3s-data run [OPTIONS] CONFIG_FILE

Options:
  --log-level LEVEL        Logging level (DEBUG, INFO, WARNING, ERROR)
  --json-logs              Output logs in JSON format
  -p, --plugin MODULE      Plugin module path to load (repeatable)
  -v, --verbose            Show stack traces on error
  --observatory            Enable Observatory web UI for debugging and monitoring
  --observatory-port PORT  Observatory server port (default: 8765)
  --interactive            Start in interactive mode (pipeline waits for UI to start it; implies --observatory)
```

### Validate Command

```bash
cod3s-data validate [OPTIONS] CONFIG_FILE

Options:
  -p, --plugin MODULE   Plugin module path to load (repeatable)
  -v, --verbose         Show stack traces on error
```

## Next Steps

- Explore [Example Pipelines](../examples/)
- Read the [API Reference](api-reference.md)
- Write your own components with the [plugin system](api-reference.md#writing-a-plugin)

## Getting Help

- GitHub Issues: [Report bugs or request features](https://github.com/yourusername/cod3s-data/issues)
- Documentation: Full docs at [cod3s-data.readthedocs.io](https://cod3s-data.readthedocs.io)
