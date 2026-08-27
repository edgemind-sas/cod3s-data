# Architecture decisions

Why the framework is built the way it is. Each entry records a decision, the
reasoning behind it, and — where the code has since diverged — what actually
happens today.

These decisions were taken in January and February 2026, when the framework was
designed. They were re-checked against the code on 2026-08-24; four did not
survive that check. All four have since been settled: the frontend missing from
the wheel, the pandas fallback that could not run, the msgspec dependency
nothing imported, and the timeline decided for canvas and built in SVG. What
remains open is tracked in the
[issue tracker](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues).

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

Where several options existed, the faster one won — which is how polars and
Pydantic v2 were chosen.

### structlog for all logging

Logs are structured events with bound context, not formatted strings, so a
pipeline's output can be parsed downstream. `--json-logs` switches the renderer
without touching a call site.

### Polars for CSV, with no fallback

**Decided:** polars for CSV and dataframe work, with pandas as an optional
fallback for ecosystem compatibility.

**Settled on 2026-08-25:** the fallback is gone; polars is the only reader.

It could never have run. It sat behind `except ImportError` on the polars
import, and polars is a *required* dependency — so the guard never fired. Had
it fired, the fallback would have failed anyway, because pandas was declared
nowhere. Two independent reasons the branch was unreachable.

Its stated justification — that pandas "supports all encodings" — had also
stopped being true of the alternative: the polars path decodes non-utf8 files
with Python before parsing, so it handles every encoding pandas would have.

One reader is also one behaviour to document and one library to keep current.

### Pydantic JSON, and only Pydantic JSON

**Decided:** Pydantic's own JSON serialization by default, with msgspec
available where speed matters.

**Settled on 2026-08-25:** the first half held — `Message.to_json()` is
`model_dump_json()`. The second half never happened: msgspec was a *required*
dependency that no module and no test ever imported, so every install carried
it and nothing used it. It has been dropped.

The speed argument had lost its target in the meantime. The one hot path that
would justify a faster encoder is the Observatory WebSocket, and that was
deliberately decided the other way — see *JSON on the WebSocket, not
MessagePack* below. The Observatory also samples messages rather than encoding
every one, because the browser saturates long before the encoder does.

If a serialization bottleneck ever shows up in a measurement, this is worth
reopening. It should not be reopened on the strength of a benchmark someone
read.

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

### A dead letter is tagged, not wrapped

A message that reaches the dead-letter channel keeps its key, its timestamp and
its value, and gains `dlq_*` tags: which destination gave up, on what
exception, after how many attempts.

The alternative was to wrap the value in a structure holding the original
alongside the failure. Tags won because a dead-letter channel is still a
channel: anything that can read the input stream can read this one, and a
wrapper would break every such consumer. The cost is that `tags` is
`dict[str, str]`, so the attempt count travels as `"3"`.

Private state was not an option either — `model_dump_json()` omits private
attributes, so nothing written to a file or a sink would ever carry it. That is
also why `Message._retry_count`, declared for this purpose and never used, was
removed rather than wired in.

Until 2026-08-26 the message was republished untouched. `_write_with_retry`
returned a bare `bool` and discarded the exception, so by the time the caller
knew a message had failed, the reason no longer existed anywhere in the
process. That is the part that had to change first; the tags were the easy
half.

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

### The WebSocket protocol is defined by the code that sends it

**Settled on 2026-08-26:** `observatory/models/` held Pydantic models —
`WebSocketEvent`, a payload model per event, five debug commands — that read
like the definition of the protocol. Nothing imported them. The bridge builds
its event dictionaries itself and `routes/ws.py` dispatches on `data["type"]`,
so the models sat beside that path rather than on it, which is what the 0 %
coverage was reporting.

They had also drifted from the shape they claimed to describe: no model for
`param.updated`, none for the `pipeline.*`, `param.update` or `message.inspect`
commands, and `message_id` and `label` absent from two payloads that carry them.
Wiring them in would have meant writing them again, not connecting them.

