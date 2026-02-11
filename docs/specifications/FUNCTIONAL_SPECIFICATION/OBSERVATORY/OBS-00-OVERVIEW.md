# COD3S Observatory - Overview

**Version:** 1.0
**Date:** 2026-02-11
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← Framework Overview](../00-OVERVIEW.md) | [README](../../README.md) | [OBS-01-ARCHITECTURE →](OBS-01-ARCHITECTURE.md) |

**Observatory Documents:**
- [Architecture](OBS-01-ARCHITECTURE.md) | [Bridge](OBS-02-BRIDGE.md) | [Debug Controls](OBS-03-DEBUG-CONTROLS.md)
- [Pipeline Topology](OBS-04-PIPELINE-TOPOLOGY.md) | [Temporal Timeline](OBS-05-TEMPORAL-TIMELINE.md)
- [Message Inspector](OBS-06-MESSAGE-INSPECTOR.md) | [Metrics Dashboard](OBS-07-METRICS-DASHBOARD.md)
- [Configuration](OBS-08-CONFIGURATION.md) | [Glossary](OBS-99-GLOSSARY.md)

**Technical Specification:**
- [Tech Overview](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-00-OVERVIEW.md)

---

## Table of Contents

- [What is COD3S Observatory?](#what-is-cod3s-observatory)
- [Value Proposition](#value-proposition)
- [Scope V1](#scope-v1)
- [Document Map](#document-map)
- [Reading Guide](#reading-guide)
- [Roadmap](#roadmap)
- [Related Documents](#related-documents)

---

## What is COD3S Observatory?

COD3S Observatory is an **optional web-based observability and debug module** for the COD3S Data framework. It provides a visual interface for understanding, debugging, and controlling data pipelines in real time.

**Core Concept:** Embed a lightweight web server (FastAPI + Vue 3) directly into the framework's event loop, providing a browser-based dashboard that visualizes pipeline topology, traces message flow, and enables interactive debugging — all without modifying the pipeline code.

**Installation:**

```bash
# Install framework with Observatory support
pip install cod3s-data[observatory]

# Or with uv
uv pip install cod3s-data[observatory]
```

**Activation:**

```python
# Python
framework = Framework(config, observatory=True)
```

```yaml
# YAML
observatory:
  enabled: true
```

**Key Principle:** The framework functions identically with or without Observatory. When not installed, there is zero overhead — no imports, no hooks, no performance impact.

---

## Value Proposition

### Problems Solved

1. **Opaque pipeline behavior** — Difficult to understand how messages flow through sources, transformations, and destinations without visual tools
2. **Print-debugging limitations** — Log-based debugging cannot show topology, timing, or message relationships
3. **No interactive control** — Cannot pause, step, or set breakpoints on a running pipeline
4. **Metrics scattered** — Framework metrics exist on `_metrics.*` channels but lack visual aggregation
5. **Onboarding friction** — New developers struggle to understand complex pipeline configurations

### Benefits

| Stakeholder | Key Benefits |
|-------------|-------------|
| **Pipeline Developers** | Visual DAG, step-by-step debugging, message inspection |
| **Data Engineers** | Temporal timeline, message tracing, transformation I/O diff |
| **Operations** | Real-time metrics dashboard, error tracking, throughput monitoring |
| **New Team Members** | Visual pipeline understanding, interactive exploration |

### Before vs After

| Task | Without Observatory | With Observatory |
|------|-------------------|-----------------|
| Understand pipeline topology | Read YAML config, trace code | View interactive DAG in browser |
| Debug message flow | Add print/log statements, restart | Set breakpoint, step through, inspect |
| Find transformation bugs | Compare input/output in logs | Side-by-side message diff in inspector |
| Monitor performance | Subscribe to `_metrics.*` channels | Live dashboard with charts |
| Trace a specific message | grep logs by trace_id | Click message in timeline, see full journey |

---

## Scope V1

### In Scope

| Feature | Description | Document |
|---------|-------------|----------|
| **Pipeline Topology** | Interactive DAG visualization of sources, transforms, destinations, channels | [OBS-04](OBS-04-PIPELINE-TOPOLOGY.md) |
| **Temporal Timeline** | Chrome DevTools-style timeline of message flow over time | [OBS-05](OBS-05-TEMPORAL-TIMELINE.md) |
| **Message Inspector** | Detailed message inspection with tree view, tags, journey, JSON | [OBS-06](OBS-06-MESSAGE-INSPECTOR.md) |
| **Metrics Dashboard** | Real-time charts for throughput, latency, errors, buffer utilization | [OBS-07](OBS-07-METRICS-DASHBOARD.md) |
| **Debug Controls** | Pause, resume, step (3 granularities), slow-motion, breakpoints | [OBS-03](OBS-03-DEBUG-CONTROLS.md) |
| **Bridge API** | Hook-based interface between framework and observatory | [OBS-02](OBS-02-BRIDGE.md) |
| **Configuration** | YAML, Python, and environment variable configuration | [OBS-08](OBS-08-CONFIGURATION.md) |

### Not in Scope (V1)

| Feature | Reason | Planned |
|---------|--------|---------|
| Disk persistence | Complexity, not needed for debug use case | V2 |
| Authentication / authorization | Local-only use in V1 (127.0.0.1) | V2 |
| Remote Observatory | Requires network security, auth | V2 |
| Multi-instance monitoring | Observe multiple frameworks from one UI | V2 |
| Custom dashboard layouts | Drag-and-drop widget arrangement | V2 |
| Alert rules in Observatory | Use existing framework alerting mechanisms | V2 |

---

## Document Map

### Functional Specification (this directory)

```
OBS-00-OVERVIEW.md            ← You are here
│
├── OBS-01-ARCHITECTURE.md     Architecture, module pattern, embedding
├── OBS-02-BRIDGE.md           Bridge API (framework ↔ observatory)
├── OBS-03-DEBUG-CONTROLS.md   Pause, step, breakpoints, slow-motion
│
├── OBS-04-PIPELINE-TOPOLOGY.md   DAG visualization
├── OBS-05-TEMPORAL-TIMELINE.md   Timeline visualization
├── OBS-06-MESSAGE-INSPECTOR.md   Message detail view
├── OBS-07-METRICS-DASHBOARD.md   Metrics charts
│
├── OBS-08-CONFIGURATION.md    YAML, Python, env vars configuration
├── OBS-99-GLOSSARY.md         Observatory-specific terminology
│
└── QA_SPEC_OBSERVATORY.md     Design decisions (source of truth)
```

### Technical Specification

```
OBS-TECH-00-OVERVIEW.md              Tech stack, traceability
├── OBS-TECH-01-BACKEND-ARCHITECTURE.md   FastAPI, endpoints, static serving
├── OBS-TECH-02-BRIDGE-API.md             Bridge implementation, debug controller
├── OBS-TECH-03-WEBSOCKET-PROTOCOL.md     Message format, events, commands
├── OBS-TECH-04-FRONTEND-ARCHITECTURE.md  Vue project structure, routing
├── OBS-TECH-05-COMPONENT-LIBRARY.md      Vue components (DAG, timeline, etc.)
├── OBS-TECH-06-STATE-MANAGEMENT.md       Pinia stores
├── OBS-TECH-07-TESTING.md                Test strategy (backend + frontend)
└── OBS-TECH-APPENDIX-A-DECISIONS.md      Technical decision log
```

---

## Reading Guide

### For Pipeline Developers

**Goal:** Debug and inspect pipelines during development

**Recommended Path:**
1. This overview (you are here)
2. [Architecture](OBS-01-ARCHITECTURE.md) — How Observatory integrates
3. [Debug Controls](OBS-03-DEBUG-CONTROLS.md) — Pause, step, breakpoints
4. [Pipeline Topology](OBS-04-PIPELINE-TOPOLOGY.md) — Visual DAG
5. [Message Inspector](OBS-06-MESSAGE-INSPECTOR.md) — Message details
6. [Configuration](OBS-08-CONFIGURATION.md) — How to enable

**Time Investment:** 1-2 hours

### For Operations / Monitoring

**Goal:** Monitor pipeline health and performance

**Recommended Path:**
1. This overview
2. [Architecture](OBS-01-ARCHITECTURE.md) — Deployment impact
3. [Metrics Dashboard](OBS-07-METRICS-DASHBOARD.md) — Charts and monitoring
4. [Temporal Timeline](OBS-05-TEMPORAL-TIMELINE.md) — Message flow analysis
5. [Configuration](OBS-08-CONFIGURATION.md) — Setup and tuning

**Time Investment:** 1 hour

### For Frontend Contributors

**Goal:** Extend or customize the Observatory UI

**Recommended Path:**
1. This overview
2. [Architecture](OBS-01-ARCHITECTURE.md) — System design
3. [Bridge](OBS-02-BRIDGE.md) — API contract
4. [Tech Overview](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-00-OVERVIEW.md) — Tech stack
5. [Frontend Architecture](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-04-FRONTEND-ARCHITECTURE.md) — Vue project structure
6. [Component Library](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-05-COMPONENT-LIBRARY.md) — Vue components
7. [WebSocket Protocol](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-03-WEBSOCKET-PROTOCOL.md) — Data format

**Time Investment:** 2-3 hours

---

## Roadmap

### Observatory V1 — Debug & Inspect (Current Specification)

**Focus:** Local development debugging and pipeline inspection

- Interactive pipeline topology (DAG)
- Temporal message timeline
- Message inspection and comparison
- Debug controls (pause, step, breakpoints)
- Real-time metrics dashboard
- In-memory event buffering
- Single-machine deployment (127.0.0.1)

### Observatory V2 — Persistence & Remote (Future)

**Focus:** Production monitoring and remote access

- Event persistence to disk (SQLite or similar)
- Authentication and access control (API keys, OIDC)
- Remote access (bind to 0.0.0.0, TLS)
- Multi-instance monitoring
- Custom dashboard layouts
- Binary WebSocket protocol (MessagePack)
- Alert rules and notifications in UI

### Observatory V3+ — Advanced (Ideas)

**Focus:** Team collaboration and advanced analysis

- Shared debug sessions (collaborative debugging)
- Pipeline diff (compare two pipeline runs)
- Anomaly detection on metrics
- Record/replay integration (replay messages through Observatory)
- Plugin system for custom visualizations

---

## Related Documents

### Framework V1.0 Specifications

- [10-OBSERVABILITY.md](../10-OBSERVABILITY.md) — Framework observability (metrics-as-messages, logging, tracing)
- [02-ARCHITECTURE.md](../02-ARCHITECTURE.md) — Framework architecture (components, data flow)
- [08-BROKER.md](../08-BROKER.md) — Broker design (channels, subscriptions, publishing)
- [09-CONFIGURATION.md](../09-CONFIGURATION.md) — Configuration system (YAML, Python, env vars)
- [13-FUTURE-V2-V3.md](../13-FUTURE-V2-V3.md) — Framework roadmap

### Design Decisions

- [QA_SPEC_OBSERVATORY.md](QA_SPEC_OBSERVATORY.md) — All Observatory design decisions

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← Framework Overview](../00-OVERVIEW.md) | [README](../../README.md) | [OBS-01-ARCHITECTURE →](OBS-01-ARCHITECTURE.md) |

---

*This is a functional specification document for the COD3S Observatory module. Technical implementation details are in the [Technical Specification](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-00-OVERVIEW.md).*
