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
uv run cod3s-data run examples/print_job_incident.yaml
uv run cod3s-data run examples/cold_chain_round.yaml
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

## Scenario Demos

The pipelines above demonstrate mechanisms with `random` or `sequence` sources.
These two demonstrate *situations*: the data is fictional but scripted, replayed
from a CSV, and the numbers describe an incident an operator would recognise.
Nothing is random — the same run produces the same story every time.

The datasets live in `data/`, alongside the script that produced each one.
Regenerate either with `uv run python examples/data/generate_<name>.py`.

### 8. A 3D print that goes wrong (`print_job_incident.yaml`)

**What happens:** twenty minutes of a PLA job, replayed at 60× — the demo lasts
about twenty seconds. The nozzle heats to 210 °C, prints, then a partial clog
drags it down to 197 °C over three minutes; meanwhile the workshop door is
opened and a draft cools the bed. The operator purges the nozzle and both
recover.

**What it demonstrates:** why a smoothed signal is worth having. A thermocouple
on a moving hotend is genuinely noisy, and that noise makes the alarm chatter
each time the signal crosses the threshold. The pipeline runs the same alarm
twice — once on the raw signal, once on a 30-second moving average — and prints
both:

```bash
uv run cod3s-data run examples/print_job_incident.yaml | grep -c "'alarm_type': 'brut'"   # 70
uv run cod3s-data run examples/print_job_incident.yaml | grep -c "'alarm_type': 'lisse'"  # 8
```

Seventy alarms against eight, on the same incident. The eight read as the
story: both sensors start in alarm because the printer is cold, clear as they
reach temperature, fire again for the clog and the draft, and clear once more.

### 9. A cold chain, and a compliance log that cannot be written (`cold_chain_round.yaml`)

**What happens:** one hour of a refrigerated van's round, three compartments,
replayed at 120×. At a delivery stop the chilled compartment is left open for
eight minutes and reaches 16 °C. The two frozen compartments never leave their
range.

**What it demonstrates:** two things.

One alarm transformation covers all three compartments — `setpoint` takes a
dict keyed by compartment, and state is tracked per key, so one compartment
going out of range says nothing about the others.

And the compliance log is written to a network mount that does not exist, so
the alarms cannot be archived. They land on the dead-letter channel carrying
the reason:

```
dlq_destination        FileDestination
dlq_error_type         FileNotFoundError
dlq_error              [Errno 2] No such file or directory: '/mnt/qualite-nfs/…'
dlq_attempts           2
dlq_component_id       dst-0
```

The original `cargo` tag is still there. Without those `dlq_*` tags the message
would arrive on the dead-letter channel indistinguishable from ordinary
traffic — which is what it used to do.

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
