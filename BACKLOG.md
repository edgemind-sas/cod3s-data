# Backlog

The backlog lives in the **[issue tracker](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues)**.
Everything below was opened there on 2026-08-24, after being verified against the
code; this page is an index, not a second copy.

Why an index rather than nothing: a clone should be able to say what is known to
be broken without network access. Why not the full text: two places tracking the
same work drift apart, which is the failure this repository has just spent a
cleanup recovering from.

## Defects

| # | | |
|---|---|---|
| [#1](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/1) | An installed package has no Observatory UI | `défaut` `empaquetage` |
| [#2](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/2) | `msgspec` is a required dependency, imported nowhere | `défaut` `empaquetage` |
| [#3](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/3) | The pandas fallback cannot run on a clean install | `défaut` `empaquetage` |
| [#4](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/4) | `observatory/models/` is dead code | `défaut` |
| [#5](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/5) | The timeline renders SVG where canvas was decided | `défaut` |

#1 is the one to read first: `pip install 'cod3s-data[observatory]'` gives a
working API and a 404 on every page, and it is invisible from a clone.

## Tests and CI

| # | | |
|---|---|---|
| [#6](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/6) | The Observatory HTTP/WebSocket surface is barely tested | `tests` |
| [#7](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/7) | InfluxDB integration tests never run in CI | `tests` |
| [#8](https://gitlab.edgemind.net/cod3s/cod3s-data/-/issues/8) | 28 public methods have no docstring | `chore` |

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
