# Configuration System Implementation

**Document**: TECH-07-CONFIGURATION-API.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [09-CONFIGURATION](../FUNCTIONAL_SPECIFICATION/09-CONFIGURATION.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-06](TECH-06-DESTINATIONS-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-08 →](TECH-08-OBSERVABILITY-API.md) |

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
2. **Python Programmatic**: Direct API calls (embedded, testing)
3. **Environment Variables**: Runtime overrides (containers, CI/CD)

---

## Pydantic Configuration Models

### Base Configuration Classes

```python
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from enum import Enum

class SourceConfig(BaseModel):
    """Source configuration (validated by Pydantic)"""
    type: str = Field(..., description="Source type (csv, random, sequence, file)")
    channel: str = Field(..., description="Target channel")
    batch_mode: str = Field(default="batch", description="Batch mode (batch, realtime, transpose)")

    # Type-specific fields (optional)
    file_path: str | None = None
    rate: float | None = None
    start: int | None = None
    end: int | None = None

    @field_validator('type')
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        allowed = ['csv', 'random', 'sequence', 'file']
        if v not in allowed:
            raise ValueError(f"Source type must be one of {allowed}, got '{v}'")
        return v

    @field_validator('batch_mode')
    @classmethod
    def validate_batch_mode(cls, v: str) -> str:
        allowed = ['batch', 'realtime', 'transpose']
        if v not in allowed:
            raise ValueError(f"Batch mode must be one of {allowed}, got '{v}'")
        return v

class TransformationConfig(BaseModel):
    """Transformation configuration"""
    type: str
    input_channel: str | list[str]
    output_channel: str

    # Type-specific fields
    threshold: float | None = None
    predicate: str | None = None
    window_duration: str | None = None  # e.g., "5m", "1h"

class DestinationConfig(BaseModel):
    """Destination configuration"""
    type: str
    channel_pattern: str

    # Optional fields
    file_path: str | None = None
    buffer_size: int = 1000
    overflow_strategy: str = "drop_oldest"
    retry_attempts: int = 3
    dlq_channel: str | None = None

class BrokerConfig(BaseModel):
    """Broker configuration"""
    type: str = "in_memory"
    default_history_size: int = 100
    enable_metrics: bool = True

class PipelineConfig(BaseModel):
    """
    Complete pipeline configuration.

    This is the root configuration model.
    """
    name: str = Field(default="cod3s_pipeline", description="Pipeline name")
    plugins: list[str] = Field(
        default_factory=list,
        description="Plugin module paths to load before creating components"
    )
    sources: list[SourceConfig] = Field(default_factory=list)
    transformations: list[TransformationConfig] = Field(default_factory=list)
    destinations: list[DestinationConfig] = Field(default_factory=list)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",  # Reject unknown fields (catch typos)
    }

    @field_validator('sources')
    @classmethod
    def validate_sources_not_empty(cls, v):
        if len(v) == 0:
            raise ValueError("At least one source is required")
        return v
```

---

## YAML Configuration

### YAML Schema

```yaml
# pipeline.yaml

# Plugins: custom component modules loaded before creating components
plugins:
  - my_package.custom_transforms

broker:
  type: in_memory
  default_history_size: 100
  enable_metrics: true

sources:
  - type: csv
    file_path: data/sensors.csv
    channel: sensors.raw
    batch_mode: batch

  - type: random
    channel: sensors.simulated
    rate: 1.0  # 1 msg/sec
    min_value: 0.0
    max_value: 100.0
    batch_mode: realtime

transformations:
  - type: threshold_alert
    input_channel: sensors.raw
    output_channel: alerts.critical
    threshold: 50.0

  - type: filter
    input_channel: sensors.raw
    output_channel: sensors.filtered
    predicate: "value > 10"

destinations:
  - type: console
    channel_pattern: alerts.**

  - type: file
    channel_pattern: sensors.filtered
    file_path: output/filtered.jsonl
    buffer_size: 1000
    overflow_strategy: drop_oldest
    retry_attempts: 3
    dlq_channel: _dlq.file_failures
```

### Loading YAML Configuration

```python
import yaml
from pydantic import ValidationError

class Framework:
    @classmethod
    def from_yaml(cls, file_path: str) -> "Framework":
        """
        Load framework from YAML file.

        Args:
            file_path: Path to YAML configuration file

        Returns:
            Configured Framework instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValidationError: If configuration is invalid
            yaml.YAMLError: If YAML is malformed
        """
        # Load YAML
        with open(file_path, 'r') as f:
            config_dict = yaml.safe_load(f)

        # Validate with Pydantic
        try:
            config = PipelineConfig(**config_dict)
        except ValidationError as e:
            # Pydantic provides clear error messages
            print("Configuration validation failed:")
            print(e)
            raise

        # Build framework from validated config
        return cls._build_from_config(config)

    @classmethod
    def _build_from_config(cls, config: PipelineConfig) -> "Framework":
        """
        Build framework from validated config.

        Internal method to construct components.
        """
        framework = cls()

        # Create broker
        if config.broker.type == "in_memory":
            framework.broker = InMemoryBroker(
                default_history_size=config.broker.default_history_size,
                enable_metrics=config.broker.enable_metrics
            )

        # Create sources
        for src_cfg in config.sources:
            source = cls._create_source(framework.broker, src_cfg)
            framework.add_source(source)

        # Create transformations
        for tf_cfg in config.transformations:
            transform = cls._create_transformation(framework.broker, tf_cfg)
            framework.add_transformation(transform)

        # Create destinations
        for dest_cfg in config.destinations:
            destination = cls._create_destination(framework.broker, dest_cfg)
            framework.add_destination(destination)

        return framework

    @staticmethod
    def _create_source(broker: Broker, config: SourceConfig) -> Source:
        """Factory method for sources"""
        if config.type == "csv":
            return CSVSource(
                broker=broker,
                channel=config.channel,
                file_path=config.file_path,
                batch_mode=BatchMode(config.batch_mode)
            )
        elif config.type == "random":
            return RandomSource(
                broker=broker,
                channel=config.channel,
                rate=config.rate or 1.0
            )
        elif config.type == "sequence":
            return SequenceSource(
                broker=broker,
                channel=config.channel,
                start=config.start or 0,
                end=config.end or 100
            )
        else:
            raise ValueError(f"Unknown source type: {config.type}")

    # Similar factory methods for transformations and destinations
```

