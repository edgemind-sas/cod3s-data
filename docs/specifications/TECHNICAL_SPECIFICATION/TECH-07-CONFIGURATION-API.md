# Configuration System Implementation

**Document**: TECH-07-CONFIGURATION-API.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [09-CONFIGURATION](../FUNCTIONAL_SPECIFICATION/09-CONFIGURATION.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [<- TECH-06](TECH-06-DESTINATIONS-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-08 ->](TECH-08-OBSERVABILITY-API.md) |

---

## Table of Contents

1. [Configuration Approaches](#configuration-approaches)
2. [Pydantic Configuration Models](#pydantic-configuration-models)
3. [YAML Configuration](#yaml-configuration)
4. [Python Programmatic API](#python-programmatic-api)
5. [Environment Variables](#environment-variables)

---

## Configuration Approaches

COD3S Data supports three configuration approaches:

1. **YAML Declarative**: Configuration files (production)
2. **Python Programmatic**: Building a `PipelineConfig` in code (embedded, testing)
3. **Environment Variables**: Runtime overrides via `COD3S_*` env vars (containers, CI/CD)

---

## Pydantic Configuration Models

### Base Configuration Classes

```python
from pydantic import BaseModel, Field
from typing import Any

class SourceConfig(BaseModel):
    """Configuration for a source component."""
    type: str = Field(..., description="Source type (e.g., 'random', 'sequence', 'csv')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    channel: str = Field(..., description="Channel to publish to")
    params: dict[str, Any] = Field(default_factory=dict, description="Source-specific parameters")

class TransformConfig(BaseModel):
    """Configuration for a transformation component."""
    type: str = Field(..., description="Transform type (e.g., 'filter', 'map', 'aggregate')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    input_channels: str | list[str] = Field(..., description="Input channel(s)")
    output_channel: str = Field(..., description="Output channel")
    params: dict[str, Any] = Field(default_factory=dict, description="Transform-specific parameters")

class DestinationConfig(BaseModel):
    """Configuration for a destination component."""
    type: str = Field(..., description="Destination type (e.g., 'console', 'file', 'inmemory')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    channel_pattern: str = Field(..., description="Channel pattern to subscribe to")
    params: dict[str, Any] = Field(default_factory=dict, description="Destination-specific parameters")

class BrokerConfig(BaseModel):
    """Configuration for the broker."""
    enable_metrics: bool = Field(default=True, description="Enable metrics emission")
    history_size: int = Field(default=100, description="Default history size per channel")

class PipelineConfig(BaseModel):
    """
    Top-level pipeline configuration.

    This is the root configuration model.
    """
    name: str = Field(default="cod3s_pipeline", description="Pipeline name")
    plugins: list[str] = Field(
        default_factory=list,
        description="Plugin module paths to load before creating components"
    )
    broker: BrokerConfig = Field(default_factory=BrokerConfig, description="Broker configuration")
    sources: list[SourceConfig] = Field(default_factory=list, description="Source components")
    transformations: list[TransformConfig] = Field(
        default_factory=list, description="Transformation components"
    )
    destinations: list[DestinationConfig] = Field(
        default_factory=list, description="Destination components"
    )
    observatory: dict[str, Any] | None = Field(
        default=None, description="Observatory configuration (optional)"
    )
```

Key design decisions:

- **No type validation on config models.** Source/transform/destination `type` values are validated at component creation time by `ComponentFactory`, not by the config models. This allows plugins to register new types without modifying the config schema.
- **`params` dict pattern.** Type-specific parameters live in `params` rather than as flat fields on the config model. This keeps the models generic and extensible.
- **Sources can be empty.** There is no validator requiring at least one source -- an empty pipeline is valid.
- **No `extra: "forbid"`.** Extra fields are silently ignored rather than rejected, for forward compatibility.

---

## YAML Configuration

### YAML Schema

```yaml
# pipeline.yaml
name: my_pipeline

# Plugins: custom component modules loaded before creating components
plugins:
  - my_package.custom_transforms

broker:
  history_size: 100
  enable_metrics: true

sources:
  - type: csv
    label: Sensor data
    channel: sensors.raw
    params:
      file_path: data/sensors.csv
      batch_mode: batch

  - type: random
    label: Simulated sensors
    channel: sensors.simulated
    params:
      rate: 1.0
      min_value: 0.0
      max_value: 100.0

transformations:
  - type: threshold_alert
    label: Critical alert
    input_channels: sensors.raw
    output_channel: alerts.critical
    params:
      threshold: 50.0

  - type: filter
    input_channels: sensors.raw
    output_channel: sensors.filtered
    params:
      predicate: "value > 10"

destinations:
  - type: console
    channel_pattern: alerts.**

  - type: file
    label: Filtered output
    channel_pattern: sensors.filtered
    params:
      file_path: output/filtered.jsonl

# Optional Observatory configuration
observatory:
  enabled: true
  host: "0.0.0.0"
  port: 8765
```

### Loading YAML Configuration

```python
from cod3s_data.config.loaders import load_yaml, load_dict
from cod3s_data.framework import Framework

# --- Load from YAML file ---
config = load_yaml("pipeline.yaml")

# --- Or load from a Python dict ---
config = load_dict({
    "name": "my_pipeline",
    "sources": [
        {"type": "random", "channel": "test", "params": {"rate": 10.0}}
    ],
    "destinations": [
        {"type": "console", "channel_pattern": "test"}
    ],
})

# --- Run the pipeline ---
async with Framework(config) as framework:
    await framework.run()
```

The `load_yaml()` function:

1. Reads and parses the YAML file.
2. Applies environment variable overrides (`COD3S_*`).
3. Validates the result with `PipelineConfig.model_validate()`.
4. Returns a `PipelineConfig` instance.

### Configuration Validation Errors

Pydantic provides clear, actionable error messages:

```python
# Missing required field
>>> load_dict({"sources": [{"type": "csv"}]})
ValidationError: 1 validation error for PipelineConfig
sources.0.channel
  Field required [type=missing ...]

# Invalid field type
>>> load_dict({"broker": {"history_size": "not_a_number"}})
ValidationError: 1 validation error for PipelineConfig
broker.history_size
  Input should be a valid integer [type=int_parsing ...]
```

---

## Python Programmatic API

### Building Configuration in Code

The programmatic approach constructs a `PipelineConfig` directly and passes it to `Framework`:

```python
from cod3s_data.config.models import (
    PipelineConfig,
    SourceConfig,
    TransformConfig,
    DestinationConfig,
    BrokerConfig,
)
from cod3s_data.framework import Framework

# Build configuration
config = PipelineConfig(
    name="sensor_monitoring",
    broker=BrokerConfig(history_size=200, enable_metrics=True),
    sources=[
        SourceConfig(
            type="csv",
            label="Sensor data",
            channel="sensors.raw",
            params={"file_path": "data/sensors.csv", "batch_mode": "batch"},
        ),
        SourceConfig(
            type="random",
            label="Simulated sensors",
            channel="sensors.simulated",
            params={"rate": 1.0, "min_value": 0.0, "max_value": 100.0},
        ),
    ],
    transformations=[
        TransformConfig(
            type="threshold_alert",
            input_channels="sensors.raw",
            output_channel="alerts.critical",
            params={"threshold": 50.0},
        ),
    ],
    destinations=[
        DestinationConfig(
            type="console",
            channel_pattern="alerts.**",
        ),
        DestinationConfig(
            type="file",
            channel_pattern="sensors.raw",
            params={"file_path": "output/raw.jsonl"},
        ),
    ],
)

# Run the pipeline
async with Framework(config) as framework:
    await framework.run()
```

### Framework Constructor

```python
class Framework:
    def __init__(
        self,
        config: PipelineConfig,
        plugins: list[str] | None = None,
        observatory: bool | Any = False,
    ) -> None:
        """
        Args:
            config: Pipeline configuration
            plugins: Extra plugin module paths (merged with config.plugins)
            observatory: Enable Observatory. Pass True for defaults,
                or an ObservatoryConfig instance for custom settings.
                Pass False (default) to disable.
        """
```

The `Framework` is used as an async context manager:

```python
async with Framework(config) as framework:
    await framework.run()
```

On enter (`__aenter__`), the framework calls `start()` which:
1. Starts the Observatory server (if enabled).
2. Loads plugins (config.plugins + extra plugins, deduplicated).
3. Creates components from configuration via `ComponentFactory`.
4. Starts the pipeline (broker, destinations, transformations, sources).

On exit (`__aexit__`), the framework calls `stop()` for graceful shutdown.

---

## Environment Variables

### Environment Override Pattern

Environment variables are applied as overrides by the `_apply_env_overrides()` function
inside `load_yaml()` and `load_dict()`. They follow the naming convention `COD3S_<SECTION>_<KEY>`.

```python
# cod3s_data/config/loaders.py

def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """
    Apply COD3S_* environment variable overrides to config dict.

    Supported variables:
      COD3S_PIPELINE_NAME          - Override pipeline name
      COD3S_BROKER_ENABLE_METRICS  - Override broker.enable_metrics (bool)
      COD3S_BROKER_HISTORY_SIZE    - Override broker.history_size (int)
      COD3S_OBSERVATORY_ENABLED    - Enable/disable Observatory (bool)
      COD3S_OBSERVATORY_HOST       - Observatory host (str)
      COD3S_OBSERVATORY_PORT       - Observatory port (int)
      COD3S_OBSERVATORY_BUFFER_SIZE        - Observatory buffer size (int)
      COD3S_OBSERVATORY_MEMORY_LIMIT_MB    - Observatory memory limit (int)
      COD3S_OBSERVATORY_DEBUG              - Enable debug mode (bool)
      COD3S_OBSERVATORY_DEBUG_GRANULARITY  - Debug granularity (str)
      COD3S_OBSERVATORY_DEBUG_AUTO_PAUSE   - Auto-pause in debug (bool)
      COD3S_OBSERVATORY_SAMPLING_STRATEGY  - Sampling strategy (str)
      COD3S_OBSERVATORY_SAMPLING_RATE      - Sampling rate (float)
      COD3S_OBSERVATORY_SAMPLING_INTERVAL_MS - Sampling interval (int)
    """
    ...
```

Environment variables are applied **after** YAML parsing and **before** Pydantic validation, so they override file-based values.

### Usage Examples

```bash
# Override pipeline name
export COD3S_PIPELINE_NAME=production_pipeline

# Override broker settings
export COD3S_BROKER_HISTORY_SIZE=200
export COD3S_BROKER_ENABLE_METRICS=false

# Enable and configure Observatory
export COD3S_OBSERVATORY_ENABLED=true
export COD3S_OBSERVATORY_PORT=9000
```

### Docker Compose Example

```yaml
# docker-compose.yml
version: '3.8'

services:
  cod3s-data:
    image: cod3s-data:latest
    environment:
      - COD3S_PIPELINE_NAME=production
      - COD3S_BROKER_HISTORY_SIZE=200
      - COD3S_BROKER_ENABLE_METRICS=true
      - COD3S_OBSERVATORY_ENABLED=true
      - COD3S_OBSERVATORY_PORT=8765
    volumes:
      - ./data:/data
      - ./output:/output
    command: cod3s-data run /config/pipeline.yaml
```

---

## Plugin System

### Plugin Convention

A plugin is a Python module that exports a `register(factory: ComponentFactory) -> None` function.
As a fallback for backwards compatibility, `register_all(factory)` is also accepted.

### Plugin Loading

```python
# cod3s_data/plugins.py

class PluginError(Exception):
    """Error raised when a plugin fails to load or register."""

def load_plugin(module_path: str, factory: ComponentFactory) -> None:
    """
    Load a single plugin module.

    1. importlib.import_module(module_path)
    2. Look for register(), fallback to register_all()
    3. Call register(factory)
    4. Wrap errors in PluginError
    """

def load_plugins(
    module_paths: list[str],
    factory: ComponentFactory,
    *,
    raise_on_error: bool = True,
) -> list[str]:
    """
    Load multiple plugins in declaration order.

    Returns list of successfully loaded module paths.
    """
```

### Framework Integration

The `Framework` class loads plugins at the beginning of `start()`, before creating components:

```python
class Framework:
    def __init__(self, config: PipelineConfig, plugins: list[str] | None = None):
        self._extra_plugins = plugins or []
        ...

    def _load_plugins(self) -> list[str]:
        """Merge config.plugins + extra_plugins (deduplicated), load in order."""
        ...

    async def start(self):
        self._load_plugins()  # Before component creation
        self._create_components()  # Uses ComponentFactory
        await self._start_pipeline()
```

### CLI Integration

Both `run` and `validate` subcommands accept `-p/--plugin MODULE` (repeatable):

```bash
cod3s-data run pipeline.yaml -p my_package.custom_transforms
cod3s-data validate pipeline.yaml --plugin my_package.custom_transforms
```

CLI plugins are merged with YAML `plugins:` list (without duplication).
The `validate` command loads plugins and verifies that all referenced component types exist in the factory registries.

---

## References

- **Functional Spec**: [09-CONFIGURATION](../FUNCTIONAL_SPECIFICATION/09-CONFIGURATION.md)
- **QA Decisions**: [Q7.1-Q7.3](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) - Technology stack (Pydantic)
  - [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md) - Pydantic rationale

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [<- TECH-06](TECH-06-DESTINATIONS-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-08 ->](TECH-08-OBSERVABILITY-API.md) |
