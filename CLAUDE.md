# CLAUDE.md

Guidance for Claude Code when working in this repository.

COD3S Data is an AsyncIO pub/sub framework for real-time sensor data. Python
3.12+. Sources publish messages to channels, transformations process them
between channels, destinations consume them.

## Commands

```bash
# Install (uses uv)
uv pip install -e ".[dev]"           # dev dependencies
uv pip install -e ".[observatory]"   # Observatory (FastAPI/WebSocket UI)
uv pip install -e ".[influxdb]"      # InfluxDB destination

# Tests
uv run pytest                        # all tests (coverage enabled by default)
uv run pytest tests/unit/            # unit tests only
uv run pytest tests/integration/     # integration (InfluxDB ones self-skip)
uv run pytest tests/performance/ -s  # benchmarks, -s to see the numbers
uv run pytest tests/unit/broker/ -k "wildcard"   # a single test

# Code quality — all four run in CI and are expected to be clean
uv run ruff check .
uv run ruff format .
uv run mypy cod3s_data/              # strict mode

# CLI
uv run cod3s-data validate FILE.yaml
uv run cod3s-data run FILE.yaml
uv run cod3s-data run FILE.yaml --observatory --log-level DEBUG

# Observatory frontend (frontend/)
cd frontend && npm run dev           # dev server, proxies /api and /ws to :8765
cd frontend && npm run build         # vue-tsc typecheck + vite build
cd frontend && npm run deploy        # build + copy into cod3s_data/observatory/static/
                                     # NOTE: deploy skips the typecheck — build first
```

## Architecture

### Core pipeline: Sources → Broker → Transformations → Destinations

- **Message** (`core/message.py`): frozen Pydantic model with `key`,
  `timestamp`, `value`, `tags`, `id`. Immutable; `with_value()` / `with_tags()`
  return copies.
- **Broker** (`broker/in_memory.py`): in-memory pub/sub. Exact subscriptions are
  O(1); wildcards (`sensors.*`, `sensors.**`) are compiled to regex at subscribe
  time. Keeps bounded per-channel history.
- **Sources** (`sources/`): `RandomSource`, `SequenceSource`, `FileSource`,
  `CSVSource` (polars), `CSVWatchSource`, `DirectoryWatchSource`,
  `ParamFileSource`. Extend via `sources/base.py:Source`.
- **Transformations** (`transformations/`): `FilterTransform`, `MapTransform`,
  `AggregateTransform` (tumbling), `UnpackTransform`, `ThrottleTransform`,
  `MovingAverageTransform`, `MedianFilterTransform`,
  `DeviationFilterTransform`, `AlarmTransform`, `RelativeAlarmTransform`.
  Extend via `transformations/base.py:Transformation`.
- **Destinations** (`destinations/`): `ConsoleDestination`, `FileDestination`,
  `InMemoryDestination`, `CollectDestination`, `InfluxDBDestination`. Extend via
  `destinations/base.py:Destination`.
- **Framework** (`framework.py`): wires components and manages lifecycle
  (`PipelineState`: idle → running → stopping → stopped).

`config/factory.py` holds the registry mapping a YAML `type:` name to a class.
It is the authority; `docs/api-reference.md#component-type-names` mirrors it.

### Configuration

- **Models** (`config/models.py`): `PipelineConfig`, `SourceConfig`,
  `TransformConfig`, `DestinationConfig`, `ParamRef`.
- **Dynamic parameters**: a param written as
  `{ref: <channel>, default: ..., key: ...}` is fed from the broker instead of
  the file. The factory substitutes `default` and attaches a `ParameterStore`
  (`transformations/param_store.py`) that rebinds the attribute on each message
  and reads channel history at start. Editable at runtime via `/api/params`.
- **Loaders** (`config/loaders.py`): YAML loading plus `COD3S_*` environment
  overrides.

### Observatory (optional)

FastAPI + WebSocket backend in `observatory/`, Vue 3 / Vuetify / Vue Flow
frontend in `frontend/`. Six pages: topology, timeline, message inspector,
parameters, metrics, debug. Full reference in `docs/observatory.md`.

Every bridge hook swallows its exceptions on purpose: monitoring must never
break the pipeline it monitors.

### Observability

`structlog` (`observability/logging.py`). Metrics are published as ordinary
messages on `_metrics.**` channels (`observability/metrics.py`) — there is no
separate metrics system.

## Conventions

- `asyncio_mode = "auto"` in pytest — async tests need no decorator
- ruff line-length 100, target py312; mypy strict
- Coverage on by default (term-missing + HTML)
- Integration tests carry `@pytest.mark.integration`
- A `Source` in REALTIME mode blocks in `start()`; tests must wrap it in
  `asyncio.create_task()` rather than awaiting it

## Working here

Keep `ruff check`, `ruff format --check`, `mypy` and `pytest` clean rather than
adding ignores — CI runs all four on merge requests, `main` and tags
(`.gitlab-ci.yml`).

Before documenting behaviour, verify it against the code or by running it. The
documentation drifted badly once and was rebuilt with scripted checks; the
useful habit is to instantiate a pipeline through the real `ComponentFactory`
rather than trusting that a config validates.

Read `BACKLOG.md` before assuming something is missing by accident — several
gaps are known and recorded, including the wheel not shipping the Observatory
UI. `docs/architecture.md` records why the framework is shaped this way and the
four places the code has diverged from its own design decisions.
