# Observatory Technical Specification - Overview

**Document:** OBS-TECH-00-OVERVIEW.md
**Version:** 1.0.0
**Date:** 2026-02-11
**Status:** Draft
**Purpose:** Technical specification index, navigation, and technology stack summary

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← Functional Spec](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-00-OVERVIEW.md) | [TECH-00-OVERVIEW](../TECH-00-OVERVIEW.md) | [OBS-TECH-01 →](OBS-TECH-01-BACKEND-ARCHITECTURE.md) |

---

## Table of Contents

1. [Introduction](#introduction)
2. [Document Map](#document-map)
3. [Technology Stack](#technology-stack)
4. [Dependencies](#dependencies)
5. [Traceability Matrix](#traceability-matrix)
6. [Reading Guide](#reading-guide)

---

## Introduction

### Purpose

This technical specification suite provides **implementation-ready guidance** for building the COD3S Observatory module. It specifies:

- Backend architecture (FastAPI, WebSocket, static serving)
- Bridge implementation (hooks, debug controller, breakpoint evaluator)
- WebSocket protocol (message format, events, commands)
- Frontend architecture (Vue 3, Pinia stores, composables)
- Component library (DAG, timeline, inspector, metrics)
- State management (Pinia store design)
- Testing strategy (backend + frontend)

### Target Audience

- **Backend Implementers** — Developers building the Python observatory package
- **Frontend Implementers** — Developers building the Vue 3 dashboard
- **Framework Integrators** — Developers adding bridge hooks to the core framework
- **Technical Reviewers** — Architects validating design decisions

### Relationship to Functional Specification

The [Observatory Functional Specification](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-00-OVERVIEW.md) defines **what** the Observatory must do. This technical specification defines **how** to implement it.

### Relationship to Framework Technical Specification

The Observatory extends the framework specified in the [V1.0 Technical Specification](../TECH-00-OVERVIEW.md). Key framework documents:

- [TECH-01-ARCHITECTURE](../TECH-01-ARCHITECTURE.md) — AsyncIO concurrency model the Observatory integrates with
- [TECH-03-BROKER-API](../TECH-03-BROKER-API.md) — Broker API where observation hooks are inserted
- [TECH-04-SOURCES-API](../TECH-04-SOURCES-API.md) — Source API where debug pause points are added
- [TECH-08-OBSERVABILITY-API](../TECH-08-OBSERVABILITY-API.md) — Metrics infrastructure the Observatory consumes

---

## Document Map

### Backend Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | Index, tech stack (this document) | Draft |
| [OBS-TECH-01-BACKEND-ARCHITECTURE](OBS-TECH-01-BACKEND-ARCHITECTURE.md) | FastAPI app, endpoints, Uvicorn embedding, static serving | Draft |
| [OBS-TECH-02-BRIDGE-API](OBS-TECH-02-BRIDGE-API.md) | Bridge class, debug controller, breakpoint evaluator, event buffer | Draft |
| [OBS-TECH-03-WEBSOCKET-PROTOCOL](OBS-TECH-03-WEBSOCKET-PROTOCOL.md) | Message format, events, commands, error codes | Draft |

### Frontend Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [OBS-TECH-04-FRONTEND-ARCHITECTURE](OBS-TECH-04-FRONTEND-ARCHITECTURE.md) | Vue project structure, routing, composables | Draft |
| [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md) | PipelineGraph, TimelineChart, MessageDetail, MetricCard, DebugControls | Draft |
| [OBS-TECH-06-STATE-MANAGEMENT](OBS-TECH-06-STATE-MANAGEMENT.md) | Pinia stores, data flow, persistence | Draft |

### Cross-Cutting Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [OBS-TECH-07-TESTING](OBS-TECH-07-TESTING.md) | Backend + frontend test strategy, fixtures | Draft |
| [OBS-TECH-APPENDIX-A-DECISIONS](OBS-TECH-APPENDIX-A-DECISIONS.md) | Technical decision log (5 decisions) | Draft |

### Recommended Reading Order

**For Backend Implementers:**
1. OBS-TECH-00-OVERVIEW (this document)
2. OBS-TECH-APPENDIX-A-DECISIONS (understand key choices)
3. OBS-TECH-02-BRIDGE-API (core bridge implementation)
4. OBS-TECH-03-WEBSOCKET-PROTOCOL (data contract)
5. OBS-TECH-01-BACKEND-ARCHITECTURE (FastAPI app structure)
6. OBS-TECH-07-TESTING (backend tests)

**For Frontend Implementers:**
1. OBS-TECH-00-OVERVIEW (this document)
2. OBS-TECH-03-WEBSOCKET-PROTOCOL (data contract)
3. OBS-TECH-04-FRONTEND-ARCHITECTURE (project structure)
4. OBS-TECH-06-STATE-MANAGEMENT (Pinia stores)
5. OBS-TECH-05-COMPONENT-LIBRARY (Vue components)
6. OBS-TECH-07-TESTING (frontend tests)

**For Framework Integrators:**
1. OBS-TECH-00-OVERVIEW (this document)
2. OBS-TECH-02-BRIDGE-API (hook points, integration pattern)
3. OBS-TECH-01-BACKEND-ARCHITECTURE (embedding pattern)

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.12+ | Runtime (same as framework) |
| **FastAPI** | 0.115+ | Web framework (REST + WebSocket) |
| **Uvicorn** | 0.34+ | ASGI server (embedded in event loop) |
| **websockets** | 14.0+ | WebSocket protocol implementation |
| **Pydantic v2** | 2.9+ | Data models and validation (shared with framework) |
| **msgspec** | 0.18+ | High-performance JSON serialization |

### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| **Vue 3** | 3.5+ | UI framework (Composition API) |
| **Vuetify 3** | 3.7+ | Material Design component library |
| **Pinia** | 2.3+ | State management |
| **TypeScript** | 5.6+ | Type-safe JavaScript |
| **Vite** | 6+ | Build tool and dev server |
| **@vue-flow/core** | 1.x | DAG visualization |
| **Chart.js** | 4.x | Metric charts (line, bar, gauge) |
| **vue-chartjs** | 5.x | Vue 3 wrapper for Chart.js |

### Build & Distribution

| Technology | Purpose |
|-----------|---------|
| **Vite** | Frontend build → `dist/` |
| **Python package** | Frontend dist bundled in `cod3s_data/observatory/static/` |
| **No Node.js for users** | Pre-built frontend distributed with pip package |

---

## Dependencies

### Python Optional Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
observatory = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "websockets>=14.0",
]
```

**Total additional dependencies:** 3 (+ their transitive deps)

**Note:** Pydantic and msgspec are already framework dependencies — no duplication.

### Frontend Dependencies (Build-Time Only)

```json
{
  "dependencies": {
    "vue": "^3.5.0",
    "vuetify": "^3.7.0",
    "pinia": "^2.3.0",
    "@vue-flow/core": "^1.0.0",
    "@vue-flow/background": "^1.0.0",
    "@vue-flow/minimap": "^1.0.0",
    "@vue-flow/controls": "^1.0.0",
    "chart.js": "^4.0.0",
    "vue-chartjs": "^5.0.0",
    "vue-router": "^4.0.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "@vitejs/plugin-vue": "^5.0.0",
    "vitest": "^2.0.0",
    "@vue/test-utils": "^2.0.0",
    "playwright": "^1.40.0"
  }
}
```

These dependencies are only needed at **build time** (CI). End users install the pre-built static files via pip.

---

## Traceability Matrix

### Functional → Technical Mapping

| Functional Spec | Technical Spec | Coverage |
|-----------------|----------------|----------|
| [OBS-00-OVERVIEW](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-00-OVERVIEW.md) | OBS-TECH-00-OVERVIEW | Scope, stack |
| [OBS-01-ARCHITECTURE](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-01-ARCHITECTURE.md) | [OBS-TECH-01-BACKEND-ARCHITECTURE](OBS-TECH-01-BACKEND-ARCHITECTURE.md) | Server embedding, module pattern |
| [OBS-02-BRIDGE](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-02-BRIDGE.md) | [OBS-TECH-02-BRIDGE-API](OBS-TECH-02-BRIDGE-API.md) | Bridge class, hooks, debug controller, breakpoints |
| [OBS-03-DEBUG-CONTROLS](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-03-DEBUG-CONTROLS.md) | [OBS-TECH-02-BRIDGE-API](OBS-TECH-02-BRIDGE-API.md) | Debug controller, state machine |
| [OBS-04-PIPELINE-TOPOLOGY](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-04-PIPELINE-TOPOLOGY.md) | [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md) | PipelineGraph component |
| [OBS-05-TEMPORAL-TIMELINE](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-05-TEMPORAL-TIMELINE.md) | [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md) | TimelineChart component |
| [OBS-06-MESSAGE-INSPECTOR](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-06-MESSAGE-INSPECTOR.md) | [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md) | MessageDetail component |
| [OBS-07-METRICS-DASHBOARD](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-07-METRICS-DASHBOARD.md) | [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md) | MetricCard component |
| [OBS-08-CONFIGURATION](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-08-CONFIGURATION.md) | [OBS-TECH-01-BACKEND-ARCHITECTURE](OBS-TECH-01-BACKEND-ARCHITECTURE.md) | Config model, env vars |
| - (cross-cutting) | [OBS-TECH-03-WEBSOCKET-PROTOCOL](OBS-TECH-03-WEBSOCKET-PROTOCOL.md) | Communication contract |
| - (cross-cutting) | [OBS-TECH-04-FRONTEND-ARCHITECTURE](OBS-TECH-04-FRONTEND-ARCHITECTURE.md) | Vue project structure |
| - (cross-cutting) | [OBS-TECH-06-STATE-MANAGEMENT](OBS-TECH-06-STATE-MANAGEMENT.md) | Pinia stores |
| - (cross-cutting) | [OBS-TECH-07-TESTING](OBS-TECH-07-TESTING.md) | Test strategy |

### QA_SPEC Decision Coverage

All 13 decisions in [QA_SPEC_OBSERVATORY](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/QA_SPEC_OBSERVATORY.md) are addressed:

| QA Decision | Technical Spec | Implementation |
|-------------|----------------|----------------|
| Q1.1 (Module strategy) | OBS-TECH-01 | Optional extras in pyproject.toml |
| Q1.2 (Backend framework) | OBS-TECH-01 | FastAPI application |
| Q1.3 (Server embedding) | OBS-TECH-01 | Uvicorn asyncio task |
| Q1.4 (Memory model) | OBS-TECH-02 | EventBuffer ring buffer |
| Q2.1 (Observation + control) | OBS-TECH-02 | Bridge bidirectional interface |
| Q2.2 (Step granularity) | OBS-TECH-02 | DebugController.step_next() |
| Q2.3 (Pause semantics) | OBS-TECH-02 | asyncio.Event synchronization |
| Q2.4 (Breakpoints) | OBS-TECH-02 | BreakpointEvaluator |
| Q3.1 (Frontend framework) | OBS-TECH-04 | Vue 3 + Vuetify 3 |
| Q3.2 (State management) | OBS-TECH-06 | Pinia stores |
| Q3.3 (Frontend distribution) | OBS-TECH-01 | Static files in package |
| Q3.4 (DAG library) | OBS-TECH-05 | @vue-flow/core |
| Q4.1 (Protocol) | OBS-TECH-03 | WebSocket bidirectional |
| Q4.2 (Serialization) | OBS-TECH-03 | JSON format |
| Q4.3 (Multi-client) | OBS-TECH-03 | WebSocket manager broadcast |

**Coverage:** 100% of Observatory design decisions

---

## Reading Guide

### Code Example Conventions

All code examples follow the framework conventions defined in [TECH-00-OVERVIEW](../TECH-00-OVERVIEW.md):

- **Python:** Type hints (3.12+ syntax), async/await, Pydantic models, Google-style docstrings
- **TypeScript:** Strict mode, Vue Composition API, interface-first design
- **JSON:** WebSocket protocol messages with full schemas

### Package Structure Preview

```
cod3s_data/
├── observatory/           # Observatory package (optional)
│   ├── __init__.py       # create_observatory() entry point
│   ├── app.py            # FastAPI application
│   ├── bridge.py         # ObservatoryBridge implementation
│   ├── config.py         # ObservatoryConfig (Pydantic)
│   ├── debug.py          # DebugController, BreakpointEvaluator
│   ├── buffer.py         # EventBuffer (ring buffer)
│   ├── sampler.py        # MessageSampler
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py     # GET /api/health
│   │   ├── topology.py   # GET /api/topology
│   │   ├── debug.py      # POST/DELETE /api/debug/breakpoints
│   │   └── websocket.py  # WebSocket /ws
│   ├── models/
│   │   ├── __init__.py
│   │   ├── events.py     # WebSocket event models
│   │   └── commands.py   # WebSocket command models
│   └── static/           # Pre-built Vue 3 frontend
│       ├── index.html
│       └── assets/
│           ├── index-[hash].js
│           └── index-[hash].css
```

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-11 | 1.0.0 | Initial Observatory technical specification overview |

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← Functional Spec](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-00-OVERVIEW.md) | [TECH-00-OVERVIEW](../TECH-00-OVERVIEW.md) | [OBS-TECH-01 →](OBS-TECH-01-BACKEND-ARCHITECTURE.md) |
