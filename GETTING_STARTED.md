# Getting started

Recipes for the problems this framework was built for. Each one is a complete,
runnable pipeline you can paste into a file and run with:

```bash
uv run cod3s-data validate pipeline.yaml   # check it first
uv run cod3s-data run pipeline.yaml
```

If you have not written a pipeline before, read
[docs/quickstart.md](docs/quickstart.md) first — it explains sources, channels,
transformations and destinations. This page assumes you know what those are and
shows how to combine them. Every parameter used here is described in the
[API reference](docs/api-reference.md).

---

## Follow a file that is still being written

A machine appends telemetry to a CSV while it runs. `csv_watch` reads what is
already there, then polls for new lines.

```yaml
name: follow_telemetry

sources:
  - type: csv_watch
    channel: telemetry.raw
    params:
      file_path: /var/log/printer/telemetry.csv
      poll_interval: 0.5
      timestamp_column: time
      value_columns: [extruder, bed, chamber]
      tag_columns: [printer_id]

destinations:
  - type: console
    channel_pattern: telemetry.raw
    params: {}
```

With `value_columns`, each row becomes **one** message whose value is a dict:
`{"extruder": 211.4, "bed": 60.1, "chamber": 32.0}`.

For a file that is complete before the pipeline starts, use `csv` instead. It
reads through polars and supports replay:

```yaml
sources:
  - type: csv
    channel: telemetry.raw
    params:
      file_path: history.csv
      value_columns: [extruder, bed]
      replay: true          # honour the gaps between timestamps
      speed_factor: 10.0    # ten times faster than real time
```

`replay` is how you re-run a past session at a chosen speed against the same
pipeline you use live.

---

## Split one wide row into per-sensor channels

Most transformations work on a numeric value, not a dict. `unpack` explodes a
dict-valued message into one message per key, each on its own sub-channel
`{output_channel}.{key}`.

```yaml
name: split_sensors

sources:
  - type: csv_watch
    channel: telemetry.raw
    params:
      file_path: telemetry.csv
      value_columns: [extruder, bed]

transformations:
  - type: unpack
    input_channels: telemetry.raw
    output_channel: sensors

destinations:
  - type: console
    channel_pattern: sensors.*
    params: {}
```

`{"extruder": 211.4, "bed": 60.1}` on `telemetry.raw` becomes `211.4` on
`sensors.extruder` and `60.1` on `sensors.bed`. Everything downstream can now
subscribe to `sensors.*` and be handed one number at a time, with
`message.key` naming the sensor.

---

## Smooth a noisy signal

`moving_average` keeps a sliding window **per key**, so a single transform on a
wildcard handles every sensor independently.

```yaml
transformations:
  - type: moving_average
    input_channels: sensors.*
    output_channel: sensors.smoothed
    params:
      window_type: count
      window_size: 10
      min_samples: 3
      key_suffix: _avg
```

`min_samples` suppresses output until the window has enough data, so the first
few readings do not produce a misleading average.

`key_suffix` matters more than it looks. Without it the smoothed message keeps
the raw key and lands on `sensors.smoothed`; with it the key becomes
`extruder_avg` and the message is published on `sensors.smoothed.extruder_avg`.
That is what lets a smoothed signal coexist with its raw counterpart in a sink
that keys by `message.key` — InfluxDB, for instance, where both would otherwise
write to the same measurement.

Use `median_filter` with the same parameters when the noise is isolated spikes
rather than jitter: the median ignores an outlier that the mean would absorb.

---

## Alarm on a threshold

`alarm` emits only on **state transitions**, so a value that stays out of range
produces one message, not one per sample.

```yaml
transformations:
  - type: alarm
    input_channels: sensors.extruder
    output_channel: alarms
    params:
      min_value: 190.0
      max_value: 230.0
```

The output message has key `sensors.extruder.alarm` and a dict value carrying
`original_value`, `alarm_type` (`min` or `max`), `threshold`, and `status` —
`ACTIVE` on entry, `CLEARED` on return to range.

---

## Alarm on a setpoint you can change while it runs

A fixed threshold is wrong the moment the job changes. `relative_alarm` watches
the deviation from a setpoint, and the setpoint can come from a channel rather
than from the file.

Put the job's setpoints in their own file:

```yaml
# jobs/PLA.yaml
alarm:
  extruder:
    setpoint: 210.0
    tolerance: 5.0
  bed:
    setpoint: 60.0
    tolerance: 3.0
```

