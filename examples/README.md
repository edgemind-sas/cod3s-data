# COD3S Data Framework - Examples

This directory contains example pipelines demonstrating the COD3S Data Framework capabilities.

## Running Examples

Python examples run directly:

```bash
uv run python examples/simple_pipeline.py
uv run python examples/sensor_monitoring.py
uv run python examples/data_transformation.py
uv run python examples/observatory_demo.py
```

YAML pipelines run through the CLI:

```bash
uv run cod3s-data validate examples/simple_pipeline.yaml
uv run cod3s-data run examples/simple_pipeline.yaml
uv run cod3s-data run examples/sensor_pipeline.yaml
uv run cod3s-data run examples/print_job_dynamic.yaml --observatory
```

## Python Examples

### 1. Simple Pipeline (`simple_pipeline.py`)

**Concepts demonstrated:**
- Basic pipeline creation
- Sequence source
- Console destination
- Async context manager usage

**What it does:**
Generates numbers 1-10 at 2 messages per second and prints them to the console.

**Run time:** ~5 seconds

### 2. Sensor Monitoring (`sensor_monitoring.py`)

**Concepts demonstrated:**
- Multiple sources
- Random data generation
- Wildcard channel patterns
- Filter transformations
- Aggregate transformations
- Multiple destinations
- Metrics collection

**What it does:**
Simulates real-time sensor monitoring for temperature and pressure:
- Generates random sensor readings at 10 Hz
- Alerts on high temperature (>28°C)
- Calculates rolling averages
- Collects and displays pipeline metrics

**Run time:** ~10 seconds

### 3. Data Transformation (`data_transformation.py`)

**Concepts demonstrated:**
- Chained transformations
- Filter transformation
- Map transformation
- Aggregate transformation
- Multiple destinations subscribing to different channels
- Result verification

**What it does:**
Processes numbers 1-100 through a transformation pipeline:
1. **Filter:** Keep only even numbers
2. **Map:** Square each number
3. **Aggregate:** Sum every 5 values

**Run time:** ~2 seconds

### 4. Observatory Demo (`observatory_demo.py`)

**Concepts demonstrated:**
- Running a pipeline with the Observatory enabled
- `ObservatoryConfig` from the Python API
- Querying the REST API while the pipeline runs
- Reading the event buffer

**What it does:**
Runs a small pipeline with the web UI attached. Open
<http://127.0.0.1:8765> while it runs, or query it:

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/topology
```

Needs the extra: `pip install 'cod3s-data[observatory]'`. See
[Observatory](../docs/observatory.md).

## YAML Pipelines

### 5. Simple Pipeline (`simple_pipeline.yaml`)

The YAML counterpart of `simple_pipeline.py`: a sequence source, a console
destination, and a `broker:` section. The place to start when moving from the
Python API to configuration files.

### 6. Sensor Pipeline (`sensor_pipeline.yaml`)

**Concepts demonstrated:**
- Two sources on distinct channels
- Wildcard subscriptions (`sensors.temperature.**`)
- `alarm` transformation on a threshold, firing only on state change
- Two `aggregate` transformations with an inline `aggregation_fn_code`
- Three console destinations partitioning the output by channel
- `label` on every component, so the Observatory topology reads clearly

Runs for about ten seconds (`max_messages: 100` at 10 Hz).

### 7. Dynamic Print Job (`print_job_dynamic.yaml` + `jobs/PLA.yaml`)

**Concepts demonstrated:**
- The [`ParamRef`](../docs/api-reference.md#dynamic-parameters-paramref) mechanism
- `param_file` source loading a job file into `params.**`
- `relative_alarm` with a setpoint and tolerance bound to channels
- `display_name` / `subtitle` for the Observatory header
- Editing a setpoint while the pipeline runs

Setpoints come from `jobs/PLA.yaml`, published at start. Change one mid-run:

```bash
uv run cod3s-data run examples/print_job_dynamic.yaml --observatory

curl -X POST http://localhost:8765/api/params/params.alarm.extruder.setpoint \
     -H 'Content-Type: application/json' -d '{"value": 215}'
```

The alarm re-evaluates against the new setpoint on the next message, with no
restart. The Observatory's Parameters page does the same thing from the UI.

## Key Concepts

### Sources

- **SequenceSource** (`sequence`): Sequential numbers
- **RandomSource** (`random`): Random values within a range
- **ParamFileSource** (`param_file`): A YAML job file, published as parameters

### Transformations

- **FilterTransform** (`filter`): Filter messages by predicate
- **MapTransform** (`map`): Transform message values
- **AggregateTransform** (`aggregate`): Aggregate over tumbling windows
- **AlarmTransform** (`alarm`): Fixed thresholds, emitted on state change
- **RelativeAlarmTransform** (`relative_alarm`): Deviation from a setpoint

The full catalogue is in the
[API reference](../docs/api-reference.md#component-type-names).

### Destinations

- **ConsoleDestination** (`console`): Print messages to stdout
- **InMemoryDestination** (`inmemory`): Store messages in memory for analysis

### Configuration

The `.py` examples build a `PipelineConfig` programmatically; the `.yaml` ones
are loaded by the CLI. Both produce the same pipeline — see
[Configuration](../docs/api-reference.md#configuration).

## Next Steps

- Read the [API reference](../docs/api-reference.md) for the full component set
- Try modifying the examples to experiment with different configurations
- Create your own components with the [plugin system](../docs/api-reference.md#writing-a-plugin)
- Check out the integration tests for more complex pipeline scenarios
