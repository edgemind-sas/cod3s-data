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

### Channels

Channels route messages from sources to destinations:
- **Exact match**: `sensors.temp` matches only `sensors.temp`
- **Single-level wildcard**: `sensors.*` matches `sensors.temp`, `sensors.pressure`
- **Multi-level wildcard**: `sensors.**` matches `sensors.temp`, `sensors.room1.temp`, etc.

### Transformations

Transformations process messages:
- **filter**: Keep messages matching a predicate
- **map**: Transform message values
- **aggregate**: Aggregate messages over windows

### Destinations

Destinations consume messages:
- **console**: Print to stdout
- **file**: Write to files
- **inmemory**: Store in memory (for testing)

## Common Patterns

### Multi-Sensor Monitoring

```yaml
name: multi_sensor

sources:
  - type: random
    channel: sensors.temperature
    params: {rate: 10.0, value_min: 20.0, value_max: 30.0}

  - type: random
    channel: sensors.pressure
    params: {rate: 10.0, value_min: 1000.0, value_max: 1030.0}

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
  --log-level LEVEL     Logging level (DEBUG, INFO, WARNING, ERROR)
  --json-logs           Output logs in JSON format
  -v, --verbose         Show stack traces on error
```

### Validate Command

```bash
cod3s-data validate [OPTIONS] CONFIG_FILE

Options:
  -v, --verbose         Show stack traces on error
```

## Next Steps

- Explore [Example Pipelines](../examples/)
- Read the [API Reference](api-reference.md)
- Learn about [Custom Components](custom-components.md)
- Check out [Best Practices](best-practices.md)

## Getting Help

- GitHub Issues: [Report bugs or request features](https://github.com/yourusername/cod3s-data/issues)
- Documentation: Full docs at [cod3s-data.readthedocs.io](https://cod3s-data.readthedocs.io)
