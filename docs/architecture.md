# Architecture decisions

Why the framework is built the way it is. Each entry records a decision, the
reasoning behind it, and — where the code has since diverged — what actually
happens today.

These decisions were taken in January and February 2026, when the framework was
designed. They were re-checked against the code on 2026-08-24; the four marked
**⚠ diverged** did not survive that check.

For *what* a component does, read the [API reference](api-reference.md). This
page is about *why*.

---

## Runtime and libraries

### Python 3.12+ as the minimum version

Structural pattern matching, `asyncio.TaskGroup`, the `X | Y` type syntax and
faster startup were all wanted, and the target deployments are controlled
environments rather than arbitrary user machines, so there was no long tail of
old interpreters to support.

The cost is real: 3.12 was recent at the time, and distributions still shipping
3.10 or 3.11 need a separate interpreter. `uv` makes that a non-issue in
practice — it installs the interpreter it needs.

### Pydantic v2 for every data model

One validation mechanism for messages, configuration and component parameters,
rather than dataclasses here and manual checks there. v2's Rust core made it
fast enough to sit on the message path itself.

This is what makes a configuration error fail at load time with a message that
names the field, and it is why `ParamRef` could be added as a model rather than
as a parsing convention.

### AsyncIO for concurrency

The workload is I/O-bound — reading files, writing to sinks, waiting on
sockets — which is what asyncio is for. A single event loop also means the
broker needs no locks around its subscription registry on the hot path, and
component lifecycles are ordinary coroutines.

The consequence to keep in mind: a CPU-bound transformation blocks the loop and
therefore the whole pipeline. The original design allowed for a
`ProcessPoolExecutor` escape hatch; none is implemented today, so a heavy
transformation must be kept out of the pipeline or made cheap.

### Prefer proven libraries over custom code

The value of this project is its pub/sub architecture, not its CSV parser. So:
polars rather than a hand-rolled reader, Pydantic rather than hand-written
validation, structlog rather than a logging wrapper, FastAPI rather than an
HTTP layer.

Where several options existed, the faster one won — which is how polars,
Pydantic v2 and (nominally) msgspec were chosen.

### structlog for all logging

Logs are structured events with bound context, not formatted strings, so a
pipeline's output can be parsed downstream. `--json-logs` switches the renderer
without touching a call site.

### ⚠ Polars primary, pandas as a fallback — *diverged*

**Decided:** polars for CSV and dataframe work, with pandas as an optional
fallback for ecosystem compatibility.

**Today:** `CSVSource` does contain the fallback (`file_sources.py`, the
encoding path falls back to pandas), but **pandas is not a declared
dependency**. The fallback therefore raises `ImportError` unless the user
happens to have pandas installed for other reasons.

Either declare pandas as an optional extra or remove the fallback. As it
stands, the code advertises a path that is not reachable from a clean install.

### ⚠ Pydantic JSON by default, msgspec as a fast option — *diverged*

**Decided:** Pydantic's own JSON serialization by default, with msgspec
available where speed matters.

**Today:** msgspec is a **required** dependency in `pyproject.toml` and is
**imported nowhere** in the package or the tests. It is dead weight in every
install.

Either use it where it was meant to be used, or drop the dependency.

---

## Messages and the broker

### Messages are immutable

`Message` is a frozen Pydantic model. A transformation cannot mutate a message
that other subscribers are also holding, which removes a whole class of bug in
a fan-out topology where several components receive the same object.

Deriving a new message is explicit: `with_value()` and `with_tags()` return a
copy. That explicitness is the point — a message changing shape is visible in
the code.

### Hybrid subscription registry: O(1) exact, compiled regex for wildcards

Most subscriptions are exact channel names, so those go in a dict and cost
nothing to match. Wildcard patterns (`sensors.*`, `sensors.**`) are compiled to
regex once at subscribe time rather than being interpreted per message.

A trie would be asymptotically better but is harder to reason about, and the
wildcard count in a real pipeline is small. This keeps the common case fast and
the code readable.

### Fail fast on configuration, stay resilient at runtime

Two different kinds of error deserve two different answers.

A **configuration** error is a mistake that will not fix itself: an unknown
component type, a missing required parameter, a malformed channel. It raises at
load time, before anything starts, which is why `cod3s-data validate` is worth
running.

A **runtime** error is often transient: a sink that is briefly unreachable, one
malformed row in a file. Killing the pipeline for it would be wrong, so
destinations retry with backoff and can route failures to a dead-letter
channel, and a component that fails is isolated rather than fatal.

The same principle explains why every Observatory hook is wrapped in a bare
`except`: monitoring must never be able to break the thing it monitors.

---

## Observatory

### Embedded FastAPI, not a separate process

The bridge reads live framework state — topology, component states, buffered
messages — and doing that in-process avoids serialising it across an IPC
boundary. Uvicorn's `loop="none"` lets the server run as a task inside the
framework's own event loop rather than starting a second one.

The isolation that makes this safe is the exception guard on every hook: a
failure in the Observatory cannot propagate into the pipeline.

### Vue Flow for the topology graph

Nodes and edges are reactive Vue props, so the graph follows the store with no
manual DOM work; custom node types are ordinary Vue components rendered through
slots; and minimap, zoom controls and dagre layout come with it. Cytoscape.js
would have meant bridging an imperative graph library into a reactive UI.

### JSON on the WebSocket, not MessagePack

Payloads are small and the client count is low, so the bandwidth saving would
have been invisible — while JSON stays readable in browser devtools and needs
no decoding library on either side. Debuggability won over efficiency, on
purpose.

### ⚠ Canvas for the timeline — *diverged*

**Decided:** render the timeline on a `<canvas>`, because SVG DOM manipulation
becomes the bottleneck at thousands of visible markers, and canvas allows
drawing only the visible window plus density heatmaps when zoomed out.

**Today:** `TimelineView.vue` renders `<svg>`. The element that carries the
name is a wrapper `div` with a `timeline-canvas-wrap` class, not a canvas.

Either the performance argument did not hold in practice and the decision was
quietly reversed, or the reversal was accidental. Worth settling before anyone
pushes the timeline to high message rates.

### ⚠ Bundle the built frontend in the Python package — *diverged*

**Decided:** ship the pre-built UI inside the wheel, so
`pip install 'cod3s-data[observatory]'` is a single command with no Node.js,
works offline in industrial environments, and cannot drift out of version with
its backend.

**Today:** it is not shipped. `pyproject.toml` declares no `package-data`, there
is no `MANIFEST.in`, and `cod3s_data/observatory/static/` is gitignored.
Building a wheel produces 60 files, **none** of them from `static/`.

The failure is silent: `create_app()` only mounts the static directory when it
exists and is non-empty, so an installed package serves a working REST and
WebSocket API and 404s the UI. Anyone working from a clone after
`npm run deploy` sees a functioning Observatory and has no reason to suspect
this.

Fixing it means deciding how the artifact is produced at build time — commit
it, build it in CI before packaging, or use a build hook — which is a packaging
decision, not a documentation one. Tracked as
[issue #1](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/1).