They were removed. A stale second description of a protocol is worse than none,
because it invites a reader to trust it. If the protocol is ever worth
validating rather than merely documenting, the schema should be written against
the messages that actually cross the socket, alongside the tests that exercise
them — [issue #6](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/6).

### SVG for the timeline — the cost is the redraw rate, not the marker count

**Decided:** render the timeline on a `<canvas>`, because SVG DOM manipulation
becomes the bottleneck at thousands of visible markers, and canvas allows
drawing only the visible window plus density heatmaps when zoomed out.

**Settled on 2026-08-26:** `TimelineView.vue` renders `<svg>`, and it stays
that way. The premise did not survive the check — the marker count cannot reach
thousands. `stores/messages.ts` retains 1000 messages and evicts the oldest, so
the plot is capped at a thousand `<circle>` elements by construction, which is
well inside what SVG handles.

The cost the decision was reaching for is real, but it is a *rate*, not a count,
and canvas on its own would not have addressed it. Sampling defaults to `none`,
so a fast pipeline delivers one WebSocket event per message, and each one drove
a full re-render: the store replaced its array, every derived value was
invalidated, and every dot moved. That last part was the expensive one and it
was not obvious — a dot's `x` derives from the time origin, which tracked the
oldest retained message, and from `pxPerSecond`, which tracked the retained
span. Both shifted whenever a message arrived, so adding one dot rewrote the
coordinates of the other thousand. A canvas would have redrawn a thousand points
per message for exactly the same reason.

Three changes put the rate under the display's control instead of the
pipeline's. Arrivals are coalesced into one reactive mutation per animation
frame. The origin and the extent are snapped to a ten-second grid — the origin
down, the extent up — so both hold still between jumps and the dots that did not
move keep their coordinates. Dots are keyed by message id and carry geometry
alone; the tooltip's formatted strings are derived from the hovered message,
rather than being built for a thousand messages in order to display one.

Replaying evictions against both formulas, counting surviving dots whose `x`
changed, gives per arrival: at 100 msg/s, 999 before and 5 after; at 10 msg/s,
999 and 20; at 1 msg/s, 999 and 100. The middle case is the one worth keeping in
mind — it is where `pxPerSecond` sits between its floor and the zoom window, so
quantising the origin alone changed nothing there and the scale had to be
quantised too.

What this does not buy is the other half of the canvas argument: drawing only
the visible window, and density heatmaps when zoomed out. Both remain out of
reach in SVG, and both only start to matter above the 1000-message cap. Raising
that cap is what would reopen this decision.

### Bundle the built frontend in the Python package

Ship the pre-built UI inside the wheel, so
`pip install 'cod3s-data[observatory]'` is a single command with no Node.js,
works offline in industrial environments, and cannot drift out of version with
its backend.

This was decided in February and only implemented in August: for six months
`pyproject.toml` declared no `package-data`, so a wheel carried 60 files and
none of the UI. The failure was silent — `create_app()` mounts the static
directory only when it exists and is non-empty, so an installed package served
a working REST and WebSocket API and 404'd every page — and invisible from a
clone, where `npm run deploy` has populated the directory.

**How it holds now.** The built artifact is versioned in
`cod3s_data/observatory/static/` rather than gitignored, and `package-data`
ships it. Two CI jobs keep it honest: `package` builds a wheel and fails if
`index.html` is missing from it, and `frontend` rebuilds the UI and fails if the
committed artifact no longer matches the sources.

Versioning a build artifact is a real cost — every frontend change produces a
binary diff — and it was accepted because it is what makes the wheel buildable
by anyone, anywhere, with no Node toolchain. That property is the one that
failed.

Related: `@mdi/font` declares four font formats and Vite emitted all four, 3.5 MB
of the 4.9 MB bundle. A `vite.config.ts` plugin now keeps woff2 alone, which
every browser since about 2015 supports; the artifact is 1.8 MB.
