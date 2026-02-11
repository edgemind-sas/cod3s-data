# COD3S Data Framework - Configuration

**Version:** 1.0
**Date:** 2026-01-24
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← 08-BROKER](08-BROKER.md) | [OVERVIEW](00-OVERVIEW.md) | [10-OBSERVABILITY →](10-OBSERVABILITY.md) |

---

## Table of Contents

- [Configuration Approach](#configuration-approach)
- [YAML Configuration](#yaml-configuration)
- [Python API Configuration](#python-api-configuration)
- [Environment Variables](#environment-variables)
- [Configuration Hierarchy](#configuration-hierarchy)
- [Validation](#validation)
- [Examples and Patterns](#examples-and-patterns)
- [Best Practices](#best-practices)

---

## Configuration Approach

### Triple Configuration Model

COD3S Data supports **three configuration methods**, designed to work together:

1. **YAML Files** - Declarative configuration for standard cases
2. **Python API** - Programmatic configuration for advanced cases
3. **Environment Variables** - Runtime overrides and secrets

```mermaid
graph LR
    YAML[YAML File<br/>pipeline.yaml] --> Merge[Configuration<br/>Merger]
    Python[Python API<br/>Framework.add_*] --> Merge
    Env[Environment Variables<br/>CODS_*] --> Merge

    Merge --> Validate[Validation]
    Validate --> Runtime[Runtime<br/>Configuration]

    style Merge fill:#f9f,stroke:#333,stroke-width:2px
```

---

### Design Principles

**1. Declarative First**
- YAML for common patterns (80% of use cases)
- Clear, readable, version-controllable

**2. Programmatic for Power**
- Python API for complex logic
- Dynamic configuration
- Custom components

**3. Environment for Deployment**
- Secrets and credentials
- Deployment-specific overrides
- 12-factor app compliance

---

### Configuration Scope

**What can be configured:**
- Sources (type, channels, batch mode, delivery guarantee)
- Transformations (type, inputs, outputs, parameters)
- Destinations (type, channels, buffering, retry)
- Broker (history size, performance tuning)
- Logging and observability

**What cannot be configured (yet):**
- Internal data structures (V1.0 - fixed)
- Concurrency model (V1.0 - asyncio)
- Serialization format (V1.0 - JSON)

---

## YAML Configuration

### Basic Structure

```yaml
# pipeline.yaml - Full pipeline configuration

# Broker settings (optional)
broker:
  history_size: 100
  history_ttl: 3600

# Sources
sources:
  - type: csv
    path: "/data/sensors.csv"
    channel: "sensors.temp"
    mode: BATCH

  - type: random
    channel: "test.random"
    mode: REALTIME
    rate_per_second: 10

# Transformations
transformations:
  - type: threshold_alert
    input: "sensors.temp"
    threshold: 100
    output: "alerts.critical"

  - type: deduplication
    input: "sensors.temp"
    output: "sensors.temp.clean"
    window: 60

# Destinations
destinations:
  - type: console
    channel: "alerts.**"
    format: "pretty"

  - type: file
    channel: "sensors.**"
    path: "/output/sensors.jsonl"

# Logging
logging:
  level: "INFO"
  format: "json"
```

---

### Sources Configuration

```yaml
sources:
  # CSV file source
  - type: csv
    name: "historical_import"  # Optional name for reference
    path: "/data/temperature_history.csv"
    channel: "sensors.{location}.temp"
    mode: BATCH

    # CSV parsing
    delimiter: ","
    has_header: true
    timestamp_column: "ts"
    value_column: "reading"
    tag_columns: ["location", "sensor_id"]

    # Delivery guarantee
    delivery_guarantee: "at-least-once"
    retry_attempts: 3
    retry_timeout: 5s
    dead_letter_channel: "_dlq.source_failures"

  # Real-time random source
  - type: random
    name: "test_generator"
    channel: "test.random.temp"
    mode: REALTIME
    rate_per_second: 100
    min_value: 20.0
    max_value: 100.0
    duration_seconds: 60  # Run for 60s then stop
```

---

### Transformations Configuration

```yaml
transformations:
  # Built-in transformation
  - type: threshold_alert
    name: "temp_alert"
    input: "sensors.*.temp"
    threshold: 100
    severity: "critical"
    output: "alerts.critical.temp"

  # Custom Python transformation
  - type: custom_python
    name: "viscosity_computer"
    class: "myapp.transforms.ViscosityComputer"
    inputs:
      - "sensors.{id}.temperature"
      - "sensors.{id}.speed"
      - "sensors.{id}.force"
    output: "indicators.{id}.viscosity"
    parameters:
      calibration_factor: 1.2
      min_speed: 10

  # Deduplication
  - type: deduplication
    input: "sensors.temp.raw"
    output: "sensors.temp.clean"
    window: 60  # 60 seconds
    strategy: "key+timestamp"
```

---

### Destinations Configuration

```yaml
destinations:
  # Console destination
  - type: console
    name: "debug_console"
    channel: "alerts.**"
    format: "pretty"
    colors: true
    history: "none"  # Real-time only

  # File destination
  - type: file
    name: "sensor_archive"
    channel: "sensors.**"
    path: "/data/sensors.jsonl"
    format: "jsonl"
    rotation:
      max_size: "100MB"
      max_age: "24h"
      max_files: 7

    # Buffering
    buffer_size: 5000
    overflow_strategy: "drop_oldest"

    # Retry
    retry_attempts: 3
    retry_backoff: "exponential"
    retry_initial_delay: 1s
    retry_max_delay: 60s
    dead_letter_channel: "_dlq.file_failures"

  # In-memory collector (testing)
  - type: collect
    name: "test_collector"
    channel: "test.results"
    max_messages: 1000
```

---

### Broker Configuration

```yaml
broker:
  # History buffer
  history_enabled: true
  history_size: 100  # Default per channel
  history_ttl: 3600  # 1 hour

  # Per-channel overrides
  channel_history:
    "sensors.**":
      size: 1000
      ttl: 7200
    "alerts.**":
      size: 50
      ttl: 300

  # Out-of-order handling
  reject_out_of_order: false  # Global default
  warn_out_of_order: true

  channels:
    "sensors.critical.*":
      reject_out_of_order: true  # Override for critical sensors
```

---

### Logging Configuration

```yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"  # or "text"
  output: "stdout"  # or file path

  # Structured logging
  include_timestamps: true
  include_trace_ids: true

  # Log filtering
  filters:
    - component: "broker"
      level: "DEBUG"
    - component: "destinations"
      level: "WARNING"
```

---

## Python API Configuration

### Programmatic Configuration

```python
from cod3s_data import Framework
from cod3s_data.sources import CSVSource, RandomSource
from cod3s_data.transformations import ThresholdAlert
from cod3s_data.destinations import ConsoleDestination, FileDestination

# Create framework
framework = Framework()

# Configure broker
framework.configure_broker(
    history_size=100,
    history_ttl=3600
)

# Add sources
csv_source = CSVSource(
    path="/data/sensors.csv",
    channel="sensors.temp",
    mode="BATCH",
    timestamp_column="ts",
    value_column="reading"
)
framework.add_source(csv_source)

random_source = RandomSource(
    channel="test.random",
    mode="REALTIME",
    rate_per_second=10,
    min_value=20.0,
    max_value=100.0
)
framework.add_source(random_source)

# Add transformations
alert_transform = ThresholdAlert(
    input_channel="sensors.temp",
    output_channel="alerts.critical",
    threshold=100
)
framework.add_transformation(alert_transform)

# Add destinations
console_dest = ConsoleDestination(
    channel="alerts.**",
    format="pretty"
)
framework.add_destination(console_dest)

file_dest = FileDestination(
    channel="sensors.**",
    path="/output/sensors.jsonl",
    buffer_size=5000
)
framework.add_destination(file_dest)

# Start framework
framework.start()

# Run for some time or wait for completion
import time
time.sleep(60)

# Stop framework
framework.stop()
```

---

### Dynamic Configuration

**Add components at runtime:**

```python
framework = Framework()
framework.start()

# Add source dynamically
new_source = RandomSource(channel="dynamic.sensor")
framework.add_source(new_source)

# Add destination dynamically
new_dest = ConsoleDestination(channel="dynamic.**")
framework.add_destination(new_dest)

# Components start immediately
```

**Remove components at runtime:**

```python
# Remove source
framework.remove_source(csv_source)

# Remove destination
framework.remove_destination(console_dest)
```

---

### Custom Components

```python
# Import custom transformation
from myapp.transforms import ViscosityComputer

# Register with framework
framework.register_transformation("viscosity", ViscosityComputer)

# Use in configuration
viscosity_transform = ViscosityComputer(
    input_channels=[
        "sensors.temp",
        "sensors.speed",
        "sensors.force"
    ],
    output_channel="indicators.viscosity",
    calibration_factor=1.2
)
framework.add_transformation(viscosity_transform)
```

---

## Environment Variables

### Variable Substitution

**YAML files support environment variable substitution:**

```yaml
sources:
  - type: mqtt
    broker: "${MQTT_BROKER_URL}"  # From environment
    username: "${MQTT_USERNAME}"
    password: "${MQTT_PASSWORD}"
    channel: "sensors.temp"

destinations:
  - type: database
    connection_string: "${DATABASE_URL}"
    table: "sensor_data"
```

**Set environment variables:**

```bash
export MQTT_BROKER_URL="mqtt://localhost:1883"
export MQTT_USERNAME="admin"
export MQTT_PASSWORD="secret123"
export DATABASE_URL="postgresql://user:pass@localhost/db"

# Run framework
cod3s-data --config pipeline.yaml
```

---

### Framework Environment Variables

**Reserved prefix:** `CODS_*`

**Configuration variables:**

| Variable | Description | Default |
|----------|-------------|---------|
| `CODS_CONFIG` | Path to YAML config file | `./pipeline.yaml` |
| `CODS_LOG_LEVEL` | Logging level | `INFO` |
| `CODS_LOG_FORMAT` | Log format (json/text) | `json` |
| `CODS_BROKER_HISTORY_SIZE` | Broker history size | `100` |
| `CODS_METRICS_ENABLED` | Enable metrics emission | `true` |

**Example:**

```bash
export CODS_CONFIG="/etc/cod3s/production.yaml"
export CODS_LOG_LEVEL="WARNING"
export CODS_BROKER_HISTORY_SIZE="1000"

cod3s-data
```

---

### Secrets Management

**Best practices for secrets:**

**1. Environment variables (recommended):**
```yaml
destinations:
  - type: database
    connection_string: "${DATABASE_URL}"
```

**2. Secret files:**
```yaml
destinations:
  - type: database
    connection_string_file: "/run/secrets/db_connection"
```

**3. Secret management services (V2.0+):**
```yaml
destinations:
  - type: database
    connection_string:
      vault: "secret/data/database/url"
```

**Never:**
- ❌ Hard-code secrets in YAML
- ❌ Commit secrets to version control
- ❌ Log secrets (framework redacts known patterns)

---

## Configuration Hierarchy

### Override Order

**Priority (highest to lowest):**

1. **Python API** (programmatic)
2. **Environment Variables** (runtime)
3. **YAML Files** (declarative)
4. **Framework Defaults** (built-in)

```mermaid
graph TB
    Defaults[Framework Defaults<br/>Built-in values] --> YAML[YAML File<br/>pipeline.yaml]
    YAML --> Env[Environment Variables<br/>CODS_*, ${VAR}]
    Env --> Python[Python API<br/>Framework.configure_*]
    Python --> Final[Final Configuration]

    style Final fill:#f9f,stroke:#333,stroke-width:2px
```

---

### Example: Override Chain

```python
# 1. Framework default
history_size = 100  # Built-in default

# 2. YAML file
# pipeline.yaml:
#   broker:
#     history_size: 500

# 3. Environment variable
# export CODS_BROKER_HISTORY_SIZE=1000

# 4. Python API
framework.configure_broker(history_size=2000)

# Final value: 2000 (Python API wins)
```

---

### Merge Behavior

**Simple values:** Last one wins (override)

**Collections (lists):** Append (extend)

```yaml
# base.yaml
sources:
  - type: csv
    path: "data.csv"

# override.yaml
sources:
  - type: random
    channel: "test"

# Merged result (both sources):
sources:
  - type: csv
    path: "data.csv"
  - type: random
    channel: "test"
```

**Dictionaries:** Recursive merge

```yaml
# base.yaml
broker:
  history_size: 100
  history_ttl: 3600

# override.yaml
broker:
  history_size: 500  # Override
  # history_ttl: 3600  # Inherited from base

# Merged result:
broker:
  history_size: 500   # Overridden
  history_ttl: 3600   # Inherited
```

---

## Validation

### Configuration Validation

**Framework validates configuration at startup:**

```python
try:
    framework = Framework.from_yaml("pipeline.yaml")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Example errors:
    # - Missing required field: sources[0].channel
    # - Invalid value: retry_attempts must be >= 0
    # - Unknown type: sources[0].type="unknown_source"
```

---

### Validation Rules

**Type validation:**
- Source type exists and is registered
- Transformation type exists
- Destination type exists

**Required fields:**
- Sources must have: `type`, `channel`
- Transformations must have: `type`, `input`, `output`
- Destinations must have: `type`, `channel`

**Value constraints:**
- `buffer_size` > 0
- `retry_attempts` >= 0
- `rate_per_second` > 0
- `history_size` >= 0

**Cross-field validation:**
- Channel names follow naming rules
- Wildcard patterns are valid
- File paths exist (for file sources)

---

### Validation CLI

**Validate configuration without running:**

```bash
# Validate YAML file
cod3s-data validate --config pipeline.yaml

# Output:
# ✓ Configuration valid
# - 2 sources configured
# - 3 transformations configured
# - 2 destinations configured
# - No errors found

# Or if errors:
# ✗ Configuration invalid
# ERROR: sources[0].channel: Required field missing
# ERROR: transformations[1].threshold: Must be a number
# WARNING: destinations[0].buffer_size: Value 0 will disable buffering
```

---

## Examples and Patterns

### Example 1: Simple Monitoring

```yaml
# Simple temperature monitoring

sources:
  - type: random
    channel: "sensors.temp"
    rate_per_second: 1
    min_value: 20
    max_value: 100

transformations:
  - type: threshold_alert
    input: "sensors.temp"
    threshold: 80
    output: "alerts.high_temp"

destinations:
  - type: console
    channel: "alerts.**"
    format: "pretty"
```

---

### Example 2: Historical Data Processing

```yaml
# Batch processing of historical data

sources:
  - type: csv
    path: "/data/2024-01-15-incident.csv"
    channel: "replay.sensors.temp"
    mode: TRANSPOSE  # Preserve timestamps
    time_scale: 10   # Replay 10x faster

transformations:
  - type: custom_python
    class: "analysis.RootCauseAnalyzer"
    input: "replay.sensors.temp"
    output: "analysis.results"

destinations:
  - type: file
    channel: "analysis.results"
    path: "/output/analysis_report.json"
```

---

### Example 3: Multi-Sensor Processing

```yaml
# Compute derived metrics from multiple sensors

sources:
  - type: mqtt
    broker: "${MQTT_BROKER}"
    topics:
      - "sensors/+/temperature"
      - "sensors/+/speed"
      - "sensors/+/force"
    channel: "sensors.{topic[1]}.{topic[2]}"

transformations:
  - type: custom_python
    class: "physics.ViscosityComputer"
    inputs:
      - "sensors.{id}.temperature"
      - "sensors.{id}.speed"
      - "sensors.{id}.force"
    output: "indicators.{id}.viscosity"

destinations:
  - type: database
    connection_string: "${DATABASE_URL}"
    channel: "indicators.**"
    table: "computed_metrics"
```

---

### Example 4: Production Pipeline

```yaml
# Production-ready configuration with monitoring

broker:
  history_size: 1000
  history_ttl: 7200

sources:
  - type: mqtt
    broker: "${MQTT_BROKER}"
    topic: "sensors/#"
    channel: "sensors.{topic}"
    delivery_guarantee: "at-least-once"
    retry_attempts: 5
    dead_letter_channel: "_dlq.mqtt_failures"

transformations:
  # Deduplication
  - type: deduplication
    input: "sensors.**"
    output: "sensors.clean.**"
    window: 60

  # Alerting
  - type: threshold_alert
    input: "sensors.clean.*.temperature"
    threshold: 100
    output: "alerts.critical.temperature"

destinations:
  # Production database
  - type: database
    connection_string: "${DATABASE_URL}"
    channel: "sensors.clean.**"
    buffer_size: 10000
    retry_attempts: 3
    dead_letter_channel: "_dlq.db_failures"

  # Monitoring console
  - type: console
    channel: "alerts.**"
    format: "pretty"

  # Metrics monitoring
  - type: console
    channel: "_metrics.broker.**"
    format: "compact"

  # DLQ monitoring
  - type: file
    channel: "_dlq.**"
    path: "/var/log/cod3s/dlq.log"

logging:
  level: "INFO"
  format: "json"
  include_timestamps: true
  include_trace_ids: true
```

---

## Best Practices

### Configuration Organization

**Do:**
- ✅ Use YAML for declarative pipelines
- ✅ Use Python API for dynamic configuration
- ✅ Use environment variables for secrets
- ✅ Version control YAML files (git)
- ✅ Validate before deployment

**Don't:**
- ❌ Hard-code secrets in YAML
- ❌ Mix configuration methods unnecessarily
- ❌ Skip validation step

---

### Deployment

**Do:**
- ✅ Use different YAML files per environment (dev, staging, prod)
- ✅ Use environment variables for environment-specific values
- ✅ Test configuration in non-production first
- ✅ Use configuration validation in CI/CD

**Example:**
```bash
# Development
export CODS_CONFIG=config/dev.yaml
export DATABASE_URL=postgresql://localhost/dev_db

# Production
export CODS_CONFIG=config/prod.yaml
export DATABASE_URL=postgresql://prod-db/prod_db
```

---

### Security

**Do:**
- ✅ Use environment variables for secrets
- ✅ Restrict file permissions (600 for configs with secrets)
- ✅ Use secret management services (Vault, AWS Secrets Manager)
- ✅ Audit configuration changes

**Don't:**
- ❌ Commit secrets to git
- ❌ Log configuration with secrets
- ❌ Share production configs via insecure channels

---

## Summary

**COD3S Data Configuration** provides flexible, layered configuration:

1. **Triple Configuration:**
   - YAML files (declarative)
   - Python API (programmatic)
   - Environment variables (runtime)

2. **Hierarchy:**
   - Python API > Env Vars > YAML > Defaults

3. **Validation:**
   - Type checking
   - Required fields
   - Value constraints
   - CLI validation tool

4. **Best Practices:**
   - YAML for standard cases
   - Python for complex logic
   - Environment variables for secrets
   - Validate before deployment

**Next:** Explore [Observability](10-OBSERVABILITY.md) for monitoring and debugging.

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← 08-BROKER](08-BROKER.md) | [OVERVIEW](00-OVERVIEW.md) | [10-OBSERVABILITY →](10-OBSERVABILITY.md) |

---

*This is a functional specification document. Implementation details will be defined in the technical specification phase.*
