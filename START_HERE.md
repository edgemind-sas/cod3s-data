# Start here

COD3S Data is an AsyncIO pub/sub framework for real-time sensor data: sources
publish messages to channels, transformations process them between channels,
destinations consume them. Everything else is detail.

This page is a map. It tells you where to go, not how things work.

## Run something in the next minute

```bash
uv pip install -e ".[dev]"
uv run cod3s-data run examples/simple_pipeline.yaml
```

Ten numbers, printed to the console. Now something with more moving parts:

```bash
uv pip install -e ".[observatory]"
uv run cod3s-data run examples/print_job_dynamic.yaml --observatory
```

Open <http://localhost:8765>. Two simulated temperature sensors, two alarms
whose setpoints come from `examples/jobs/PLA.yaml`, and a UI showing the
topology live. Change a setpoint without stopping the pipeline:

```bash
curl -X POST http://localhost:8765/api/params/params.alarm.extruder.setpoint \
     -H 'Content-Type: application/json' -d '{"value": 215}'
```

## Where to go next

| If you want to… | Read |
|---|---|
| Write your first pipeline | [docs/quickstart.md](docs/quickstart.md) |
| Solve a concrete problem | [GETTING_STARTED.md](GETTING_STARTED.md) — task-oriented recipes |
| Look up a component or a parameter | [docs/api-reference.md](docs/api-reference.md) |
| Watch a pipeline while it runs | [docs/observatory.md](docs/observatory.md) |
| See working pipelines | [examples/README.md](examples/README.md) — seven of them |
| Install on Windows | [README_WINDOWS.md](README_WINDOWS.md) |
| Understand why it is built this way | [docs/architecture.md](docs/architecture.md) |
| Know what is missing or broken | [BACKLOG.md](BACKLOG.md) |

[docs/glossary.md](docs/glossary.md) defines the vocabulary — several of these
words mean something slightly different here than in other streaming
frameworks.

## Where the code is

```
cod3s_data/
├── core/            Message, buffers, subscription registry
├── broker/          In-memory pub/sub, wildcard channels
├── sources/         Produce messages      → sources/base.py:Source
├── transformations/ Process messages      → transformations/base.py:Transformation
├── destinations/    Consume messages      → destinations/base.py:Destination
├── config/          Pydantic models, YAML loading, ComponentFactory
├── observatory/     Web UI backend (FastAPI + WebSocket)
├── observability/   Structured logging, metrics as messages
├── framework.py     Orchestrator and lifecycle
└── cli.py           cod3s-data run / validate

frontend/            Observatory UI (Vue 3, Vuetify, Vue Flow)
examples/            Runnable pipelines, Python and YAML
tests/               unit / integration / performance
```

A component's `type:` name in YAML is resolved by the registry in
`config/factory.py`. That registry is the authority on what exists; the
[type table](docs/api-reference.md#component-type-names) mirrors it.

## Working on the framework

```bash
uv run pytest                        # the suite
uv run ruff check .                  # lint
uv run ruff format .                 # format
uv run mypy cod3s_data/              # types, strict
```

All four run in CI on every merge request, and all four are expected to be
clean. If one is not, that is a regression rather than a known state.

The Observatory UI is built separately:

```bash
cd frontend && npm ci && npm run build
cd frontend && npm run deploy        # copies into cod3s_data/observatory/static/
```

`npm run deploy` skips the typecheck that `npm run build` runs. Build before
deploying.
