# Backlog

The backlog lives in the **[issue tracker](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues)**.
Everything below was opened there on 2026-08-24, after being verified against the
code; this page is an index, not a second copy.

Why an index rather than nothing: a clone should be able to say what is known to
be broken without network access. Why not the full text: two places tracking the
same work drift apart, which is the failure this repository has just spent a
cleanup recovering from.

## Defects

None open. The five that were are all settled.

[#1](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/1) — an installed
package having no Observatory UI — the built artifact is now versioned and
declared as `package-data`, and two CI jobs keep it that way.
[#2](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/2) and
[#3](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/3) were the two
dependency defects: `msgspec` was required and imported nowhere, and the pandas
fallback in `CSVSource` could not run. Both were removed rather than wired in.
[#4](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/4) — a Pydantic
description of the WebSocket protocol that nothing imported — was removed for
the same reason, and for one more: it no longer described the protocol.
[#5](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/5) — a timeline
decided for canvas and rendered in SVG — was settled the other way round: the
marker count is capped at 1000, so the premise of the canvas decision never
arises, while the cost that is real, the redraw rate, is now coalesced per
animation frame.

The reasoning for each is in [docs/architecture.md](docs/architecture.md).

## Tests and CI

None open. All three are settled.

[#6](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/6) is fixed — the
REST routes are at 100 %, the WebSocket endpoint at 89 %, and the work found
what the ticket predicted it would: every `/api/debug/*` route answered 500
when the Observatory ran without `--debug`, which is the default.

[#7](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/7) is fixed — the CI
`test` job runs an InfluxDB service and the four integration tests run against
it. `COD3S_TEST_INFLUXDB_REQUIRED` is what keeps them running: without it, a
broken service would send them back to the silent skip that hid them, since a
JUnit report does not distinguish "skipped" from "passed" at a glance.

[#8](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/8) is fixed — the
public methods that carried no docstring now do, and
`tests/unit/test_public_api_docstrings.py` fails if a new one appears. Sixteen
public *properties* are still undocumented; the check does not cover them.

## Features designed but not built

Specified in January 2026, never implemented. Each remains a reasonable thing to
want; none is committed to a release.

| # | | |
|---|---|---|
| [#9](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/9) | `DeduplicationTransform` | `évolution` |
| [#10](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/10) | `UnitConversion` | `évolution` |
| [#11](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/11) | `Sampler` — one message in N, unlike the time-based `throttle` | `évolution` |
| [#12](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/12) | Dynamic channel names templated from the message | `évolution` |
| [#13](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/13) | Strict mode for out-of-order messages | `évolution` |
| [#14](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/14) | DLQ metadata enrichment | `évolution` |
| [#15](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/15) | Tag filtering with OR semantics | `évolution` |
| [#16](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/16) | `SourceStatus` — progress, ETA, error detail | `évolution` |

Three entries from the same January roadmap have since been built under other
names and are **not** listed: `ThresholdAlert` became `AlarmTransform`,
`RateLimiter` became `ThrottleTransform`, and TRANSPOSE mode exists as
`CSVSource(replay=, speed_factor=)`.

## Housekeeping

[#17](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/17) — the abandoned
`old-devel` branch, tutorial scaffolding at the repository root, and the
`.gitignore` rule that hides every JSON config file.

---

## Directions considered, not committed

Deliberately **not** ticketed. These were explored during design and no decision
was taken; opening issues for them would misrepresent them as planned work.

**Integration** — destinations for external databases (PostgreSQL, Redis);
sources and destinations for message brokers (MQTT, Kafka, AMQP); HTTP and
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
