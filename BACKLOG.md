# Backlog

The backlog lives in the project's **internal issue tracker**; the `#N` numbers below refer to it.
Everything below was opened there in August 2026, after being verified against
the code; this page is an index, not a second copy.

Why an index rather than nothing: a clone should be able to say what is known to
be broken without network access. Why not the full text: two places tracking the
same work drift apart, which is the failure this repository has just spent a
cleanup recovering from.

## Defects

None open. The seven defects opened in August are all settled.

#1 — an installed
package having no Observatory UI — the built artifact is now versioned and
declared as `package-data`, and two CI jobs keep it that way.
#2 and
#3 were the two
dependency defects: `msgspec` was required and imported nowhere, and the pandas
fallback in `CSVSource` could not run. Both were removed rather than wired in.
#4 — a Pydantic
description of the WebSocket protocol that nothing imported — was removed for
the same reason, and for one more: it no longer described the protocol.
#5 — a timeline
decided for canvas and rendered in SVG — was settled the other way round: the
marker count is capped at 1000, so the premise of the canvas decision never
arises, while the cost that is real, the redraw rate, is now coalesced per
animation frame.

#18 — the three
loose ends of the WebSocket debug plane — is fixed, and turned out to be four.
Every debug reply now carries the controller's whole state, which is what makes
the two orphan replies routable and what stops `set_slow_motion` announcing a
delay it had already clamped; `debug.step_result` was the fourth, carrying a
payload with no state field in it, so the client applied nothing. `debug.step`
answers twice — `debug.step_started` at once, then the result if and when a
message arrives — because the wait is unbounded by design and silence was
indistinguishable from a lost command. Both sides moved in the same change, the
protocol tables in [docs/observatory.md](docs/observatory.md) with them.

#21 — private
attributes on `Message` that nothing read or wrote — was deletion, for the
reason that made them unusable in the first place: `model_dump_json()` omits
private state, so `_retry_count` could never have reached a consumer of the
dead-letter channel. That is what #14 records in
[docs/architecture.md](docs/architecture.md), and the entry now says the
attribute was removed rather than that it sits there unused. The ticket named
two; the third in the same block, `_trace_id`, went with them, and `Message`
now declares no private state at all. Correlating a message with the ones it
produced is done — and stays done — in `observatory/bridge.py`, in a table of
its own.

The reasoning for each is in [docs/architecture.md](docs/architecture.md).

## Tests and CI

None open. The five opened in August are settled.

#6 is fixed — the
REST routes are at 100 %, the WebSocket endpoint at 89 %, and the work found
what the ticket predicted it would: every `/api/debug/*` route answered 500
when the Observatory ran without `--debug`, which is the default.

#7 is fixed — the CI
`test` job runs an InfluxDB service and the four integration tests run against
it. `COD3S_TEST_INFLUXDB_REQUIRED` is what keeps them running: without it, a
broken service would send them back to the silent skip that hid them, since a
JUnit report does not distinguish "skipped" from "passed" at a glance.

#8 is fixed — the
public methods that carried no docstring now do, and
`tests/unit/test_public_api_docstrings.py` fails if a new one appears.

#20 is fixed — the
sequel to #8, covering the sixteen public *properties* it had left out. A
second check reads them through `fget.__doc__`, because `inspect.getdoc` on a
mute redefined property returns its parent's text and would let it through.

#19 is fixed —
`tests/integration/test_example_scenarios.py` replays both scenario demos
through the CLI and holds the counts the README prints: 70 raw alarms against 8
smoothed, and the cold chain's two alarms reaching the dead-letter channel with
their `dlq_*` tags while neither frozen compartment fires. Through the CLI
rather than a Python assembly with a `collect` destination, because the numbers
being defended are counts of console lines produced by the command the README
tells a reader to type. It costs about fifty seconds of CI.

## Features designed but not built

Specified in January 2026, never implemented. Each remains a reasonable thing to
want; none is committed to a release.

| # | | |
|---|---|---|
| #9 | `DeduplicationTransform` | `évolution` |
| #10 | `UnitConversion` | `évolution` |
| #11 | `Sampler` — one message in N, unlike the time-based `throttle` | `évolution` |
| #12 | Dynamic channel names templated from the message | `évolution` |
| #13 | Strict mode for out-of-order messages | `évolution` |
| #15 | Tag filtering with OR semantics | `évolution` |
| #16 | `SourceStatus` — progress, ETA, error detail | `évolution` |

#14 is built — a
message on a dead-letter channel now carries `dlq_*` tags saying which
destination gave up, on what exception, after how many attempts. The reasoning
for tags over a wrapper is in [docs/architecture.md](docs/architecture.md).

Three entries from the same January roadmap have since been built under other
names and are **not** listed: `ThresholdAlert` became `AlarmTransform`,
`RateLimiter` became `ThrottleTransform`, and TRANSPOSE mode exists as
`CSVSource(replay=, speed_factor=)`.

## Housekeeping

None open. #17 is
done: `old-devel` is deleted, the tutorial scaffolding is gone from the
repository root, and the `.gitignore` data rules are anchored to the root so
they no longer need a negation for every config file they used to swallow.

---

## Directions considered, not committed

Deliberately **not** ticketed. These were explored during design and no decision
was taken; opening issues for them would misrepresent them as planned work.

**Integration** — destinations for external databases (PostgreSQL, Redis);
sources and destinations for message brokers (Kafka, AMQP — MQTT now ships both
ways, see `sources/mqtt_source.py` and `destinations/mqtt.py`); HTTP and
WebSocket sources; Prometheus and OpenTelemetry export.

**Scale** — a networked broker in place of the in-memory one; distributed
processing across workers; persistent state backends for stateful
transformations.

**Beyond streaming** — complex event processing, ML inference as a
transformation, a Kubernetes operator, a schema registry for message validation.

The framework's current shape — one process, one event loop, one in-memory
broker — is what makes it simple. Most of these would change that, and the first
one adopted should be the one a real deployment actually needs.

Why the framework is shaped this way, and where the code has diverged from its
own design decisions: [docs/architecture.md](docs/architecture.md).
