# COD3S Observatory - Glossary

**Version:** 1.0
**Date:** 2026-02-11
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-08-CONFIGURATION](OBS-08-CONFIGURATION.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [← Back to Overview](OBS-00-OVERVIEW.md) |

---

## Table of Contents

- [Purpose](#purpose)
- [Glossary](#glossary)
- [Cross-Reference Index](#cross-reference-index)

---

## Purpose

This glossary defines all Observatory-specific terms used throughout the functional and technical specifications. Each term includes:
- A clear definition
- The primary document that introduces the concept
- Related terms and cross-references

**Convention:** Terms are listed in **alphabetical order** for easy reference.

---

## Glossary

### Breakpoint

**Definition:** A conditional pause point in the pipeline that halts execution when a specific channel pattern and optional condition are met. Breakpoints allow developers to inspect messages that match specific criteria without stepping through every message.

**Document:** [OBS-03-DEBUG-CONTROLS](OBS-03-DEBUG-CONTROLS.md)

**Related Terms:** [Debug Controller](#debug-controller), [Granularity](#granularity), [Debug Session](#debug-session)

**Example:** A breakpoint on `sensors.*.temperature` with condition `value > 100` will pause the pipeline when any temperature sensor reports a value above 100.

---

### Bridge

**Definition:** The interface component between the COD3S Data framework and the Observatory module. The bridge provides a hook-based API that allows the Observatory to subscribe to framework events (message flow, component lifecycle, metrics) without modifying the framework core.

**Document:** [OBS-02-BRIDGE](OBS-02-BRIDGE.md)

**Related Terms:** [Hook](#hook), [Event Buffer](#event-buffer), [Observatory](#observatory)

**Architecture:** The bridge is the only coupling point between the framework and Observatory. When Observatory is not installed, the bridge is not imported, ensuring zero overhead.

---

### DAG

**Definition:** Directed Acyclic Graph — a visual representation of the pipeline topology showing sources, transformations, destinations, and the channels connecting them. The DAG view in Observatory is interactive and shows real-time message flow.

**Document:** [OBS-04-PIPELINE-TOPOLOGY](OBS-04-PIPELINE-TOPOLOGY.md)

**Related Terms:** [Topology](#topology), [Lane](#lane)

**Properties:** The DAG is acyclic (no loops) and directed (messages flow in one direction through transformations).

---

### Debug Controller

**Definition:** The component responsible for managing the debug state machine and handling debug commands (pause, resume, step, breakpoints). The debug controller intercepts framework execution at hook points and enforces the current debug state.

**Document:** [OBS-03-DEBUG-CONTROLS](OBS-03-DEBUG-CONTROLS.md), [OBS-TECH-02-BRIDGE-API](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-02-BRIDGE-API.md)

**Related Terms:** [Debug Session](#debug-session), [Step](#step), [Breakpoint](#breakpoint)

**State Machine:** The debug controller maintains states: INACTIVE, RUNNING, PAUSED, STEPPING.

---

### Debug Session

**Definition:** A period of active debugging from the moment debug mode is enabled until it is disabled. A debug session tracks the total number of steps executed and the active breakpoints.

**Document:** [OBS-03-DEBUG-CONTROLS](OBS-03-DEBUG-CONTROLS.md)

**Related Terms:** [Debug Controller](#debug-controller), [Step](#step), [Granularity](#granularity)

**Lifecycle:** Starts when debug mode is enabled (or when the pipeline is first paused), ends when debug mode is disabled or the pipeline is fully resumed.

---

### Event Buffer

**Definition:** A fixed-size ring buffer that stores Observatory events (message flow, component lifecycle, metrics) for transmission to the frontend. When the buffer is full, the oldest events are evicted to make room for new ones.

**Document:** [OBS-01-ARCHITECTURE](OBS-01-ARCHITECTURE.md), [OBS-02-BRIDGE](OBS-02-BRIDGE.md)

**Related Terms:** [Ring Buffer](#ring-buffer), [Bridge](#bridge), [Sampling](#sampling)

**Configuration:** Buffer size is configurable via `observatory.buffer_size` (default: 1,000 events).

---

### Granularity

**Definition:** The step size when executing the pipeline in debug mode. Observatory supports three granularities: MESSAGE (pause after each message), STAGE (pause after each pipeline stage), and BREAKPOINT (free-running with conditional pauses at breakpoints).

**Document:** [OBS-03-DEBUG-CONTROLS](OBS-03-DEBUG-CONTROLS.md)

**Related Terms:** [Step](#step), [Debug Controller](#debug-controller), [Breakpoint](#breakpoint)

**Values:**
- **MESSAGE:** Finest granularity — pause after every message (high overhead, very detailed)
- **STAGE:** Medium granularity — pause after each transformation stage
- **BREAKPOINT:** Coarsest granularity — free-running with conditional pauses

---

### Hook

**Definition:** An async callback function from the framework to the bridge, invoked at key points in the pipeline lifecycle (message published, transformation started, destination received, etc.). Hooks allow the Observatory to observe framework behavior without modifying core code.

**Document:** [OBS-02-BRIDGE](OBS-02-BRIDGE.md)

**Related Terms:** [Bridge](#bridge), [Event Buffer](#event-buffer)

**Implementation:** Hooks are no-ops when Observatory is not installed, ensuring zero performance impact.

---

### Inspector

**Definition:** The message detail view panel that displays the full structure, tags, metadata, and journey of a selected message. The inspector supports multiple views (tree, JSON, diff) and allows developers to trace a message's path through the pipeline.

**Document:** [OBS-06-MESSAGE-INSPECTOR](OBS-06-MESSAGE-INSPECTOR.md)

**Related Terms:** [Journey](#journey), [Trace](#trace), [Timeline](#timeline)

**Features:** Tree view, JSON view, diff view (before/after transformation), journey view, tag filtering.

---

### Journey

**Definition:** The complete path a message takes through the pipeline, from source to destination(s), including all transformations applied along the way. The journey view in the inspector shows each step with timestamps and durations.

**Document:** [OBS-06-MESSAGE-INSPECTOR](OBS-06-MESSAGE-INSPECTOR.md)

**Related Terms:** [Inspector](#inspector), [Trace](#trace), [Timeline](#timeline)

**Implementation:** Journeys are reconstructed from events that share the same `_trace_id`.

---

### Lane

**Definition:** A horizontal swim lane in the timeline view representing a single channel. Each lane shows messages flowing through that channel over time, with the timeline arranged in a stacked layout.

**Document:** [OBS-05-TEMPORAL-TIMELINE](OBS-05-TEMPORAL-TIMELINE.md)

**Related Terms:** [Timeline](#timeline), [Live Tail](#live-tail)

**Behavior:** Lanes are dynamically created as new channels become active. Lanes can be collapsed/expanded and reordered by the user.

---

### Live Tail

**Definition:** An auto-scrolling real-time view mode that keeps the most recent messages visible as they arrive. Live tail mode is the default for both the timeline and message list views, ensuring developers always see the latest pipeline activity.

**Document:** [OBS-05-TEMPORAL-TIMELINE](OBS-05-TEMPORAL-TIMELINE.md), [OBS-06-MESSAGE-INSPECTOR](OBS-06-MESSAGE-INSPECTOR.md)

**Related Terms:** [Timeline](#timeline), [Inspector](#inspector)

**Behavior:** When live tail is enabled, the view automatically scrolls to show new events. Users can disable live tail by manually scrolling backward.

---

### Observatory

**Definition:** The web-based observability and debug module for the COD3S Data framework. Observatory provides a browser-based dashboard with pipeline topology visualization, message timeline, metrics charts, and interactive debug controls.

**Document:** [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md), [OBS-01-ARCHITECTURE](OBS-01-ARCHITECTURE.md)

**Related Terms:** [Bridge](#bridge), [Debug Controller](#debug-controller), [Metrics Dashboard](#metrics-dashboard)

**Stack:** Vue 3 (frontend) + FastAPI (backend) + WebSocket (real-time communication)

---

### Ring Buffer

**Definition:** A fixed-size circular buffer data structure that evicts the oldest entries when full. The Observatory event buffer is implemented as a ring buffer to provide bounded memory usage while retaining recent history.

**Document:** [OBS-01-ARCHITECTURE](OBS-01-ARCHITECTURE.md), [OBS-02-BRIDGE](OBS-02-BRIDGE.md)

**Related Terms:** [Event Buffer](#event-buffer), [Sampling](#sampling)

**Rationale:** Ring buffers prevent memory growth in long-running pipelines while ensuring the most recent events are always available.

---

### Sampling

**Definition:** A throttling strategy for high-throughput pipelines that reduces the number of events sent to Observatory. Sampling can be based on rate (sample N% of events) or interval (sample one event per time window).

**Document:** [OBS-02-BRIDGE](OBS-02-BRIDGE.md), [OBS-08-CONFIGURATION](OBS-08-CONFIGURATION.md)

**Related Terms:** [Event Buffer](#event-buffer), [Bridge](#bridge)

**Strategies:**
- **none:** No sampling (all events captured) — Default
- **rate:** Sample a percentage of events (e.g., 0.1 = 10%)
- **interval:** Sample one event per time window (e.g., every 100ms)

**Configuration:** `observatory.sampling.strategy`, `observatory.sampling.rate`, `observatory.sampling.interval_ms`

---

### Slow-Motion

**Definition:** A reduced-speed pipeline execution mode that adds an artificial delay between messages, allowing developers to observe the pipeline flow in "slow motion" without manually stepping. Slow-motion can be adjusted in real time via a UI slider.

**Document:** [OBS-03-DEBUG-CONTROLS](OBS-03-DEBUG-CONTROLS.md)

**Related Terms:** [Step](#step), [Granularity](#granularity), [Debug Controller](#debug-controller)

**Use Cases:** Observing flow patterns, following individual messages, detailed observation without manual stepping.

---

### Step

**Definition:** One unit of execution in debug mode, as defined by the current granularity. A step can be a single message (MESSAGE granularity), a complete pipeline stage (STAGE granularity), or the execution until a breakpoint is hit (BREAKPOINT granularity).

**Document:** [OBS-03-DEBUG-CONTROLS](OBS-03-DEBUG-CONTROLS.md)

**Related Terms:** [Granularity](#granularity), [Debug Session](#debug-session), [Debug Controller](#debug-controller)

**Behavior:** When the pipeline is paused, clicking "Step" executes one unit of work and then re-pauses.

---

### Timeline

**Definition:** A temporal visualization of message flow through the pipeline over time, inspired by Chrome DevTools timeline. The timeline arranges messages in horizontal swim lanes (one per channel) and shows message arrival, transformation, and propagation with precise timestamps.

**Document:** [OBS-05-TEMPORAL-TIMELINE](OBS-05-TEMPORAL-TIMELINE.md)

**Related Terms:** [Lane](#lane), [Live Tail](#live-tail), [Inspector](#inspector)

**Features:** Zoom, pan, live tail, channel filtering, trace highlighting, playback controls.

---

### Topology

**Definition:** The pipeline structure view represented as a directed acyclic graph (DAG) showing sources, transformations, destinations, and the channels connecting them. The topology view is interactive and shows real-time message flow with animated edges.

**Document:** [OBS-04-PIPELINE-TOPOLOGY](OBS-04-PIPELINE-TOPOLOGY.md)

**Related Terms:** [DAG](#dag), [Inspector](#inspector), [Debug Controller](#debug-controller)

**Layout:** Auto-layout using hierarchical (top-to-bottom) or force-directed algorithms.

---

### Trace

**Definition:** End-to-end message correlation via the `_trace_id` metadata field. Each message carries a unique trace ID that allows Observatory to reconstruct the full journey of a message through the pipeline, even when it is transformed or split into multiple messages.

**Document:** [OBS-05-TEMPORAL-TIMELINE](OBS-05-TEMPORAL-TIMELINE.md), [OBS-06-MESSAGE-INSPECTOR](OBS-06-MESSAGE-INSPECTOR.md)

**Related Terms:** [Journey](#journey), [Inspector](#inspector), [Timeline](#timeline)

**Implementation:** The framework automatically assigns a `_trace_id` to each source message and propagates it through transformations.

---

## Cross-Reference Index

### By Document

| Document | Key Terms |
|----------|-----------|
| **OBS-00-OVERVIEW** | [Observatory](#observatory) |
| **OBS-01-ARCHITECTURE** | [Event Buffer](#event-buffer), [Ring Buffer](#ring-buffer), [Bridge](#bridge) |
| **OBS-02-BRIDGE** | [Bridge](#bridge), [Hook](#hook), [Event Buffer](#event-buffer), [Sampling](#sampling) |
| **OBS-03-DEBUG-CONTROLS** | [Debug Controller](#debug-controller), [Debug Session](#debug-session), [Breakpoint](#breakpoint), [Step](#step), [Granularity](#granularity), [Slow-Motion](#slow-motion) |
| **OBS-04-PIPELINE-TOPOLOGY** | [Topology](#topology), [DAG](#dag) |
| **OBS-05-TEMPORAL-TIMELINE** | [Timeline](#timeline), [Lane](#lane), [Live Tail](#live-tail), [Trace](#trace) |
| **OBS-06-MESSAGE-INSPECTOR** | [Inspector](#inspector), [Journey](#journey), [Trace](#trace) |
| **OBS-07-METRICS-DASHBOARD** | (No new terms — uses framework metrics from [10-OBSERVABILITY](../10-OBSERVABILITY.md)) |
| **OBS-08-CONFIGURATION** | [Sampling](#sampling) (configuration details) |

---

### By Category

#### Architecture

- [Observatory](#observatory)
- [Bridge](#bridge)
- [Event Buffer](#event-buffer)
- [Ring Buffer](#ring-buffer)
- [Hook](#hook)
- [Sampling](#sampling)

#### Debug

- [Debug Controller](#debug-controller)
- [Debug Session](#debug-session)
- [Breakpoint](#breakpoint)
- [Step](#step)
- [Granularity](#granularity)
- [Slow-Motion](#slow-motion)

#### Visualization

- [Topology](#topology)
- [DAG](#dag)
- [Timeline](#timeline)
- [Lane](#lane)
- [Live Tail](#live-tail)
- [Inspector](#inspector)

#### Tracing

- [Trace](#trace)
- [Journey](#journey)

---

## Summary

This glossary defines **20 Observatory-specific terms** organized alphabetically with clear definitions, document references, and related terms. Use this as a quick reference when reading the functional or technical specifications.

**Key Categories:**
1. **Architecture:** Bridge, Event Buffer, Ring Buffer, Hook, Sampling
2. **Debug:** Debug Controller, Breakpoint, Step, Granularity, Slow-Motion
3. **Visualization:** Topology, DAG, Timeline, Lane, Inspector
4. **Tracing:** Trace, Journey

For framework-wide terms (Source, Destination, Broker, Channel, Message, etc.), refer to the main [Framework Glossary](../12-GLOSSARY.md).

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-08-CONFIGURATION](OBS-08-CONFIGURATION.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [← Back to Overview](OBS-00-OVERVIEW.md) |

---

*This is a functional specification document for the COD3S Observatory module. Technical implementation details are in the [Technical Specification](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-00-OVERVIEW.md).*