### Configuration Validation Errors

Pydantic provides clear, actionable error messages:

```python
# Missing required field
>>> config = PipelineConfig(sources=[{"type": "csv"}])
ValidationError: 1 validation error for PipelineConfig
sources.0.channel
  field required (type=value_error.missing)

# Invalid type
>>> config = PipelineConfig(sources=[{
...     "type": "unknown",
...     "channel": "test"
... }])
ValidationError: 1 validation error for SourceConfig
type
  Source type must be one of ['csv', 'random', 'sequence', 'file'], got 'unknown'

# Extra field (typo detection)
>>> config = PipelineConfig(sources=[{
...     "type": "csv",
...     "channel": "test",
...     "file_pth": "data.csv"  # Typo
... }])
ValidationError: 1 validation error for PipelineConfig
sources.0
  Extra inputs are not permitted [type=extra_forbidden, input_value={'type': 'csv', 'channel': 'test', 'file_pth': 'data.csv'}, input_type=dict]
```

---

## Python Programmatic API

### Direct Component Creation

```python
from cod3s_data import Framework
from cod3s_data.sources import CSVSource, RandomSource
from cod3s_data.transformations import ThresholdAlert
from cod3s_data.destinations import ConsoleDestination, FileDestination

# Create framework
framework = Framework()

# Add components programmatically
framework.add_source(CSVSource(
    broker=framework.broker,
    channel="sensors.raw",
    file_path="data/sensors.csv",
    batch_mode=BatchMode.BATCH
))

framework.add_source(RandomSource(
    broker=framework.broker,
    channel="sensors.simulated",
    rate=1.0,
    min_value=0.0,
    max_value=100.0
))

framework.add_transformation(ThresholdAlert(
    broker=framework.broker,
    input_channel="sensors.raw",
    output_channel="alerts.critical",
    threshold=50.0
))

framework.add_destination(ConsoleDestination(
    broker=framework.broker,
    channel_pattern="alerts.**"
))

framework.add_destination(FileDestination(
    broker=framework.broker,
    channel_pattern="sensors.raw",
    file_path="output/raw.jsonl"
))

# Run
await framework.run()
```

### Fluent API (Optional)

```python
framework = (
    Framework()
    .with_source(CSVSource(...))
    .with_transformation(ThresholdAlert(...))
    .with_destination(ConsoleDestination(...))
)

await framework.run()
```

---

## Environment Variables

### Pydantic Settings Integration

```python
from pydantic_settings import BaseSettings

class FrameworkSettings(BaseSettings):
    """
    Framework settings from environment variables.

    Prefix: COD3S_
    Example: COD3S_BROKER_HISTORY_SIZE=200
    """

    # Broker settings
    broker_history_size: int = Field(default=100, alias="BROKER_HISTORY_SIZE")
    broker_metrics_enabled: bool = Field(default=True, alias="BROKER_METRICS_ENABLED")

    # Source settings
    csv_file_path: str | None = Field(default=None, alias="CSV_FILE_PATH")
    random_rate: float = Field(default=1.0, alias="RANDOM_RATE")

    # Destination settings
    output_dir: str = Field(default="output", alias="OUTPUT_DIR")

    model_config = {
        "env_prefix": "COD3S_",
        "case_sensitive": False,
    }

# Usage
settings = FrameworkSettings()

# Override from environment
# export COD3S_BROKER_HISTORY_SIZE=200
# export COD3S_CSV_FILE_PATH=/data/sensors.csv

broker = InMemoryBroker(default_history_size=settings.broker_history_size)
```

### Environment Variable Precedence

```python
# Load configuration with env var overrides
config = PipelineConfig.from_yaml("pipeline.yaml")

# Override with environment variables
settings = FrameworkSettings()

# Apply overrides
if settings.csv_file_path:
    config.sources[0].file_path = settings.csv_file_path

# Build framework
framework = Framework._build_from_config(config)
```

### Docker Compose Example

```yaml
# docker-compose.yml
version: '3.8'

services:
  cod3s-data:
    image: cod3s-data:latest
    environment:
      - COD3S_BROKER_HISTORY_SIZE=200
      - COD3S_CSV_FILE_PATH=/data/sensors.csv
      - COD3S_OUTPUT_DIR=/output
    volumes:
      - ./data:/data
      - ./output:/output
    command: cod3s run /config/pipeline.yaml
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
        await self.broker.start()
        # Create components from config...
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
| [← TECH-06](TECH-06-DESTINATIONS-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-08 →](TECH-08-OBSERVABILITY-API.md) |
