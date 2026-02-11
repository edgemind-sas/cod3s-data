# COD3S Observatory - Design Decisions (QA Spec)

**Version:** 1.0
**Date:** 2026-02-11
**Status:** Complete - All design decisions made

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| - | [Observatory Overview](OBS-00-OVERVIEW.md) | [OBS-00-OVERVIEW →](OBS-00-OVERVIEW.md) |

---

## Table of Contents

- [Purpose](#purpose)
- [Theme 1: Architecture](#theme-1-architecture)
- [Theme 2: Debug & Control](#theme-2-debug--control)
- [Theme 3: Frontend Technology](#theme-3-frontend-technology)
- [Theme 4: Communication Protocol](#theme-4-communication-protocol)
- [Progress Summary](#progress-summary)
- [Key Architectural Decisions Made](#key-architectural-decisions-made)

---

## Purpose

This document records all design decisions made during the Observatory specification process. Each question was discussed and resolved before specification writing began.

**Format:** Each question includes the options considered, the decision made, and the rationale.

---

## Theme 1: Architecture

### Q1.1: Module Integration Strategy

**Question:** Should the Observatory be a separate package or an integrated optional module?

**Options:**
1. **Separate package** (`cod3s-observatory`) — Independent install, own release cycle
2. **Integrated optional module** (`cod3s-data[observatory]`) — Part of main package, optional extras
3. **Hybrid** — Core bridge in main package, frontend as separate package

**Decision:** Option 2 — Integrated optional module `cod3s-data[observatory]`

**Rationale:**
- Single install command: `pip install cod3s-data[observatory]`
- Bridge interface lives alongside framework code — no version sync issues
- Zero overhead when not installed (import guard pattern)
- Simpler development workflow (single repo, single CI)
- The Observatory is tightly coupled to framework internals (hook points in broker, sources)

---

### Q1.2: Backend Framework

**Question:** Which web framework for the Observatory backend?

**Options:**
1. **FastAPI** — Modern, async-native, automatic OpenAPI docs
2. **Starlette** — Lighter, FastAPI is built on it
3. **aiohttp** — Mature, good WebSocket support
4. **Custom** — Minimal WebSocket server only

**Decision:** Option 1 — FastAPI

**Rationale:**
- Already async (matches COD3S event loop)
- WebSocket support built-in
- Automatic API documentation for debugging endpoints
- Large ecosystem and community
- Starlette underneath provides the performance

---

### Q1.3: Server Embedding Strategy

**Question:** How should the web server run relative to the framework?

**Options:**
1. **Embedded** — Uvicorn runs as asyncio task in the framework's event loop
2. **Separate process** — Observatory runs in its own process, communicates via IPC
3. **Thread** — Uvicorn runs in a separate thread with its own event loop

**Decision:** Option 1 — Embedded in framework event loop

**Rationale:**
- Direct memory access to framework state (no serialization overhead)
- Single process to manage
- Shares the asyncio event loop — natural integration
- Implementation: `uvicorn.Server(Config(app, loop="none"))` + `asyncio.create_task(server.serve())`
- Performance impact is minimal (FastAPI is async, non-blocking)

---

### Q1.4: Memory Model

**Question:** How should the Observatory store events and history?

**Options:**
1. **In-memory ring buffers** — Fixed-size, oldest evicted
2. **SQLite** — On-disk persistence, survives restarts
3. **Redis** — External store, shareable
4. **Hybrid** — In-memory primary + optional disk persistence

**Decision:** Option 1 — In-memory ring buffers (V1)

**Rationale:**
- Simplest implementation for V1
- No external dependencies
- Configurable buffer sizes and memory cap (default 50MB)
- Acceptable for debug/development use case
- Persistence can be added in V2 if needed
- Late-connecting frontends get recent history from buffer

---

## Theme 2: Debug & Control

### Q2.1: Observatory Scope

**Question:** Should the Observatory be observation-only or include active control?

**Options:**
1. **Observation only** — View topology, messages, metrics (read-only)
2. **Observation + Control** — Also pause, resume, step, breakpoints (read-write)

**Decision:** Option 2 — Observation + Control

**Rationale:**
- The primary use case is debugging pipelines before deployment
- Step-by-step execution is essential for understanding message flow
- Breakpoints allow targeted investigation
- Control features can be disabled in production via configuration
- The Bridge pattern naturally supports bidirectional communication

---

### Q2.2: Step Granularity

**Question:** What granularity levels should step-by-step debugging support?

**Options:**
1. **Message only** — Pause after each message
2. **Stage only** — Pause after each pipeline stage (source→broker→transform→destination)
3. **Breakpoint only** — Free-running, pause only on conditions
4. **All three levels** — User chooses granularity

**Decision:** Option 4 — All three levels, user chooses

**Rationale:**
- Different debugging scenarios need different granularities
- **MESSAGE**: Fine-grained inspection, useful for low-throughput debugging
- **STAGE**: Understand the flow through the pipeline, see transformations applied
- **BREAKPOINT**: Efficient for high-throughput pipelines, only pause when interesting
- Switchable at runtime via UI or API

---

### Q2.3: Pause Semantics

**Question:** What happens to in-flight messages when the pipeline is paused?

**Options:**
1. **Immediate freeze** — All processing stops instantly (may leave inconsistent state)
2. **Drain then pause** — In-flight messages complete, then pause at source yield points
3. **Checkpoint pause** — Complete current batch, checkpoint state, then pause

**Decision:** Option 2 — Drain then pause

**Rationale:**
- Sources are suspended at their yield points (between messages)
- Messages already in the broker complete their routing
- No inconsistent state or half-processed messages
- Predictable behavior developers can reason about
- Resume picks up cleanly from the paused state

---

### Q2.4: Breakpoint Specification

**Question:** How should breakpoints be defined?

**Options:**
1. **Channel pattern only** — Break on messages matching a channel pattern
2. **Channel + value condition** — Also check message content
3. **Channel + value + component** — Also specify which component triggers
4. **Expression-based** — Arbitrary Python expressions

**Decision:** Option 3 — Channel + value condition + component

**Rationale:**
- Channel patterns reuse existing `SubscriptionRegistry.match_channel()` logic
- Value conditions enable targeted debugging (e.g., temperature > 100)
- Component targeting prevents unnecessary pauses in unrelated parts
- Safer than arbitrary Python expressions (no `eval()`)
- Condition evaluation uses a safe expression parser

---

## Theme 3: Frontend Technology

### Q3.1: Frontend Framework

**Question:** Which JavaScript framework for the Observatory UI?

**Options:**
1. **Vue 3** — Composition API, Vuetify component library, good TypeScript support
2. **React** — Largest ecosystem, many visualization libraries
3. **Svelte** — Minimal bundle, excellent performance
4. **No frontend** — Terminal-based UI only

**Decision:** Option 1 — Vue 3

**Rationale:**
- Vuetify 3 provides a complete, polished component library (Material Design)
- Composition API with TypeScript is clean and productive
- Smaller learning curve than React for the team
- Pinia state management is simpler than Redux
- Vue Flow (@vue-flow/core) provides excellent DAG visualization
- Good performance for real-time updates with reactive system

---

### Q3.2: State Management

**Question:** How should frontend state be managed?

**Options:**
1. **Pinia** — Official Vue 3 store, simple API, TypeScript-first
2. **Vuex 4** — Legacy Vue store, more boilerplate
3. **No store** — Component-level state + composables only

**Decision:** Option 1 — Pinia

**Rationale:**
- Official recommendation for Vue 3 (Vuex is legacy)
- TypeScript-first design
- Simpler API than Vuex (no mutations concept)
- Composable-friendly
- DevTools integration for debugging stores

---

### Q3.3: Frontend Distribution

**Question:** How should the frontend be distributed?

**Options:**
1. **Bundled in Python package** — Vite builds to `dist/`, copied to `cod3s_data/observatory/static/`
2. **Separate npm package** — User installs frontend separately
3. **CDN-served** — Frontend loaded from CDN, only API in Python package

**Decision:** Option 1 — Bundled in Python package

**Rationale:**
- Single `pip install cod3s-data[observatory]` installs everything
- No Node.js required for end users
- Works offline (no CDN dependency)
- Version-locked with backend (no compatibility issues)
- Build step is part of the library CI, not the user's responsibility

---

### Q3.4: DAG Visualization Library

**Question:** Which library for pipeline topology (DAG) visualization?

**Options:**
1. **@vue-flow/core** — Vue-native, based on React Flow, dagre layout
2. **cytoscape.js** — Mature, many layouts, framework-agnostic
3. **D3.js** — Maximum flexibility, steep learning curve
4. **mermaid** — Simple, limited interactivity

**Decision:** Option 1 — @vue-flow/core

**Rationale:**
- Native Vue 3 integration (reactive props, slots, events)
- Built-in interactive features (drag, zoom, minimap)
- Custom node/edge components with Vue slots
- dagre layout for automatic DAG arrangement
- Active development, good TypeScript support
- Better developer experience than cytoscape.js for Vue projects

---

## Theme 4: Communication Protocol

### Q4.1: Real-Time Protocol

**Question:** Which protocol for real-time communication between backend and frontend?

**Options:**
1. **WebSocket** — Bidirectional, low latency, single connection
2. **Server-Sent Events (SSE)** — Server→client only, simpler, HTTP-based
3. **HTTP polling** — Simple, high latency, high overhead
4. **WebSocket + REST hybrid** — WebSocket for events, REST for commands

**Decision:** Option 1 — WebSocket (bidirectional)

**Rationale:**
- Commands (pause, step, breakpoints) need client→server direction
- Events (topology updates, messages, metrics) need server→client direction
- Single connection reduces overhead vs polling
- Lower latency than SSE for bidirectional communication
- FastAPI has built-in WebSocket support
- Natural fit for real-time debugging

---

### Q4.2: Serialization Format

**Question:** What serialization format for WebSocket messages?

**Options:**
1. **JSON** — Human-readable, universal, easy to debug
2. **MessagePack** — Binary, smaller, faster
3. **Protocol Buffers** — Schema-enforced, binary
4. **JSON with optional binary upgrade** — Start JSON, optimize later

**Decision:** Option 1 — JSON

**Rationale:**
- Human-readable — essential for debugging a debugging tool
- Browser-native (no decoder needed)
- Performance is adequate for debug-rate message volumes
- Easy to inspect in browser DevTools
- msgspec can be used server-side for fast JSON serialization
- Binary optimization can be added in V2 if needed

---

### Q4.3: Multi-Client Support

**Question:** Should the Observatory support multiple simultaneous browser clients?

**Options:**
1. **Single client** — One browser at a time
2. **Multiple clients** — Multiple browsers, all see the same state
3. **Multiple clients with roles** — Viewers and controllers

**Decision:** Option 2 — Multiple clients, same state

**Rationale:**
- Pair debugging (one person drives, another observes)
- No complexity of role management in V1
- All clients see the same debug state (pause affects everyone)
- Heartbeat (30s) manages connection lifecycle
- Automatic reconnection for dropped connections

---

## Progress Summary

**Completed Themes:** 4/4
**Completed Questions:** 13/13
**Status:** All design decisions made. Ready for specification writing.

---

## Key Architectural Decisions Made

1. **Integration:** Optional module `cod3s-data[observatory]`, not a separate package
2. **Backend:** FastAPI + Uvicorn embedded in the framework's asyncio event loop
3. **Bridge:** Single point of contact between framework and observatory (hook-based)
4. **Memory:** In-memory ring buffers, configurable cap (50MB default), no disk persistence in V1
5. **Debug Scope:** Observation + active control (pause, resume, step, breakpoints)
6. **Granularity:** 3 levels — MESSAGE, STAGE, BREAKPOINT — switchable at runtime
7. **Pause Semantics:** Drain in-flight messages, suspend sources at yield points
8. **Frontend:** Vue 3 + Vuetify 3 + Pinia + TypeScript, bundled in the Python package
9. **DAG Visualization:** @vue-flow/core with dagre layout
10. **Protocol:** WebSocket bidirectional, JSON serialization
11. **Multi-client:** Supported, all clients share the same debug state

---

## Deferred to V2

- Disk persistence for event history
- Authentication and access control
- Remote Observatory (connect to framework on different machine)
- Multi-instance monitoring (observe multiple framework instances)
- Binary WebSocket protocol (MessagePack optimization)
- Role-based multi-client (viewer vs controller)

---

**Last Updated:** 2026-02-11 (after Q4.3 - All decisions complete)
