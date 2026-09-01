# Observatory

The Observatory is an optional web UI for watching a pipeline while it runs: live
topology, message inspection, metrics, debug controls, and live editing of
[dynamic parameters](api-reference.md#dynamic-parameters-paramref).

It ships as an extra, because it pulls in FastAPI and uvicorn:

```bash
pip install 'cod3s-data[observatory]'
```

Enabling it without the extra raises `ImportError` with the install command.

## Enabling it

From the CLI:

```bash
cod3s-data run pipeline.yaml --observatory
cod3s-data run pipeline.yaml --observatory --observatory-port 9000
cod3s-data run pipeline.yaml --interactive     # implies --observatory
```

From the Python API:

```python
from cod3s_data.framework import Framework
from cod3s_data.observatory.config import ObservatoryConfig

# Defaults, or whatever the config's `observatory:` section says
framework = Framework(config, observatory=True)

# Explicit settings, ignoring the `observatory:` section
framework = Framework(config, observatory=ObservatoryConfig(port=9000))
```

Then open <http://localhost:8765>.

`observatory=True` reads the pipeline's `observatory:` section when there is one
and falls back to defaults otherwise. Passing an `ObservatoryConfig` instance
overrides the section entirely.

## Interactive mode

With `interactive: true` (or `--interactive`), the pipeline is built but not
started: it waits for the UI to start it. Use it to attach a debugger, arm
breakpoints, or watch the first messages of a short pipeline that would
otherwise finish before the browser connects.

The UI drives the lifecycle through the `pipeline.start`, `pipeline.stop` and
`pipeline.restart` [WebSocket commands](#client-to-server-commands).

## Pages

| Path | Page | What it shows |
|---|---|---|
| `/topology` | Pipeline Topology | Components as nodes, subscriptions as edges, animated by message rate |
| `/timeline` | Temporal Timeline | Messages over time, per channel |
| `/messages` | Message Inspector | One message in full: value, tags, raw JSON, and its journey through the pipeline |
| `/parameters` | Pipeline Parameters | Every `ParamRef` in the pipeline, with its current value, editable in place |
| `/metrics` | Metrics Dashboard | The `_metrics.**` stream, charted |
| `/debug` | Debug Controls | Pause, resume, step, slow motion, breakpoints |

The component labels shown in the UI come from the `label` and `description`
fields of each component's configuration, and the header from the pipeline's
`display_name` and `subtitle` — see
[Pipeline display metadata](api-reference.md#pipeline-display-metadata).

### Which clock the Observatory shows

A message carries two times, and they answer different questions:

- **when the pipeline published it** — the Observatory's own clock;
- **when the reading was taken** — `Message.timestamp`, set by the source.

The Observatory is a debugging view of the architecture, so every page is on
the first: the Timeline axis, the Messages table, the journey steps, and the
Inspector's *Published* row. The source's time is what InfluxDB and Grafana
index on, and it stays visible in the Inspector as *Source timestamp*, with the
gap called out when the two disagree by more than a second.

They coincide on a live pipeline. They diverge whenever a recorded session is
replayed with its original timestamps, and a gap on a live pipeline means the
source's clock has drifted from the host's — which is worth seeing.

## Configuration

The `observatory:` section of a pipeline file:

```yaml
name: my_pipeline
display_name: Extruder monitoring
subtitle: Line 3, PLA job

observatory:
  enabled: true
  host: 127.0.0.1
  port: 8765
  history_size: 500
  memory_limit_mb: 50
  interactive: false
  debug:
    enabled: false
    granularity: message
    auto_pause: false
  sampling:
    strategy: none
    rate: 1
    interval_ms: 100

sources: []
destinations: []
```

**Fields:**

| Field | Type | Default | Constraint |
|---|---|---|---|
| `enabled` | bool | `true` | |
| `host` | str | `127.0.0.1` | **only** `127.0.0.1` or `localhost` in v1 |
| `port` | int | `8765` | 1024–65535 |
| `history_size` | int | `500` | 50–100000 — messages the Observatory remembers |
| `buffer_size` | int | unset | 100–100000 — overrides `history_size` for the ring buffer |
| `message_detail_cache_size` | int | unset | 50–5000 — overrides `history_size` for the Inspector |
| `memory_limit_mb` | int | `50` | 10–500 — cap on the event buffer |
| `interactive` | bool | `false` | Wait for the UI before starting the pipeline |
| `debug.enabled` | bool | `false` | Enables the `/debug` page and the `debug.*` commands |
| `debug.granularity` | str | `message` | `message`, `stage` or `breakpoint` |
| `debug.auto_pause` | bool | `false` | Pause as soon as the pipeline starts |
| `sampling.strategy` | str | `none` | `none`, `every_nth` or `time_based` |
| `sampling.rate` | int | `1` | 1–10000 — keep 1 message in N, for `every_nth` |
| `sampling.interval_ms` | int | `100` | 10–10000 — minimum gap, for `time_based` |

`history_size` is the single retention knob, and the UI follows it: the client
keeps exactly as many rows as the server can still describe, so every listed
message can be opened. Raising it costs memory on the process running the
pipeline — the Inspector holds a full copy of each message, and its journey.
The two overrides exist for a pipeline that wants to *list* far more than it
can inspect; leave them unset unless you have measured the need, because a row
listed beyond `message_detail_cache_size` answers "no longer available" when
clicked.

Sampling only affects what the Observatory observes. It never drops a message
from the pipeline itself. Turn it on when a pipeline publishes faster than the
UI can render. Note that it applies to publications only: receptions and
processing steps are always recorded, so a sampled run produces journeys whose
publications are missing.

> `host` is validated to localhost on purpose: the Observatory has no
> authentication. To reach it from another machine, forward the port over SSH
> rather than binding a public interface.

## Environment variables

Every Observatory setting can be overridden by a `COD3S_OBSERVATORY_*` variable
at load time — see the full table in
[Environment variables](api-reference.md#environment-variables).

Two things specific to the Observatory: the `observatory:` section is created
for you if a variable is set on a pipeline file that has none, and
`message_detail_cache_size` is the one field with no variable — set it in the
file, or use `COD3S_OBSERVATORY_HISTORY_SIZE`, which drives it.

```bash
COD3S_OBSERVATORY_PORT=9000 COD3S_OBSERVATORY_DEBUG=true \
  cod3s-data run pipeline.yaml --observatory
```

## REST API

All endpoints are under `/api`, served by the same process as the pipeline.

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "1.0.0",
  "buffer_size": 412,
  "buffer_memory_mb": 1.87,
  "connected_clients": 1,
  "pipeline_state": "running"
}
```

`pipeline_state` is a [`PipelineState`](api-reference.md#pipeline-state) value,
or `"unknown"` when no framework is attached.

### `GET /api/topology`

Nodes and edges, rebuilt from the buffered component-state and subscription
events.

```json
{
  "nodes": [{"id": "src-0", "type": "source", "state": "running"}],
  "edges": [{"pattern": "sensors.**", "subscriber_id": "b1f0c9de-…"}]
}
```

`subscriber_id` is the broker's subscription handle, not a component id, and
nodes carry no label — the UI uses the richer `connected` WebSocket snapshot
instead, which resolves both from the live pipeline.

### `GET /api/components/{component_id}`

One node from the same data, by id (`src-0`, `tfm-1`, `dst-0`, …). `404` when
the id is unknown.

### `GET /api/channels/{channel_name}/history`

Recent messages seen on a channel. `limit` defaults to 50, capped at 1000.

```bash
curl 'http://localhost:8765/api/channels/sensors.extruder/history?limit=20'
```

```json
{"channel": "sensors.extruder", "messages": [], "count": 0}
```

This reads the Observatory's own ring buffer, not the broker history, so it is
bounded by `buffer_size` and affected by sampling.

### `GET /api/params`

Every parameter declared through a `ParamRef`, with the value currently bound:

```json
{
  "params": [
    {
      "component_id": "tfm-0",
      "component_label": "Extruder alarm",
      "param_name": "setpoint",
      "channel": "params.extruder.setpoint",
      "key": null,
      "default": 210.0,
      "current": 215.0
    }
  ],
  "count": 1
}
```

### `POST /api/params/{channel}`

Publish a new value on a parameter channel. Every `ParameterStore` subscribed to
it rebinds its component attribute.

```bash
curl -X POST http://localhost:8765/api/params/params.extruder.setpoint \
     -H 'Content-Type: application/json' \
     -d '{"value": 215.0}'
```

Add `"key"` to update one entry of a dict-valued parameter channel. `400` when
the body has no `value`.

### Debug endpoints

Available whether or not `debug.enabled` is set, but the controller only acts on
messages when it is.

| Endpoint | Purpose |
|---|---|
| `GET /api/debug/state` | Current state, granularity, breakpoints, slow motion, step count |
| `GET /api/debug/breakpoints` | List breakpoints |
| `POST /api/debug/breakpoints` | Create one — `channel_pattern`, optional `condition` and `component_id`. Returns `201` and the `breakpoint_id` |
| `DELETE /api/debug/breakpoints/{id}` | Remove one — `204`, or `404` if unknown |

A breakpoint's `condition` is a restricted expression over the message:
comparisons, boolean operators, `value`, and `tags.<name>`. Anything else —
calls, attribute access outside `tags`, arbitrary names — is rejected at
creation with `400`, so a condition cannot execute code.

## WebSocket

Connect to `ws://localhost:8765/ws`. The server first sends a `connected`
event carrying a full snapshot — so a client that connects mid-run renders the
current state without replaying history — then streams events as they happen. Every frame has the same envelope:

```json
{"type": "<name>", "id": "<event id>", "timestamp": "<ISO 8601>", "payload": {}}
```

### Server-to-client events

| Event | Payload |
|---|---|
| `connected` | Initial snapshot: `server_version`; the buffered `messages`, `component_states`, `metrics`, `errors`, `debug_events` and `params`; then `pipeline_info`, `pipeline_state`, `components` and `topology` resolved from the live pipeline, plus `debug` when debug mode is on |
| `message.published` | `channel`, `key`, `value_preview`, `tags`, `subscriber_count`, `message_id` |
| `component.state` | `component_id`, `component_type`, `old_state`, `new_state`, `label` |
| `topology.update` | `pattern`, `action` (`subscribe`/`unsubscribe`), `subscriber_id` |
| `metric.update` | `metric_name`, `value`, `tags` |
| `param.updated` | `component_id`, `param_name`, `channel`, `old_value`, `new_value`, `label` |
| `error.occurred` | `component_id`, `error_type`, `error_message`, `context` |
| `pipeline.state` | Result of a `pipeline.*` command |
| `message.detail` | Result of `message.inspect`: the full message plus its journey |
| `param.update_result` | Result of `param.update` |
| `debug.paused`, `debug.resumed`, `debug.granularity_set`, `debug.slow_motion_set`, `debug.step_started` | The debug state after the matching `debug.*` command: `state`, `granularity`, `breakpoints`, `slow_motion`, `slow_motion_delay_ms`, `step_count` |
| `debug.step_result` | The same state, plus `step` describing what the step did — which channel, or which breakpoint was hit |
| `error` | `message` — a command failed |

`value_preview` is `repr(message.value)` truncated to 120 characters. To get the
full value, inspect the message by id.

### Client-to-server commands

Same envelope, `payload` carrying the arguments.

| Command | Payload | Reply |
|---|---|---|
| `pipeline.start` / `pipeline.stop` / `pipeline.restart` | — | `pipeline.state` |
| `message.inspect` | `message_id` | `message.detail`, or `error` if the message has fallen out of the cache |
| `param.update` | `channel`, `value`, optional `key` | `param.update_result` |
| `debug.pause` / `debug.resume` | — | `debug.paused` / `debug.resumed` |
| `debug.step` | optional `granularity` | `debug.step_started` at once, then `debug.step_result` when the step happens |
| `debug.set_granularity` | `granularity` | `debug.granularity_set` |
| `debug.set_slow_motion` | `enabled`, `delay_ms` | `debug.slow_motion_set` |

A `debug.*` command sent while debug mode is off is answered with `error` and
the message `Debug mode is not enabled`.

`debug.step` answers twice because a step advances when the next message
arrives, and on a quiet pipeline that can be a long time or never.
`debug.step_started` says the command was accepted and the step is waiting;
`debug.step_result` follows if and when it occurs. An invalid `granularity`
comes back as `error` on the command itself, not later as a stray event.

Every debug reply carries the controller's whole state, so a client can apply
any of them the same way. That matters for `debug.set_slow_motion`, which
clamps `delay_ms` to the 100–5000 ms range: the reply reports the delay that was
kept, which is not always the one that was asked for.

```json
{"type": "param.update", "payload": {"channel": "params.extruder.setpoint", "value": 215.0}}
```

## Rebuilding the UI

The frontend lives in `frontend/` (Vue 3, Vuetify, Vue Flow) and is served from
`cod3s_data/observatory/static/`.

```bash
cd frontend
npm ci
npm run build     # typecheck (vue-tsc) + bundle into dist/
npm run deploy    # bundle and copy into cod3s_data/observatory/static/
npm run dev       # dev server, proxying /api and /ws to 127.0.0.1:8765
```

**The built artifact is versioned**, because it is what ships inside the wheel —
see [architecture.md](architecture.md#bundle-the-built-frontend-in-the-python-package).
So a frontend change is not finished until `npm run deploy` has run and the
result is committed. CI rebuilds the UI and fails if the committed artifact no
longer matches the sources, and separately builds a wheel and fails if the UI is
missing from it.

Note that `npm run deploy` skips the typecheck that `npm run build` runs. Build
before deploying.