`param_file` publishes each leaf on `params.<path>`, and any component
parameter can reference one:

```yaml
name: dynamic_alarms

sources:
  - type: param_file
    channel: params
    params:
      file_path: jobs/PLA.yaml

  - type: random
    channel: sensors.extruder
    params:
      rate: 5.0
      min_value: 195.0
      max_value: 225.0

transformations:
  - type: relative_alarm
    input_channels: sensors.extruder
    output_channel: alarms
    params:
      setpoint:
        ref: params.alarm.extruder.setpoint
        default: 200.0
      tolerance_abs:
        ref: params.alarm.extruder.tolerance
        default: 5.0

destinations:
  - type: console
    channel_pattern: alarms
    params: {}
```

`default` is what the transform uses until the first message arrives on `ref`.
Since `param_file` publishes at start and the parameter store also reads the
channel history when it starts, the real value is bound before the first sensor
reading is processed.

Run it with the Observatory and change a setpoint mid-run:

```bash
uv run cod3s-data run pipeline.yaml --observatory

curl -X POST http://localhost:8765/api/params/params.alarm.extruder.setpoint \
     -H 'Content-Type: application/json' -d '{"value": 215}'
```

The alarm re-evaluates against 215 on the next message. No restart, no reload.
The Observatory's Parameters page does the same thing from a browser. See
[Dynamic parameters](docs/api-reference.md#dynamic-parameters-paramref).

Switching jobs means pointing `param_file` at another file — `jobs/PETG.yaml`
instead of `jobs/PLA.yaml` — with the pipeline itself unchanged.

---

## Reject or clip bad readings

A sensor that briefly reports nonsense will trip every alarm downstream.
`deviation_filter` drops or clamps readings outside a band before they get
that far.

```yaml
transformations:
  - type: deviation_filter
    input_channels: sensors.*
    output_channel: sensors.clean
    params:
      setpoint:
        extruder: 210.0
        bed: 60.0
      tolerance_pct: 20.0
      mode: reject          # or "clip"
```

`reject` drops the message; `clip` clamps it into the band. A key with no
setpoint passes through untouched, as does any non-numeric value.

Note the difference from `relative_alarm`: this one filters the data stream,
that one reports on it. They are often used together, with a wide band here and
a narrow one there.

---

## Write to InfluxDB

```bash
pip install 'cod3s-data[influxdb]'
docker compose -f docker-compose.influxdb.yml up -d   # a local server
```

```yaml
destinations:
  - type: influxdb
    channel_pattern: sensors.**
    params:
      url: http://localhost:8086
      token: my-token
      org: cod3s
      bucket: sensor_data
      extra_tags:
        printer: printer-1
      batch_size: 100
```

`message.key` becomes the measurement, `message.tags` merged with `extra_tags`
become the tags, and the value becomes the fields — one per entry for a dict,
a single `value` field otherwise.

Two things bite here. InfluxDB rejects a field whose type changes between
points, so keep a measurement's fields stable. And a high-rate pipeline will
write far more points than you need:

```yaml
transformations:
  - type: throttle
    input_channels: sensors.*
    output_channel: sensors.sampled
    params:
      interval: 0.1
      per_key: true
```

`per_key: true` gives each sensor its own clock. Without it a single shared
clock lets the busiest channel consume the budget and starve the others.

---

## React to new files in a directory

```yaml
name: watch_jobs

sources:
  - type: directory_watch
    channel: jobs.incoming
    params:
      directory: /var/spool/gcode
      glob_pattern: "*.gcode"
      poll_interval: 2.0
      emit_existing: false

destinations:
  - type: console
    channel_pattern: jobs.incoming
    params: {}
```

One message per new file. Detection is by filename, compared between polls, so
a file that is rewritten under the same name is not re-emitted.
`emit_existing: true` also emits whatever is already there at startup.

---

## Put it together

The chain the pieces above are meant to form:

```yaml
name: printer_monitoring
display_name: Printer monitoring
subtitle: Line 3

broker:
  enable_metrics: true
  history_size: 1000

sources:
  - type: param_file
    label: Job setpoints
    channel: params
    params:
      file_path: jobs/PLA.yaml

  - type: csv_watch
    label: Telemetry
    channel: telemetry.raw
    params:
      file_path: telemetry.csv
      poll_interval: 0.5
      value_columns: [extruder, bed]

transformations:
  - type: unpack
    label: Split sensors
    input_channels: telemetry.raw
    output_channel: sensors

  - type: median_filter
    label: Despike
    input_channels: sensors.*
    output_channel: sensors.clean
    params:
      window_size: 5
      min_samples: 3
      key_suffix: _med

  - type: relative_alarm
    label: Extruder alarm
    input_channels: sensors.clean.extruder_med
    output_channel: alarms
    params:
      setpoint:
        ref: params.alarm.extruder.setpoint
        default: 210.0
      tolerance_abs:
        ref: params.alarm.extruder.tolerance
        default: 5.0

  - type: throttle
    label: Downsample for storage
    input_channels: sensors.clean.*
    output_channel: sensors.sampled
    params:
      interval: 0.1
      per_key: true

destinations:
  - type: console
    label: Alarms
    channel_pattern: alarms
    params: {}

  - type: file
    label: Alarm log
    channel_pattern: alarms
    params:
      file_path: alarms.jsonl
      batch_size: 10
```

Note how the channels chain: `telemetry.raw` → `sensors.*` → `sensors.clean.*`
→ one branch to the alarm, one to storage. The `label` on each component is
what the Observatory topology shows instead of `tfm-2`.

---

## Add a component of your own

Subclass the relevant base and expose a `register(factory)` function:

```python
# my_plugin.py
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from cod3s_data.core.message import Message
from cod3s_data.sources.base import Source


class ModbusSource(Source):
    """Poll a Modbus register."""

    def __init__(self, broker, channel, *, unit: int, register: int, **kwargs):
        super().__init__(broker, channel, **kwargs)
        self.unit = unit
        self.register = register

    async def produce(self) -> AsyncIterator[Message]:
        while self._running:
            value = await self._read_register()
            yield Message(
                key="modbus",
                timestamp=datetime.now(UTC),
                value=value,
                tags={"unit": str(self.unit)},
            )


def register(factory):
    factory.register_source("modbus", ModbusSource)
```

Load it by module path, from the CLI or from the pipeline file:

```bash
uv run cod3s-data run pipeline.yaml -p my_plugin
```

```yaml
plugins:
  - my_plugin

sources:
  - type: modbus
    channel: sensors.modbus
    params:
      unit: 1
      register: 40001
```

> Pick a type name the built-ins do not already use: a plugin is loaded after
> them and would override one silently. `mqtt`, for instance, is a built-in
> source *and* destination.

A plugin's components use the same registry as the built-ins, so they get
`ParamRef`, the Observatory, metrics and the DLQ for free. See
[Writing a plugin](docs/api-reference.md#writing-a-plugin).

---

## When something does not work

**Validate before running.** Most mistakes are configuration mistakes, and
`validate` reports them without starting anything:

```bash
uv run cod3s-data run pipeline.yaml --log-level DEBUG -v
```

**Check what is actually on the channels.** Every pipeline publishes its own
metrics as messages; subscribe to them:

```yaml
destinations:
  - type: console
    channel_pattern: _metrics.**
    params: {}
```

**Watch it.** The [Observatory](docs/observatory.md) shows the topology, the
messages in flight and their journey through the pipeline, and lets you pause
and step:

```bash
uv run cod3s-data run pipeline.yaml --observatory
```

**Capture messages in a test.** `inmemory` and `collect` destinations keep
messages in the process instead of writing them out:

```yaml
destinations:
  - type: collect
    channel_pattern: alarms
    params: {}
```

```python
dest = framework.destinations[0]
await dest.wait_for_messages(count=3, timeout=5.0)
dest.assert_count(3)
```

**Nothing arrives at a destination.** Check the channel pattern against what is
actually published. `sensors.*` matches one level, `sensors.**` matches any
depth — and transformations like `unpack` and `moving_average` with a
`key_suffix` publish one level deeper than their `output_channel` suggests.

---

## Going further

- [API reference](docs/api-reference.md) — every component and parameter
- [Observatory](docs/observatory.md) — the UI, its REST and WebSocket APIs
- [Examples](examples/README.md) — seven runnable pipelines
- Error handling, retries and dead-letter queues:
  [Error handling](docs/api-reference.md#error-handling)
- Buffer sizes, history limits, batch sizes:
  [Performance tuning](docs/api-reference.md#performance-tuning)
