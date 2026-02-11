# Observatory Technical Decisions Log

**Document:** OBS-TECH-APPENDIX-A-DECISIONS.md
**Version:** 1.0.0
**Date:** 2026-02-11
**Status:** Draft
**Purpose:** Record and justify key technical implementation decisions

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-TECH-07](OBS-TECH-07-TESTING.md) | [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | - |

---

## Table of Contents

1. [OBS-T1: Embedded FastAPI vs Separate Process](#obs-t1-embedded-fastapi-vs-separate-process)
2. [OBS-T2: Vue Flow vs Cytoscape.js for DAG](#obs-t2-vue-flow-vs-cytoscapejs-for-dag)
3. [OBS-T3: Canvas vs SVG for Timeline](#obs-t3-canvas-vs-svg-for-timeline)
4. [OBS-T4: JSON vs MessagePack on WebSocket](#obs-t4-json-vs-messagepack-on-websocket)
5. [OBS-T5: Frontend Bundled vs Separate Deployment](#obs-t5-frontend-bundled-vs-separate-deployment)

---

## OBS-T1: Embedded FastAPI vs Separate Process

**Decision:** Embed FastAPI/Uvicorn in the framework's asyncio event loop

**Date:** 2026-02-11

### Context

The Observatory backend needs a web server to serve the REST API, WebSocket endpoint, and static frontend files. The question is how this server relates to the framework process.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Embedded (chosen)** | Direct memory access, single process, shared event loop | Could affect framework performance if overloaded |
| **Separate process** | Complete isolation, crash-independent | IPC overhead, state synchronization complexity, harder deployment |
| **Thread** | Isolation + same process | GIL contention, separate event loop synchronization |

### Decision Rationale

1. **Direct memory access:** The bridge needs to read framework state (topology, component states, message buffers). In-process access avoids serialization/IPC overhead.

2. **Uvicorn supports `loop="none"`:** This allows running Uvicorn as an asyncio task within an existing event loop, avoiding a second event loop.

3. **Minimal impact:** FastAPI is async-native. Observatory requests don't block the framework's event loop. Under normal operation (1-5 WebSocket clients, <100 req/s), the server overhead is <1% CPU.

4. **Failure isolation:** Bridge hooks catch all exceptions — a FastAPI crash cannot propagate to the framework. The `try/except` guard in each hook ensures this.

5. **Single deployment:** Users run one process (`python pipeline.py`), not two. No process management or IPC configuration needed.

### Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Observatory overloads event loop | Sampling reduces message rate; Observatory work is minimal (buffer write + broadcast) |
| Uvicorn crash takes down framework | Not possible — Uvicorn runs as a background task; its failure is caught |
| Port conflict prevents startup | Graceful fallback — log warning and continue without Observatory |

### References

- [QA_SPEC Q1.3](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/QA_SPEC_OBSERVATORY.md#q13-server-embedding-strategy)
- [OBS-TECH-01-BACKEND-ARCHITECTURE](OBS-TECH-01-BACKEND-ARCHITECTURE.md#uvicorn-embedding)

---

## OBS-T2: Vue Flow vs Cytoscape.js for DAG

**Decision:** Use @vue-flow/core for DAG visualization

**Date:** 2026-02-11

### Context

The pipeline topology must be displayed as an interactive directed acyclic graph (DAG) with custom node rendering, animations, and real-time updates.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **@vue-flow/core (chosen)** | Native Vue 3, custom nodes via slots, built-in minimap/controls, dagre layout | Newer library, smaller community than cytoscape |
| **cytoscape.js** | Mature (10+ years), many layout algorithms, framework-agnostic | No Vue reactivity, imperative API, custom nodes harder |
| **D3.js** | Maximum flexibility, any visualization | Steep learning curve, everything from scratch |
| **vis-network** | Easy to use, good defaults | Limited customization, not Vue-native |

### Decision Rationale

1. **Vue-native reactivity:** @vue-flow nodes and edges are reactive Vue props. When the topology store updates, the graph updates automatically. No manual DOM manipulation.

2. **Custom nodes via slots:** Each node type (source, transform, destination) is a Vue component rendered via `<template #node-source>`. This allows Vuetify components, state-based styling, and breakpoint indicators inside nodes.

3. **Built-in features:** Minimap, controls (zoom/fit), background grid, and edge animations are available as plugins.

4. **dagre layout:** Automatic left-to-right DAG layout via dagre, with manual position override for user customization.

5. **TypeScript support:** Full type definitions included.

### Trade-offs

- cytoscape.js has more layout algorithms (CoSE, COSE-Bilkent, cola, etc.), but dagre is sufficient for pipeline DAGs which are typically small (<50 nodes).
- @vue-flow is based on React Flow (which has >20K GitHub stars), adapted for Vue 3.

### References

- [QA_SPEC Q3.4](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/QA_SPEC_OBSERVATORY.md#q34-dag-visualization-library)
- [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md#pipelinegraph)

---

## OBS-T3: Canvas vs SVG for Timeline

**Decision:** Use HTML5 Canvas for the temporal timeline

**Date:** 2026-02-11

### Context

The temporal timeline displays thousands of message markers on a time axis with swim lanes per component. Performance at scale is critical.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Canvas (chosen)** | Fast rendering (GPU), handles 10K+ elements, virtual rendering | No DOM events per element, manual hit testing, custom rendering code |
| **SVG** | DOM events on each element, easier styling, accessibility | Slow with >1000 elements, no virtualization, DOM overhead |
| **WebGL (via PixiJS)** | Fastest rendering (100K+ elements) | Overkill complexity, harder to integrate with Vue, large dependency |
| **CSS/HTML** | Simplest, native accessibility | Worst performance, impossible for real-time at scale |

### Decision Rationale

1. **Performance requirement:** The timeline must render 60 seconds of message history at potentially 1000+ msg/s. At 10,000 visible markers, SVG DOM manipulation becomes a bottleneck.

2. **Virtual rendering:** Canvas allows rendering only the visible time window. Markers outside the viewport are never drawn. Combined with binary search for time ranges, this gives O(log n + visible) render cost.

3. **Zoom flexibility:** Canvas rendering can switch between individual markers (zoomed in) and density heatmaps (zoomed out) without changing the rendering model.

4. **requestAnimationFrame:** Smooth 60fps updates for live tail mode.

5. **Hit testing:** Click detection is handled by recording marker positions and doing point-in-rectangle checks — a well-known pattern for Canvas interactivity.

### Trade-offs

- SVG would give free DOM events (click, hover) per marker, but at the cost of performance.
- Canvas requires manual accessibility considerations (ARIA labels on the container, keyboard navigation).

### References

- [OBS-05-TEMPORAL-TIMELINE](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/OBS-05-TEMPORAL-TIMELINE.md)
- [OBS-TECH-05-COMPONENT-LIBRARY](OBS-TECH-05-COMPONENT-LIBRARY.md#timelinechart)

---

## OBS-T4: JSON vs MessagePack on WebSocket

**Decision:** Use JSON for WebSocket message serialization

**Date:** 2026-02-11

### Context

WebSocket messages between the backend and frontend need a serialization format. The choice affects performance, debuggability, and complexity.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **JSON (chosen)** | Human-readable, browser-native, debuggable, zero client deps | Larger payload (~2-5x vs binary), slower parsing |
| **MessagePack** | 40-60% smaller payloads, faster parsing | Binary (not human-readable), requires client library, harder to debug |
| **Protocol Buffers** | Schema-enforced, smallest payloads, fast | Schema compilation step, heavy tooling, worst DX for debug tool |
| **CBOR** | Compact, schema-free binary | Less common, requires library, not human-readable |

### Decision Rationale

1. **Debugging a debugger:** The Observatory is a debugging tool. Its own communication protocol should be easily inspectable in browser DevTools. JSON messages appear directly in the Network tab.

2. **Adequate performance:** At debug-rate message volumes (10-100 events/s, not 10K), JSON serialization overhead is negligible. A 200-byte JSON message takes ~10μs to parse — irrelevant at this rate.

3. **Zero client dependencies:** `JSON.parse()` is built into browsers. No `msgpack-lite` or similar library needed.

4. **Server-side performance:** `msgspec.json` on the Python side gives near-binary serialization speed for JSON, reducing server overhead.

5. **V2 option:** MessagePack can be offered as an optional upgrade in V2 for high-frequency metric streams, as a WebSocket subprotocol negotiation.

### Payload Size Comparison

For a typical `message.published` event:

| Format | Size | Parse Time (browser) |
|--------|------|---------------------|
| JSON | ~250 bytes | ~5 μs |
| MessagePack | ~150 bytes | ~8 μs (with library) |
| Protobuf | ~100 bytes | ~3 μs (with generated code) |

At 100 events/s: JSON = 25 KB/s, MessagePack = 15 KB/s — both negligible.

### References

- [QA_SPEC Q4.2](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/QA_SPEC_OBSERVATORY.md#q42-serialization-format)
- [OBS-TECH-03-WEBSOCKET-PROTOCOL](OBS-TECH-03-WEBSOCKET-PROTOCOL.md)

---

## OBS-T5: Frontend Bundled vs Separate Deployment

**Decision:** Bundle the pre-built frontend in the Python package

**Date:** 2026-02-11

### Context

The Vue 3 frontend must be distributed to end users. The question is whether it ships with the Python package or requires separate installation.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Bundled in package (chosen)** | Single `pip install`, works offline, version-locked | Larger package size (+500KB), rebuild needed for frontend changes |
| **Separate npm package** | Independent releases, smaller Python package | Requires Node.js, version sync issues, two install commands |
| **CDN-served** | Smallest package, auto-updates | Requires internet, CORS issues, version mismatch risk |
| **Git submodule** | Clean separation | Complex build process, poor user experience |

### Decision Rationale

1. **User experience:** `pip install cod3s-data[observatory]` is a single command that installs everything. No Node.js, no npm, no additional steps.

2. **Offline support:** The frontend works without internet access. Important for industrial/IoT environments where machines may not have internet.

3. **Version locking:** The frontend and backend are guaranteed to be compatible — they ship together. No version matrix to manage.

4. **Package size impact:** The built frontend is ~500KB gzipped (Vue + Vuetify + Chart.js + @vue-flow). This is a one-time download, acceptable for an optional extra.

5. **Build process:** The frontend is built in CI (GitHub Actions) and the `dist/` output is committed to `cod3s_data/observatory/static/`. No build step for end users.

### Build Pipeline

```
CI Build:
  frontend/ → npm run build → dist/
  dist/ → copy → cod3s_data/observatory/static/
  cod3s_data/ → pip build → wheel
  wheel → pip install cod3s-data[observatory]
```

### References

- [QA_SPEC Q3.3](../../FUNCTIONAL_SPECIFICATION/OBSERVATORY/QA_SPEC_OBSERVATORY.md#q33-frontend-distribution)
- [OBS-TECH-01-BACKEND-ARCHITECTURE](OBS-TECH-01-BACKEND-ARCHITECTURE.md#static-file-serving)

---

## Decision Summary

| ID | Decision | Key Factor |
|----|----------|-----------|
| OBS-T1 | Embedded FastAPI | Direct memory access, single process |
| OBS-T2 | @vue-flow/core | Vue-native reactivity, custom nodes via slots |
| OBS-T3 | Canvas for timeline | Performance at 10K+ markers, virtual rendering |
| OBS-T4 | JSON for WebSocket | Human-readable, debugging a debugger |
| OBS-T5 | Frontend bundled | Single pip install, version-locked, offline |

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-TECH-07](OBS-TECH-07-TESTING.md) | [OBS-TECH-00-OVERVIEW](OBS-TECH-00-OVERVIEW.md) | - |
