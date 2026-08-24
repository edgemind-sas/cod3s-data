# Backlog

What is known to be missing, wrong or unfinished. Items are grouped by kind and
ordered by how much they cost to leave alone.

Everything here was verified against the code on 2026-08-24. Items about *why*
the framework is shaped the way it is live in
[docs/architecture.md](docs/architecture.md).

---

## Defects

### An installed package has no Observatory UI

`pyproject.toml` declares no `package-data`, there is no `MANIFEST.in`, and
`cod3s_data/observatory/static/` is gitignored. Building a wheel produces 60
files and **none** of them are the UI, so `pip install 'cod3s-data[observatory]'`
installs a working REST and WebSocket API that serves 404 for every page.

It fails silently — `create_app()` mounts the static directory only when it
exists and is non-empty — and it is invisible from a clone, where
`npm run deploy` has populated the directory.

Fixing it is a packaging decision, not a patch: build the frontend in CI before
packaging, commit the artifact, or add a build hook. Whichever way, the wheel
should be checked for `static/` afterwards.

### `msgspec` is a required dependency and is never imported

Zero occurrences in `cod3s_data/` and `tests/`. It was chosen as an optional
fast path for serialization (see
[architecture.md](docs/architecture.md#pydantic-json-by-default-msgspec-as-a-fast-option-diverged))
and never wired in. Either use it or drop it; today every install pays for it.

### The pandas fallback cannot run

`CSVSource` falls back to pandas for encodings polars refuses, but pandas is not
a declared dependency, so the fallback raises `ImportError` on a clean install.
Declare it as an extra or remove the branch.

### `cod3s_data/observatory/models/` is dead code

`events.py` and `commands.py` define Pydantic models for the WebSocket protocol.
48 statements, 0% coverage, imported by nothing — the WebSocket layer builds
plain dicts.

Wiring them in would give the protocol actual validation and a single place to
define it. Deleting them is also fine. Leaving them is the one option that
costs something: they read as the protocol definition and are not.

### The timeline renders SVG where canvas was chosen

Recorded as a deliberate decision for performance at high message rates, then
implemented with `<svg>`. Either the argument did not hold and the reversal
should be recorded, or it was accidental. Worth settling before pushing the
timeline to high rates.

---

## Test and CI coverage

### The Observatory HTTP and WebSocket surface is barely tested

`routes/ws.py` 11%, `routes/topology.py` 26%, `routes/params.py` 42%,
`bridge.py` 73% over 695 lines. This is the most exposed part of the codebase
and the least covered. The topology bug fixed in August — parameter updates
erasing components from `/api/topology` — lived in exactly this gap.

`httpx` is not installed, so `fastapi.testclient` is unavailable; route
functions have to be called directly, which the existing tests now show how to
do. Adding `httpx` to the dev extra would make this easier.

### InfluxDB integration tests never run in CI

They skip themselves when no server answers, so CI is green without them. The
connection URL is hardcoded to `localhost:8086` while a GitLab service is
addressed by hostname. Make the URL configurable, then add a `services:` block.

### 28 public methods have no docstring

Including `Destination.write/start/stop/close` and every assertion helper on
`CollectDestination` — the surface someone writing a custom component reads
first.

---

## Features designed but not built

Carried over from the original roadmap. These were specified in January and
never implemented; each is still a reasonable thing to want.

| Feature | What it would do |
|---|---|
| `DeduplicationTransform` | Drop duplicates by key+timestamp or message id |
| `UnitConversion` | Convert measurement units between channels |
| `Sampler` | Keep one message in N — unlike `throttle`, which is time-based |
| Dynamic channel names | Template a channel from message data (`sensors.{location}.temp`) |
| Out-of-order strict mode | Reject a message older than the latest seen, rather than accepting it |
| DLQ metadata enrichment | Add original channel, failure reason and retry count to DLQ messages |
| Tag filtering with OR | Allow a list of accepted values for one tag key |
| `SourceStatus` | Progress, ETA and error detail for long-running sources |

Two entries from the same roadmap have since been built under different names —
`ThresholdAlert` became `AlarmTransform`, `RateLimiter` became
`ThrottleTransform` — and TRANSPOSE mode exists as `CSVSource(replay=,
speed_factor=)`. They are not listed above.

---

## Directions considered, not committed

Explored during design, with no decision taken. Recorded so the thinking is not
lost, not as a plan.

**Integration** — destinations for external databases (PostgreSQL, Redis);
sources and destinations for message brokers (MQTT, Kafka, AMQP); HTTP and
WebSocket sources; Prometheus and OpenTelemetry export.

**Scale** — a networked broker in place of the in-memory one; distributed
processing across workers; persistent state backends for stateful
transformations.

**Beyond streaming** — complex event processing (patterns across a stream), ML
model inference as a transformation, a Kubernetes operator, a schema registry
for message validation.

The framework's current shape — one process, one event loop, one in-memory
broker — is what makes it simple. Most of these would change that, and the
first one adopted should be the one a real deployment actually needs.

---

## Housekeeping

- `origin/old-devel` has been abandoned since 2026-01-06, 21 commits divergent.
- `my_first_pipeline.yaml` and `my_python_pipeline.py` sit at the repository
  root as tutorial scaffolding; `examples/` is where they belong.
- The `*.json` rule in `.gitignore` matches every JSON config file, not just
  sample data. Three frontend files are negated explicitly; the next one will
  have to be too.
