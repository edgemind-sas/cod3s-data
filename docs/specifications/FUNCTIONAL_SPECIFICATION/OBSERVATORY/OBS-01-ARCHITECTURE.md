# COD3S Observatory - Architecture

**Version:** 1.0
**Date:** 2026-02-11
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-02-BRIDGE →](OBS-02-BRIDGE.md) |

---

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Optional Module Pattern](#optional-module-pattern)
- [Activation](#activation)
- [Embedded Server](#embedded-server)
- [Memory Model](#memory-model)
- [Debug Session Lifecycle](#debug-session-lifecycle)
- [Performance Impact](#performance-impact)

---

## High-Level Architecture

The Observatory is composed of four layers connected linearly:

```mermaid
graph LR
    subgraph "Python Process"
        FW["COD3S Framework<br/>(Sources, Broker, Transforms, Destinations)"]
        BR["Observatory Bridge<br/>(Hooks + Debug Controller)"]
        BE["FastAPI Backend<br/>(REST + WebSocket)"]
    end

    subgraph "Browser"
        FE["Vue 3 Frontend<br/>(Topology, Timeline, Inspector, Metrics)"]
    end

    FW -->|"Hook calls<br/>(async)"| BR
    BR -->|"Events<br/>(in-memory)"| BE
    BE <-->|"WebSocket<br/>(JSON)"| FE
    BR -->|"Control commands<br/>(pause, step)"| FW
```

### Layer Responsibilities

| Layer | Technology | Responsibility |
|-------|-----------|---------------|
| **Framework** | Python / asyncio | Execute pipeline, call bridge hooks when present |
| **Bridge** | Python | Translate framework events to observatory events, manage debug state |
| **Backend** | FastAPI / Uvicorn | Serve REST API, manage WebSocket connections, serve static frontend |
| **Frontend** | Vue 3 / Vuetify 3 | Visualize topology, timeline, messages, metrics; send debug commands |

### Data Flow

```mermaid
graph TB
    subgraph "Framework Layer"
        SRC[Sources] -->|publish| BRK[Broker]
        BRK -->|notify| TRF[Transformations]
        TRF -->|publish| BRK
        BRK -->|notify| DST[Destinations]
    end

    subgraph "Bridge Layer"
        BRK -->|on_message_published| OB[Observatory Bridge]
        SRC -->|on_component_state_change| OB
        TRF -->|on_component_state_change| OB
        DST -->|on_component_state_change| OB
        BRK -->|on_metric_emitted| OB
        OB -->|events| BUF[Event Buffer]
        OB -->|debug state| DC[Debug Controller]
    end

    subgraph "Backend Layer"
        BUF --> API[FastAPI]
        DC --> API
        API <-->|WebSocket| WS[WebSocket Manager]
    end

    subgraph "Frontend Layer"
        WS <--> VUE[Vue 3 App]
    end
```

---

## Optional Module Pattern

### Design Principle

The Observatory is **fully optional**. The framework must:
1. Function identically without Observatory installed
2. Have **zero performance overhead** when Observatory is not active
3. Never import `observatory` package directly from core code

### Import Guard Pattern

The framework uses an import guard to check for Observatory availability:

```python
# In framework.py — NOT: from cod3s_data.observatory import ...
# Instead: conditional check at startup

class Framework:
    def __init__(self, config, observatory: bool = False):
        self._bridge: ObservatoryBridge | None = None

        if observatory:
            try:
                from cod3s_data.observatory import create_observatory
                self._bridge = create_observatory(self, config)
            except ImportError:
                raise ImportError(
                    "Observatory requires extra dependencies. "
                    "Install with: pip install cod3s-data[observatory]"
                )
```

### Hook Pattern

Throughout the framework, bridge hooks are guarded by a None check:

```python
# In broker — zero cost when bridge is None
async def publish(self, channel: str, message: Message) -> int:
    # ... normal publish logic ...
    subscriber_count = await self._notify_subscribers(channel, message)

    if self._bridge is not None:
        await self._bridge.on_message_published(channel, message, subscriber_count)

    return subscriber_count
```

**Performance:** A `None` check is ~1 nanosecond — negligible even at 10K msg/s.

### Package Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
observatory = [
    "fastapi>=0.115",
    "uvicorn>=0.34",
    "websockets>=14.0",
]
```

The frontend is pre-built and bundled as static files — no Node.js dependency for end users.

---

## Activation

### Method 1: Python API

```python
from cod3s_data import Framework

# Enable with defaults
framework = Framework(config, observatory=True)

# Enable with custom configuration
from cod3s_data.observatory import ObservatoryConfig

obs_config = ObservatoryConfig(
    host="127.0.0.1",
    port=8765,
    debug=True,
    buffer_size=2000,
    memory_limit_mb=100,
)
framework = Framework(config, observatory=obs_config)
```

### Method 2: YAML Configuration

```yaml
# pipeline.yaml
sources:
  # ... sources ...

observatory:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  debug: false
  buffer_size: 1000
  memory_limit_mb: 50
```

### Method 3: Environment Variables

```bash
export COD3S_OBSERVATORY_ENABLED=true
export COD3S_OBSERVATORY_PORT=8765
```

### Activation Sequence

```mermaid
sequenceDiagram
    participant User
    participant Framework
    participant Bridge
    participant Backend
    participant Browser

    User->>Framework: Framework(config, observatory=True)
    Framework->>Framework: Import observatory module
    Framework->>Bridge: Create ObservatoryBridge
    Bridge->>Backend: Create FastAPI app
    Framework->>Framework: Register bridge hooks
    Framework->>Framework: Start pipeline components

    Note over Framework,Backend: Framework event loop running

    Backend->>Backend: Start Uvicorn (asyncio task)
    Note over Backend: Listening on 127.0.0.1:8765

    Browser->>Backend: Connect to http://localhost:8765
    Backend->>Browser: Serve Vue 3 SPA
    Browser->>Backend: WebSocket connect /ws
    Backend->>Browser: Send current topology + state
    Note over Browser: Dashboard ready
```

---

## Embedded Server

### Uvicorn Integration

The Observatory web server runs **inside** the framework's asyncio event loop as a background task:

```python
# Conceptual — see OBS-TECH-01 for implementation details
import uvicorn

config = uvicorn.Config(app=fastapi_app, host="127.0.0.1", port=8765, loop="none")
server = uvicorn.Server(config)

# Run as asyncio task in the existing event loop
asyncio.create_task(server.serve())
```

**Key:** `loop="none"` tells Uvicorn to use the **existing** event loop instead of creating its own.

### Lifecycle

| Event | Observatory Action |
|-------|-------------------|
| Framework startup | Create bridge, start Uvicorn task |
| Framework running | Bridge hooks fire on framework events |
| Framework shutdown | Graceful Uvicorn shutdown, close WebSocket connections |
| Framework error | Bridge captures error event, frontend shows alert |

### Port Binding

- **Default:** `127.0.0.1:8765` (localhost only)
- **Configurable:** Host and port via configuration
- **Conflict handling:** If port is busy, log warning and continue without Observatory
- **Security (V1):** Localhost-only binding. Remote access deferred to V2 (requires auth).

---

## Memory Model

### Ring Buffers

The Observatory stores events in fixed-size ring buffers. When a buffer is full, the oldest event is evicted.

```mermaid
graph LR
    subgraph "Event Buffer (ring, size=1000)"
        E1["Event 997"]
        E2["Event 998"]
        E3["Event 999"]
        E4["Event 1000"]
        E5["← write pointer"]
    end

    NEW["New Event"] -->|"evicts oldest"| E5
```

### Buffer Types

| Buffer | Default Size | Content | Purpose |
|--------|-------------|---------|---------|
| **Message events** | 1000 | Published messages (summary) | Timeline, topology animation |
| **Component states** | 100 per component | State transitions | Topology node colors |
| **Metric snapshots** | 300 per metric | Metric values (1/s × 5min) | Dashboard charts |
| **Error events** | 200 | Errors with context | Error panel |
| **Debug events** | 500 | Breakpoint hits, step events | Debug history |

### Memory Cap

- **Default limit:** 50 MB total Observatory memory usage
- **Enforcement:** Periodic check, oldest events evicted if over limit
- **Configurable:** `memory_limit_mb` in configuration
- **Excluded from limit:** Frontend static files (served once, cached by browser)

### Late-Connecting Frontends

When a new browser connects, it receives:
1. Current pipeline topology (sources, transforms, destinations, channels)
2. Current component states (running, paused, error)
3. Recent events from buffers (fills timeline and message list)
4. Current metric values (populates dashboard)
5. Current debug state (mode, granularity, breakpoints)

This allows a browser to connect at any time and immediately see a meaningful view.

---

## Debug Session Lifecycle

### Complete Session Sequence

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant FE as Frontend
    participant BE as Backend
    participant BR as Bridge
    participant FW as Framework

    Note over Dev,FW: Phase 1: Connect & Observe

    Dev->>FE: Open browser
    FE->>BE: WebSocket connect
    BE->>FE: topology + current state
    Note over FE: Display DAG, metrics

    Note over Dev,FW: Phase 2: Enter Debug Mode

    Dev->>FE: Click "Pause" button
    FE->>BE: debug.pause command
    BE->>BR: pause_pipeline()
    BR->>FW: Suspend sources at yield points
    FW->>BR: on_component_state_change(PAUSED)
    BR->>BE: debug.paused event
    BE->>FE: debug.paused event
    FE->>Dev: UI shows PAUSED state

    Note over Dev,FW: Phase 3: Step Through

    Dev->>FE: Click "Step" (granularity=MESSAGE)
    FE->>BE: debug.step command
    BE->>BR: step_next(MESSAGE)
    BR->>FW: Allow one message
    FW->>BR: on_message_published(...)
    BR->>BE: message.published + debug.step_completed
    BE->>FE: Events
    FE->>Dev: Show message in timeline, highlight in DAG

    Note over Dev,FW: Phase 4: Set Breakpoint

    Dev->>FE: Add breakpoint on "sensors.*.temperature" > 100
    FE->>BE: debug.add_breakpoint command
    BE->>BR: set_breakpoint(pattern, condition)
    Dev->>FE: Click "Resume"
    FE->>BE: debug.resume command
    BE->>BR: resume_pipeline()
    Note over FW: Pipeline running freely

    FW->>BR: on_message_published(temp=105)
    BR->>BR: Evaluate breakpoint → HIT
    BR->>FW: Suspend sources
    BR->>BE: debug.breakpoint_hit event
    BE->>FE: breakpoint_hit + message detail
    FE->>Dev: Pipeline paused, show matching message

    Note over Dev,FW: Phase 5: Inspect & Resume

    Dev->>FE: Click message in inspector
    FE->>BE: message.inspect command
    BE->>FE: Full message detail
    Dev->>FE: Click "Resume"
    FE->>BE: debug.resume
    Note over FW: Pipeline running again
```

---

## Performance Impact

### When Observatory is Not Installed

| Metric | Impact |
|--------|--------|
| CPU | 0% (no code loaded) |
| Memory | 0 bytes (no imports) |
| Latency | 0 ns (no hook checks) |
| Startup | 0 ms |

### When Observatory is Installed but Not Enabled

| Metric | Impact |
|--------|--------|
| CPU | 0% |
| Memory | ~0 (module loaded but bridge is None) |
| Latency per message | ~1 ns (`if self._bridge is not None` check) |
| Startup | ~0 ms |

### When Observatory is Active (No Debug)

| Metric | Impact |
|--------|--------|
| CPU | 1-3% (hook processing, WebSocket) |
| Memory | 10-50 MB (event buffers, FastAPI, static files) |
| Latency per message | 5-20 us (hook call, buffer write) |
| Startup | ~200 ms (Uvicorn, FastAPI) |

### When Observatory is Active (Debug Mode)

| Metric | Impact |
|--------|--------|
| CPU | 5-15% (breakpoint evaluation, debug controller) |
| Memory | 10-50 MB (same buffers) |
| Latency per message | 50-500 us (breakpoint eval, pause checks) |
| Note | Debug mode is not for production use |

### Sampling

For high-throughput pipelines, the bridge supports sampling to reduce overhead:
- **Every-Nth**: Process every Nth message (e.g., every 10th)
- **Time-based**: Process at most one message per time window (e.g., every 100ms)
- **Bypass**: Breakpoint evaluation always runs (no sampling) to avoid missing conditions

See: [OBS-02-BRIDGE](OBS-02-BRIDGE.md#sampling-and-throttling) for details.

---

## Summary

The Observatory architecture is designed around four principles:

1. **Zero overhead when absent** — Import guard pattern ensures no cost when not installed
2. **Minimal overhead when present** — In-process integration avoids serialization overhead
3. **Bidirectional communication** — Bridge enables both observation and control
4. **Memory-bounded** — Ring buffers with configurable caps prevent unbounded growth

**Next:** [OBS-02-BRIDGE](OBS-02-BRIDGE.md) defines the critical Bridge interface between framework and observatory.

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-02-BRIDGE →](OBS-02-BRIDGE.md) |

---

*This is a functional specification document for the COD3S Observatory module. Technical implementation details are in [OBS-TECH-01-BACKEND-ARCHITECTURE](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-01-BACKEND-ARCHITECTURE.md).*
