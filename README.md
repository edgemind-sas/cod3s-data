# COD3S Data Framework v1.0

A lightweight, flexible data streaming framework for real-time processing of temporal sensor data.

## Overview

COD3S Data is an AsyncIO-based pub/sub framework designed for real-time sensor data processing, with a primary focus on 3D printer monitoring and similar IoT applications.

**Key Features:**
- 🚀 **High Performance**: 10,000+ msg/s end to end (the perf suite measures 50-100k on a dev machine)
- 🔄 **Flexible Pub/Sub**: In-memory broker with wildcard channel subscriptions
- 📊 **Rich Data Sources**: Random, sequence, JSON/JSONL, CSV, tailed CSV, and directory watching
- 🧮 **Signal Processing**: Sliding-window smoothing, median filtering, deviation filtering, threshold and setpoint alarms
- 🎛️ **Dynamic Parameters**: Setpoints and tolerances sourced from a channel and editable while the pipeline runs
- 💾 **Time-Series Storage**: InfluxDB 2.x destination
- 🔭 **Observatory**: Web UI for live topology, message inspection, metrics and parameters
- 🔌 **Extensible**: Easy-to-implement custom sources, transformations, and destinations
- ⚙️ **Multiple Configuration Options**: YAML, Python API, and environment variables
- 📈 **Built-in Observability**: Structured logging with structlog, metrics as messages

## Quick Start

### Installation

```bash
pip install cod3s-data

# Optional extras
pip install 'cod3s-data[observatory]'  # Web UI (FastAPI + WebSocket)
pip install 'cod3s-data[influxdb]'     # InfluxDB 2.x destination
```

### Simple Example (Python API)

```python
import asyncio
from cod3s_data.config import PipelineConfig, SourceConfig, DestinationConfig
from cod3s_data.framework import Framework

async def main():
    config = PipelineConfig(
        name="simple_pipeline",
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

### YAML Configuration

```yaml
name: simple_pipeline

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

Run with CLI:
```bash
cod3s-data run pipeline.yaml
```

Or validate before running:
```bash
cod3s-data validate pipeline.yaml
```

## Architecture

```
┌──────────────┐      ┌──────────┐      ┌──────────────┐
│   Sources    │─────>│  Broker  │─────>│ Destinations │
│              │      │(In-Mem)  │      │              │
│ -Random      │      │          │      │ -Console     │
│ -Sequence    │      │ Pub/Sub  │      │ -File        │
│ -File / CSV  │      │ Channels │      │ -InMemory    │
│ -Watchers    │      │ Wildcards│      │ -InfluxDB    │
│ -ParamFile   │      │          │      │              │
└──────────────┘      └────┬─────┘      └──────────────┘
                           │
                  ┌────────▼────────┐        ┌─────────────┐
                  │Transformations  │<───────│ Observatory │
                  │                 │  params│  (Web UI)   │
                  │ -Stateless      │───────>│             │
                  │ -Stateful       │  events└─────────────┘
                  └─────────────────┘
```

## Components

Every component below is reachable from YAML through its `type:` name — see the
[full table](docs/api-reference.md#component-type-names).

### Sources
- **RandomSource** (`random`): Generate random values for testing
- **SequenceSource** (`sequence`): Emit sequential numbers
- **FileSource** (`file`): Read from JSON/JSONL files
- **CSVSource** (`csv`): Read from CSV with polars — column mapping, replay, epoch timestamps
- **CSVWatchSource** (`csv_watch`): Follow a CSV file that is still being written
- **DirectoryWatchSource** (`directory_watch`): Emit a message per new file in a directory
- **ParamFileSource** (`param_file`): Publish a YAML/JSON job file as parameter messages

### Destinations
- **ConsoleDestination** (`console`): Print to stdout/stderr
- **FileDestination** (`file`): Write to JSON/JSONL files
- **InMemoryDestination** (`inmemory`): Store in memory (for testing)
- **CollectDestination** (`collect`): Collect with assertion helpers (for testing)
- **InfluxDBDestination** (`influxdb`): Write time-series points to InfluxDB 2.x

### Transformations
- **FilterTransform** (`filter`): Filter messages by predicate
- **MapTransform** (`map`): Transform message values
- **AggregateTransform** (`aggregate`): Tumbling time/count window aggregations
- **UnpackTransform** (`unpack`): Explode a dict-valued message into one message per key
- **ThrottleTransform** (`throttle`): Rate-limit a stream, globally or per key
- **MovingAverageTransform** (`moving_average`): Sliding-window mean, per key
- **MedianFilterTransform** (`median_filter`): Sliding-window median, per key
- **DeviationFilterTransform** (`deviation_filter`): Reject or clip values off a setpoint
- **AlarmTransform** (`alarm`): Fixed min/max thresholds, emits on transitions only
- **RelativeAlarmTransform** (`relative_alarm`): Deviation from a setpoint, per-key state

### Observatory

An optional web UI for watching a running pipeline: live topology, message
inspector with per-message journey, metrics, and a Parameters page that edits
`ParamRef` values in place.

```bash
pip install -e ".[observatory]"
```

Enable it on a pipeline and open <http://localhost:8765>.

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/cod3s/cod3s-data.git
cd cod3s-data

# Install with dev dependencies
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=cod3s_data --cov-report=html

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
pytest tests/performance/
```

### Code Quality

```bash
# Type checking
mypy cod3s_data/

# Linting
ruff check .

# Formatting
ruff format .
```

## CLI Usage

COD3S Data includes a command-line interface:

```bash
# Run a pipeline
cod3s-data run pipeline.yaml

# Validate configuration
cod3s-data validate pipeline.yaml

# With options
cod3s-data run pipeline.yaml --log-level DEBUG --json-logs
```

## Docker Support

Build and run with Docker:

```bash
# Build image
docker build -t cod3s-data .

# Run pipeline
docker run -v $(pwd)/examples:/app/pipelines cod3s-data run /app/pipelines/simple_pipeline.yaml
```

## Performance

Measured by `tests/performance/` on a developer machine — reproduce with
`pytest tests/performance -s`:

- **Broker latency**: 0.28ms p50, 0.49ms p95, 0.57ms p99 (target: <50ms)
- **End-to-end throughput**: 50,000-140,000 msg/s through source → broker → destination
- **Transformation overhead**: ~50% for one map transform, which is one extra broker hop per message
- **Memory**: history buffers are bounded by `history_size`; a 10,000-message run stays flat

Numbers vary with the machine. What the suite guards is the order of magnitude
and the absence of regressions, not an absolute figure.

**Test suite**: 519 tests passing, 83% coverage.

## Documentation

See the [docs/](docs/) directory for:
- Installation guide
- API reference
- Configuration examples
- Performance tuning

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please see CONTRIBUTING.md for guidelines.

## Support

For issues and questions:
- GitHub Issues: https://github.com/cod3s/cod3s-data/issues
- Documentation: https://cod3s-data.readthedocs.io/
