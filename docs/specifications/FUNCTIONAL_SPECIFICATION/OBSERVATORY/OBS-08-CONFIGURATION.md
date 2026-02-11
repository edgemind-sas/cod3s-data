# COD3S Observatory - Configuration

**Version:** 1.0
**Date:** 2026-02-11
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-07-METRICS-DASHBOARD](OBS-07-METRICS-DASHBOARD.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-99-GLOSSARY →](OBS-99-GLOSSARY.md) |

---

## Table of Contents

- [Configuration Approach](#configuration-approach)
- [YAML Configuration](#yaml-configuration)
- [Python Configuration](#python-configuration)
- [Environment Variables](#environment-variables)
- [Configuration Hierarchy](#configuration-hierarchy)
- [Default Values](#default-values)
- [Validation Rules](#validation-rules)
- [Examples](#examples)
- [Summary](#summary)

---

## Configuration Approach

Observatory follows the same **triple configuration model** as the main COD3S Data framework:

1. **YAML Files** — Declarative configuration under `observatory:` key
2. **Python API** — `ObservatoryConfig` Pydantic model
3. **Environment Variables** — `COD3S_OBSERVATORY_*` prefix

**Design Principles:**
- **Optional by Default** — Observatory is disabled unless explicitly enabled
- **Zero Overhead When Disabled** — No imports, no hooks, no performance impact
- **Consistent with Framework** — Uses same patterns as framework configuration (see [09-CONFIGURATION](../09-CONFIGURATION.md))

---

## YAML Configuration

### Full Configuration Example

```yaml
# pipeline.yaml

# Observatory configuration block
observatory:
  # Enable Observatory (required to activate)
  enabled: true

  # Network settings
  host: "127.0.0.1"  # Bind address (V1: localhost only)
  port: 8765         # WebSocket server port

  # Debug settings
  debug:
    enabled: false          # Enable debug controls (pause, step, breakpoints)
    granularity: "MESSAGE"  # MESSAGE, STAGE, or BREAKPOINT
    auto_pause: false       # Pause pipeline on Observatory connection

  # Performance settings
  buffer_size: 1000       # Event buffer size (ring buffer)
  memory_limit_mb: 50     # Maximum memory for event buffering

  # Sampling settings (for high-throughput pipelines)
  sampling:
    strategy: "none"      # none, rate, or interval
    rate: 1.0             # Sample rate (0.0-1.0) if strategy=rate
    interval_ms: 100      # Sample interval if strategy=interval
```

---

### Minimal Configuration

```yaml
# Enable Observatory with all defaults
observatory:
  enabled: true
```

This is sufficient for most use cases. All other settings use framework defaults.

---

### Configuration Fields

#### Top-Level Fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `enabled` | `bool` | Enable Observatory module | `false` |
| `host` | `str` | Bind address for WebSocket server | `"127.0.0.1"` |
| `port` | `int` | WebSocket server port | `8765` |
| `debug` | `object` | Debug mode configuration | (see below) |
| `buffer_size` | `int` | Ring buffer size for events | `1000` |
| `memory_limit_mb` | `int` | Maximum memory limit (MB) | `50` |
| `sampling` | `object` | Event sampling configuration | (see below) |

---

#### Debug Configuration

```yaml
debug:
  enabled: false          # Enable debug controls
  granularity: "MESSAGE"  # Step granularity: MESSAGE, STAGE, BREAKPOINT
  auto_pause: false       # Pause pipeline when Observatory connects
```

| Field | Type | Values | Default | Description |
|-------|------|--------|---------|-------------|
| `enabled` | `bool` | `true`/`false` | `false` | Enable pause, step, breakpoints |
| `granularity` | `str` | `MESSAGE`, `STAGE`, `BREAKPOINT` | `MESSAGE` | Default step granularity |
| `auto_pause` | `bool` | `true`/`false` | `false` | Auto-pause on connection (useful for inspecting startup) |

---

#### Sampling Configuration

```yaml
sampling:
  strategy: "none"     # Sampling strategy
  rate: 1.0            # Sample rate (for "rate" strategy)
  interval_ms: 100     # Sample interval (for "interval" strategy)
```

| Field | Type | Values | Default | Description |
|-------|------|--------|---------|-------------|
| `strategy` | `str` | `none`, `rate`, `interval` | `none` | Sampling strategy |
| `rate` | `float` | `0.0` to `1.0` | `1.0` | Sample rate (1.0 = 100%, 0.1 = 10%) |
| `interval_ms` | `int` | `1` to `10000` | `100` | Sample every N milliseconds |

**Sampling strategies:**
- `none` — No sampling (send all events) — Default for low/medium throughput
- `rate` — Sample a percentage of events (e.g., 0.1 = 10% of events)
- `interval` — Sample one event per time interval (e.g., every 100ms)

**When to use sampling:**
- Pipeline throughput > 1,000 msg/s
- Event buffer fills up quickly (check memory limit)
- Browser performance degrades (timeline rendering slows down)

---

## Python Configuration

### ObservatoryConfig Model

```python
from pydantic import BaseModel, Field

class ObservatoryDebugConfig(BaseModel):
    enabled: bool = False
    granularity: str = "MESSAGE"  # MESSAGE, STAGE, BREAKPOINT
    auto_pause: bool = False

class ObservatorySamplingConfig(BaseModel):
    strategy: str = "none"  # none, rate, interval
    rate: float = 1.0
    interval_ms: int = 100

class ObservatoryConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    debug: ObservatoryDebugConfig = ObservatoryDebugConfig()
    buffer_size: int = Field(default=1000, ge=100, le=100000)
    memory_limit_mb: int = Field(default=50, ge=10, le=500)
    sampling: ObservatorySamplingConfig = ObservatorySamplingConfig()
```

---

### Programmatic Configuration

```python
from cod3s_data import Framework, ObservatoryConfig

# Create Observatory configuration
observatory_config = ObservatoryConfig(
    enabled=True,
    host="127.0.0.1",
    port=8765,
    debug={"enabled": True, "granularity": "MESSAGE"},
    buffer_size=2000,
    memory_limit_mb=100
)

# Pass to Framework
framework = Framework(
    config=pipeline_config,
    observatory=observatory_config
)

# Or enable with defaults
framework = Framework(
    config=pipeline_config,
    observatory=True  # Uses ObservatoryConfig() defaults
)
```

---

### Runtime Configuration Changes

**Observatory cannot be enabled/disabled at runtime** in V1. It must be configured at framework initialization.

**Some settings can be changed at runtime via WebSocket commands:**
- Debug granularity (via `debug.set_granularity` command)
- Slow-motion delay (via `debug.set_slow_motion` command)
- Breakpoints (add/remove/enable/disable)

---

## Environment Variables

### Variable List

Observatory supports environment variable overrides with the `COD3S_OBSERVATORY_*` prefix:

| Environment Variable | Maps To | Type | Example |
|---------------------|---------|------|---------|
| `COD3S_OBSERVATORY_ENABLED` | `enabled` | `bool` | `true` or `false` |
| `COD3S_OBSERVATORY_HOST` | `host` | `str` | `127.0.0.1` |
| `COD3S_OBSERVATORY_PORT` | `port` | `int` | `8765` |
| `COD3S_OBSERVATORY_DEBUG` | `debug.enabled` | `bool` | `true` or `false` |
| `COD3S_OBSERVATORY_DEBUG_GRANULARITY` | `debug.granularity` | `str` | `MESSAGE`, `STAGE`, `BREAKPOINT` |
| `COD3S_OBSERVATORY_DEBUG_AUTO_PAUSE` | `debug.auto_pause` | `bool` | `true` or `false` |
| `COD3S_OBSERVATORY_BUFFER_SIZE` | `buffer_size` | `int` | `1000` |
| `COD3S_OBSERVATORY_MEMORY_LIMIT_MB` | `memory_limit_mb` | `int` | `50` |
| `COD3S_OBSERVATORY_SAMPLING_STRATEGY` | `sampling.strategy` | `str` | `none`, `rate`, `interval` |
| `COD3S_OBSERVATORY_SAMPLING_RATE` | `sampling.rate` | `float` | `0.1` (10%) |
| `COD3S_OBSERVATORY_SAMPLING_INTERVAL_MS` | `sampling.interval_ms` | `int` | `100` |

---

### Usage Example

```bash
# Enable Observatory with custom settings
export COD3S_OBSERVATORY_ENABLED=true
export COD3S_OBSERVATORY_PORT=9000
export COD3S_OBSERVATORY_DEBUG=true
export COD3S_OBSERVATORY_BUFFER_SIZE=5000

# Run framework (Observatory settings read from environment)
cod3s-data run pipeline.yaml
```

---

### Boolean Parsing

Environment variables are parsed as follows:
- **Truthy:** `true`, `True`, `TRUE`, `1`, `yes`, `Yes`, `YES`
- **Falsy:** `false`, `False`, `FALSE`, `0`, `no`, `No`, `NO`

---

## Configuration Hierarchy

### Priority Order

**Highest to lowest:**

1. **Environment Variables** (`COD3S_OBSERVATORY_*`)
2. **Python API** (`Framework(observatory=ObservatoryConfig(...))`)
3. **YAML Files** (`observatory:` block)
4. **Framework Defaults** (built-in values)

This matches the main framework configuration hierarchy (see [09-CONFIGURATION](../09-CONFIGURATION.md)).

---

### Override Example

```python
# 1. Framework default
enabled = False  # Built-in default

# 2. YAML file (pipeline.yaml):
#    observatory:
#      enabled: true
#      port: 8765

# 3. Python API:
observatory_config = ObservatoryConfig(enabled=True, port=9000)
framework = Framework(config, observatory=observatory_config)

# 4. Environment variable:
# export COD3S_OBSERVATORY_PORT=9999

# Final value: enabled=True (Python/YAML), port=9999 (env var)
```

---

### Merge Behavior

**Simple values:** Last one wins (override)

**Nested objects (debug, sampling):** Recursive merge

```yaml
# base.yaml
observatory:
  enabled: true
  debug:
    enabled: true
    granularity: "MESSAGE"

# override.yaml (or Python/env)
observatory:
  debug:
    granularity: "STAGE"  # Override
    # enabled: true         # Inherited from base

# Merged result:
observatory:
  enabled: true
  debug:
    enabled: true       # Inherited
    granularity: "STAGE"  # Overridden
```

---

## Default Values

### Complete Defaults Table

| Setting | Default | Rationale |
|---------|---------|-----------|
| `enabled` | `false` | Observatory is opt-in |
| `host` | `127.0.0.1` | V1 is localhost-only (no remote access) |
| `port` | `8765` | Common WebSocket port, unlikely to conflict |
| `debug.enabled` | `false` | Debug mode is opt-in (performance impact) |
| `debug.granularity` | `MESSAGE` | Finest granularity for detailed debugging |
| `debug.auto_pause` | `false` | Do not pause unless user requests |
| `buffer_size` | `1000` | Holds ~5 seconds at 200 msg/s |
| `memory_limit_mb` | `50` | Conservative limit to avoid memory bloat |
| `sampling.strategy` | `none` | No sampling by default (accurate metrics) |
| `sampling.rate` | `1.0` | 100% sampling (if strategy is `rate`) |
| `sampling.interval_ms` | `100` | Sample every 100ms (if strategy is `interval`) |

---

## Validation Rules

### Field Validation

Observatory configuration is validated using Pydantic. Invalid configurations will raise `ValidationError` at framework initialization.

---

### Port Validation

**Range:** 1024-65535 (non-privileged ports)

```python
port: int = Field(default=8765, ge=1024, le=65535)
```

**Why 1024+?**
- Ports 0-1023 are privileged (require root)
- Observatory is a development tool, should not require elevated permissions

---

### Memory Limit Validation

**Range:** 10 MB to 500 MB

```python
memory_limit_mb: int = Field(default=50, ge=10, le=500)
```

**Why this range?**
- **Minimum 10 MB:** Below this, buffer is too small to be useful
- **Maximum 500 MB:** Above this, Observatory may degrade system performance

---

### Buffer Size Validation

**Range:** 100 to 100,000 events

```python
buffer_size: int = Field(default=1000, ge=100, le=100000)
```

**Why this range?**
- **Minimum 100:** Holds at least a few seconds of events
- **Maximum 100,000:** Beyond this, memory and rendering performance degrade

---

### Granularity Validation

**Allowed values:** `MESSAGE`, `STAGE`, `BREAKPOINT`

```python
granularity: str = Field(default="MESSAGE", pattern="^(MESSAGE|STAGE|BREAKPOINT)$")
```

---

### Sampling Strategy Validation

**Allowed values:** `none`, `rate`, `interval`

**Rate range:** 0.0 to 1.0 (if strategy is `rate`)

**Interval range:** 1 to 10,000 ms (if strategy is `interval`)

---

### Host Validation

**V1 restriction:** `host` must be `127.0.0.1` or `localhost`

```python
def validate_host(cls, v):
    if v not in ["127.0.0.1", "localhost"]:
        raise ValueError("V1 only supports localhost (127.0.0.1)")
    return v
```

**Rationale:** V1 does not include authentication or TLS. Remote access is unsafe and not supported.

---

### Cross-Field Validation

**If `sampling.strategy == "rate"`, then `sampling.rate` must be set (0.0-1.0)**

**If `sampling.strategy == "interval"`, then `sampling.interval_ms` must be set (1-10000)**

---

## Examples

### Example 1: Enable with Defaults

```yaml
observatory:
  enabled: true
```

**Result:**
- WebSocket server on `ws://127.0.0.1:8765`
- Debug controls disabled
- No sampling (all events captured)
- Buffer: 1,000 events, 50 MB limit

---

### Example 2: Debug Mode

```yaml
observatory:
  enabled: true
  debug:
    enabled: true
    granularity: "MESSAGE"
    auto_pause: true  # Pause on Observatory connection
```

**Result:**
- Observatory starts with debug controls enabled
- Pipeline pauses immediately when browser connects
- Step granularity is MESSAGE (finest level)

---

### Example 3: High-Throughput Pipeline

```yaml
observatory:
  enabled: true
  buffer_size: 5000
  memory_limit_mb: 100
  sampling:
    strategy: "rate"
    rate: 0.1  # Sample 10% of events
```

**Result:**
- Larger buffer and memory limit
- Only 10% of events are sent to Observatory
- Reduces browser load on high-throughput pipelines

---

### Example 4: Production Observation (No Debug)

```yaml
observatory:
  enabled: true
  debug:
    enabled: false  # No debug controls in production
  sampling:
    strategy: "interval"
    interval_ms: 1000  # One event per second
```

**Result:**
- Observatory provides read-only observation
- No ability to pause or step the pipeline
- Minimal performance impact (1 event/second)

---

### Example 5: Environment Variable Override

```bash
# Base configuration in pipeline.yaml
# observatory:
#   enabled: false
#   port: 8765

# Enable Observatory via environment variable
export COD3S_OBSERVATORY_ENABLED=true
export COD3S_OBSERVATORY_PORT=9000

# Run framework
cod3s-data run pipeline.yaml

# Result: Observatory enabled on port 9000 (env var overrides YAML)
```

---

### Example 6: Programmatic Configuration

```python
from cod3s_data import Framework, PipelineConfig, ObservatoryConfig

pipeline_config = PipelineConfig.from_yaml("pipeline.yaml")

observatory_config = ObservatoryConfig(
    enabled=True,
    port=8765,
    debug={
        "enabled": True,
        "granularity": "STAGE",
        "auto_pause": False
    },
    buffer_size=2000,
    sampling={
        "strategy": "rate",
        "rate": 0.5  # Sample 50%
    }
)

framework = Framework(
    config=pipeline_config,
    observatory=observatory_config
)

framework.run()
```

---

## Summary

Observatory configuration follows the COD3S Data triple configuration model:

1. **YAML Configuration:**
   - `observatory:` block in pipeline.yaml
   - Full control over all settings
   - Minimal configuration: just `enabled: true`

2. **Python Configuration:**
   - `ObservatoryConfig` Pydantic model
   - Passed to `Framework(observatory=...)`
   - Programmatic control for advanced use cases

3. **Environment Variables:**
   - `COD3S_OBSERVATORY_*` prefix
   - Override YAML and Python settings
   - Useful for deployment-specific settings

4. **Validation:**
   - Port range: 1024-65535
   - Memory limit: 10-500 MB
   - Buffer size: 100-100,000 events
   - V1 host restriction: localhost only

5. **Defaults:**
   - Disabled by default (`enabled: false`)
   - Localhost-only (`127.0.0.1:8765`)
   - Debug mode off, no sampling, 1,000-event buffer

**Next:** [OBS-99-GLOSSARY](OBS-99-GLOSSARY.md) defines all Observatory-specific terminology.

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← OBS-07-METRICS-DASHBOARD](OBS-07-METRICS-DASHBOARD.md) | [OBS-00-OVERVIEW](OBS-00-OVERVIEW.md) | [OBS-99-GLOSSARY →](OBS-99-GLOSSARY.md) |

---

*This is a functional specification document for the COD3S Observatory module. Technical implementation details are in [OBS-TECH-01-BACKEND-ARCHITECTURE](../../TECHNICAL_SPECIFICATION/OBSERVATORY/OBS-TECH-01-BACKEND-ARCHITECTURE.md).*
