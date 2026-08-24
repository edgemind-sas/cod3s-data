# Glossary

The vocabulary this project uses, and what each term means *here* — several of
these words mean something slightly different in other streaming frameworks.

Terms are grouped by where you meet them. For parameters and signatures, see
the [API reference](api-reference.md).

---

## The data

**Message** — the unit that flows through everything. A frozen Pydantic model
with five fields: `key`, `timestamp`, `value`, `tags`, `id`. Immutable by
design, so a fan-out cannot let one subscriber mutate what another is reading;
`with_value()` and `with_tags()` return a copy.

**Key** — what the message is about, not where it is going. Usually a sensor or
signal name (`extruder`, `bed`). Several transformations keep per-key state, and
some destinations map the key onto their own naming — `InfluxDBDestination`
turns it into the measurement name.

**Value** — the payload. A number, a string, or a dict. Numeric transformations
ignore anything that is not a number, silently, which is the usual reason a
stage produces nothing.

**Tags** — string metadata carried alongside the value (`{"printer_id": "p3"}`).
They travel with the message through transformations and reach destinations as
labels. Always strings.

**Timestamp** — when the reading happened, not when it was processed.
Timezone-aware and normalised to UTC. Sources that read files take it from the
data; a replay preserves the original spacing between timestamps.

**Message ID** — a UUID identifying one message. The Observatory's inspector
uses it to fetch a message's full detail.

**Trace ID** — identifies a *lineage*: the message a source published and
everything derived from it downstream. What makes a "journey" reconstructable.

---

## Routing

**Channel** — a dot-separated name a message is published to
(`sensors.temperature.extruder`). Channels are not declared anywhere; a channel
exists because something publishes to it.

**Wildcard** — a subscription pattern. `*` matches exactly one level
(`sensors.*` catches `sensors.bed`, not `sensors.temp.bed`); `**` matches any
depth. Getting these two confused is the most common reason a destination sees
nothing.

**Subscription** — a callback registered against a pattern. Exact patterns are
matched in O(1); wildcards are compiled to regex once, at subscribe time.

**Fan-out** — one message delivered to several subscribers. Since messages are
immutable, they are shared rather than copied.

**Broker** — the in-memory bus that holds subscriptions and delivers messages.
One per pipeline. It also keeps a bounded history per channel, which is what
lets a `ParameterStore` learn a value published before it started.

**System channels** — the `_metrics.**` namespace, reserved for the framework's
own metrics. The `_` prefix is refused for ordinary channels.

---

## The components

**Source** — produces messages and publishes them. Implements `produce()` as an
async generator.

**Transformation** — reads from one or more channels and publishes to another.
**Stateless** ones (`filter`, `map`) decide from the message alone;
**stateful** ones (`aggregate`, the sliding windows, the alarms) keep state
between messages — usually per key, so one transform on a wildcard handles
every sensor independently.

**Destination** — consumes messages and does something terminal with them:
print, write, store. Buffered, retried, and able to divert failures to a DLQ.

**Batch mode** — how a source behaves over time. `batch` reads a finite dataset
once and stops; `realtime` runs until stopped; `transpose` replays historical
data honouring the gaps between timestamps.

**Component id** — `src-0`, `tfm-1`, `dst-0`. Assigned in configuration order,
used by the Observatory to identify components. `label` gives them a human name.

---

## Delivery and failure

**Delivery guarantee** — `at_most_once` (the default) or `at_least_once`. In
the in-memory broker this is advisory: it is recorded, not enforced.

**Buffer** — the queue between a destination and its writer loop. Sized by
`buffer_size`.

**Overflow strategy** — what a full buffer does: `drop_oldest` (the default),
`drop_newest`, or `block`. Blocking applies backpressure upstream; dropping
keeps the pipeline moving and loses data.

**Backpressure** — a slow consumer slowing its producer instead of losing
messages. Only `block` produces it.

**Retry strategy** — `exponential` (the default) or `fixed`, applied
`retry_attempts` times before a write is given up on.

**Dead letter queue (DLQ)** — a channel messages are published to when a
destination has exhausted its retries. Nothing subscribes to it unless you say
so; a DLQ with no subscriber is a silent drop.

**Metrics as messages** — the framework has no separate metrics system. Counts
and rates are published on `_metrics.**` like any other message, so you observe
them with an ordinary destination.

---

## Windows

**Time window** — a window defined by duration. **Count window** — by number of
messages.

**Tumbling** — the window used by `aggregate`: it fills, emits once, and starts
empty. One output per closed window.

**Sliding** — the window used by `moving_average` and `median_filter`: it emits
on *every* input message once `min_samples` is reached, over the last N values
for that key. One output per input.

Reaching for the wrong one is a common mistake: `aggregate` for a summary every
N messages, a sliding window for a smoothed signal.

---

## Dynamic parameters

**ParamRef** — a component parameter written as `{ref: <channel>, default: …}`
instead of a fixed value, so it is fed from the broker.

**ParameterStore** — what the factory attaches to a component for each
`ParamRef`. It subscribes to the channel, rebinds the attribute on every
message, and reads channel history at start so a late component is hydrated
before its first data message.

Together they are why a setpoint can be changed while a pipeline runs.

---

## Observatory

**Observatory** — the optional web UI. See [observatory.md](observatory.md).

**Bridge** — the object between framework and UI. The framework calls hooks on
it; it pushes events to browsers and answers their commands. Every hook
swallows its exceptions: monitoring must not break what it monitors.

**Hook** — one of those call sites (`on_message_published`,
`on_component_state_change`, `on_param_updated`, …).

**Event buffer** — a bounded ring buffer of recent events, capped by both entry
count and memory. What a late-connecting browser is sent so it can render the
current state without replaying history.

**Sampling** — showing the UI only a fraction of messages (`every_nth`,
`time_based`) when a pipeline publishes faster than a browser can render. It
never drops a message from the pipeline itself.

**Topology** — the components-and-subscriptions graph drawn on the topology
page.

**Journey** — one message's path through the pipeline, reconstructed from its
trace id: which component received it, what it produced, on which channel.

**Inspector** — the page that shows one message in full, with its journey.

**Timeline** — messages over time, per channel. **Live tail** is the mode where
it follows the present.

**Debug controller** — pause, resume, step. Its **state** is `inactive`,
`running`, `paused` or `stepping`; its **granularity** is `message`, `stage` or
`breakpoint`. **Slow motion** inserts a delay between messages instead of
stopping.

**Breakpoint** — a channel pattern with an optional condition, evaluated by a
restricted expression parser that allows comparisons, boolean operators,
`value` and `tags.<name>` — and nothing that could execute code.

**Interactive mode** — the pipeline is built but waits for the UI to start it,
so nothing is missed before a browser connects.
