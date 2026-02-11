# COD3S Data Framework - Glossary

**Version:** 1.0
**Date:** 2026-01-24
**Status:** Functional Specification

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← 13-FUTURE-V2-V3](13-FUTURE-V2-V3.md) | [OVERVIEW](00-OVERVIEW.md) | - |

---

## Table of Contents

- [Core Concepts](#core-concepts)
- [Components](#components)
- [Messaging](#messaging)
- [Configuration](#configuration)
- [Operations](#operations)
- [Performance](#performance)
- [Acronyms](#acronyms)

---

## Core Concepts

### Batch Mode
Operational mode for sources that process a **finite dataset** once and then complete. Used for historical data import, file processing, and testing. Contrast with REALTIME mode.

**Related:** [Sources](04-SOURCES.md#batch-modes), REALTIME Mode, TRANSPOSE Mode

---

### Backpressure
Situation where a **slow consumer** cannot keep up with message production rate. COD3S Data handles backpressure via **bounded buffers** with configurable overflow strategies (drop_oldest, drop_newest, block).

**Related:** [Destinations](06-DESTINATIONS.md#buffering-and-backpressure), Buffer, Overflow Strategy

---

### Broker
The **central message router** responsible for distributing messages from publishers (sources, transformations) to subscribers (transformations, destinations) based on channel patterns. V1.0 uses an in-memory broker.

**Related:** [Broker](08-BROKER.md), Channel, Subscription

---

### Channel
A **logical routing path** for messages, identified by a hierarchical string (e.g., `sensors.temp.extruder`). Channels support **wildcard subscriptions** (`*` for single-level, `**` for multi-level). Not a physical queue - purely a routing concept.

**Related:** [Channels & Routing](07-CHANNELS-ROUTING.md), Wildcard

---

### Dead Letter Queue (DLQ)
Special **channels** (prefixed with `_dlq.*`) that receive messages that **failed processing** after retry attempts exhausted. Used for manual investigation and recovery. Messages in DLQ include original message + error metadata.

**Related:** [Messages](03-MESSAGES.md#dead-letter-queue), Retry Strategy

---

### Destination
A **passive component** that **subscribes** to channels and **writes** messages to external systems (databases, files, dashboards). Handles buffering, retries, and failure recovery.

**Related:** [Destinations](06-DESTINATIONS.md), Source, Transformation

---

### Delivery Guarantee
Promise about message delivery reliability. COD3S Data supports:
- **At-Most-Once** (default): Fire-and-forget, may lose messages
- **At-Least-Once** (opt-in): Acknowledged delivery with retries, may deliver duplicates

**Related:** [Messages](03-MESSAGES.md#delivery-guarantees)

---

### Message
The **fundamental unit** of data in COD3S Data. Structure: `key` (identifier), `timestamp` (when), `value` (measurement), `tags` (metadata), `id` (unique ID).

**Related:** [Messages](03-MESSAGES.md), Key, Value, Tags, Timestamp

---

### REALTIME Mode
Operational mode for sources that run **continuously** without end condition. Used for live sensor streams, MQTT subscriptions, polling APIs. Must be explicitly stopped.

**Related:** [Sources](04-SOURCES.md#batch-modes), Batch Mode, TRANSPOSE Mode

---

### Source
An **active component** that **ingests** data from external systems and **publishes** messages to channels. Handles data acquisition, message construction, and delivery guarantees.

**Related:** [Sources](04-SOURCES.md), Destination, Transformation

---

### Stateful Transformation
A transformation that **maintains state** across messages and can consume from **multiple input channels** (N:M mapping). Uses framework helpers like `self.latest`, `TimeWindow`, `CountWindow`, `Cache` for state management.

**Related:** [Transformations](05-TRANSFORMATIONS.md#stateful-transformations), Stateless Transformation

---

### Stateless Transformation
A transformation that processes **one message at a time** with **no memory** of previous messages (1:N mapping). Simpler, faster, and easier to test than stateful transformations.

**Related:** [Transformations](05-TRANSFORMATIONS.md#stateless-transformations), Stateful Transformation

---

### Subscription
Registration of a **callback function** with the broker to receive messages matching a **channel pattern**. Supports exact match or wildcard patterns (`*`, `**`).

**Related:** [Broker](08-BROKER.md#subscription-management), Channel, Wildcard

---

### Tags
**Metadata dictionary** attached to messages for filtering and routing. V1.0 supports exact match filtering with OR logic within same key and AND logic across keys.

**Related:** [Messages](03-MESSAGES.md#tags), Metadata Filtering

---

### Timestamp
**ISO 8601 datetime** indicating when measurement was taken. COD3S Data **normalizes all timestamps to UTC** internally. Missing timezones assumed UTC (with warning).

**Related:** [Messages](03-MESSAGES.md#timezone-handling), Timezone

---

### Transformation
A component that **processes messages** (filter, compute, enrich, aggregate) and **publishes results**. Acts as both subscriber (to input channels) and publisher (to output channels).

**Related:** [Transformations](05-TRANSFORMATIONS.md), Stateful Transformation, Stateless Transformation

---

### TRANSPOSE Mode
Operational mode for sources that **replays historical data** while **preserving original timestamps**. Supports time scaling (speed up/slow down replay). Used for testing and analysis.

**Related:** [Sources](04-SOURCES.md#batch-modes), Batch Mode, REALTIME Mode

---

### Wildcard
Pattern matching operator for channel subscriptions:
- **`*`** (asterisk): Single-level wildcard (e.g., `sensors.*.temp` matches `sensors.printer1.temp`)
- **`**`** (double asterisk): Multi-level wildcard (e.g., `sensors.**` matches `sensors.temp`, `sensors.printer1.temp`, etc.)

**Related:** [Channels & Routing](07-CHANNELS-ROUTING.md#wildcard-subscriptions), Channel

---

## Components

### CollectDestination
A **test destination** that collects messages **in memory** for assertions. Used in unit and integration tests. Alias: `InMemoryDestination`.

**Related:** [Testing](12-TESTING.md#assertions-and-validation)

---

### ConsoleDestination
A destination that **prints messages to stdout**. Supports formats: pretty (human-readable), json (structured), compact (one-line). Used for debugging and development.

**Related:** [Destinations](06-DESTINATIONS.md#consoledestination)

---

### CSVSource
A source that reads **CSV files** with headers. Supports column mapping to message fields (timestamp, key, value, tags). Operates in BATCH or TRANSPOSE mode.

**Related:** [Sources](04-SOURCES.md#csvsource)

---

### FileDestination
A destination that **appends messages to files**. Supports formats: jsonl (JSON lines), json (array), csv. Includes file rotation (size, age, count limits).

**Related:** [Destinations](06-DESTINATIONS.md#filedestination)

---

### FileSource
A source that reads **line-delimited files** (JSON lines format). Supports field extraction from JSON objects. Operates in BATCH or TRANSPOSE mode.

**Related:** [Sources](04-SOURCES.md#filesource)

---

### RandomSource
A test source that generates **random numeric values**. Configurable: value range, rate, duration. Used for testing, simulation, demos.

**Related:** [Sources](04-SOURCES.md#randomsource), SequenceSource, TestSource

---

### SequenceSource
A test source that generates **numeric sequences** (start, stop, step). Produces deterministic output for testing.

**Related:** [Sources](04-SOURCES.md#sequencesource), RandomSource, TestSource

---

### TestSource
A test source that injects **custom messages**. Accepts list of pre-constructed messages. Used for edge case testing and specific scenarios.

**Related:** [Testing](12-TESTING.md#test-sources), RandomSource, SequenceSource

---

## Messaging

### At-Least-Once Delivery
**Delivery guarantee** where messages are **not lost** (except DLQ), but may be **delivered multiple times** due to retries. Requires acknowledgment from broker. Higher latency than at-most-once.

**Related:** [Messages](03-MESSAGES.md#at-least-once), At-Most-Once Delivery, Deduplication

---

### At-Most-Once Delivery
**Delivery guarantee** (default) where messages are **fire-and-forget** - may be lost on failure, but **never duplicated**. Low latency, high throughput. No retries.

**Related:** [Messages](03-MESSAGES.md#at-most-once), At-Least-Once Delivery

---

### Deduplication
Process of **removing duplicate messages**. In COD3S Data, deduplication is a **transformation** (not built into broker). Strategies: key+timestamp, key+timestamp+value, message_id.

**Related:** [Messages](03-MESSAGES.md#duplicate-detection), Cache, Stateful Transformation

---

### Fan-Out
Pattern where **one message** is delivered to **multiple subscribers**. Broker sends same message instance to all matching subscriptions.

**Related:** [Architecture](02-ARCHITECTURE.md#data-flow-patterns), Broker, Subscription

---

### Key
The **identifier field** in a message indicating **what is being measured** (e.g., "temperature", "speed", "viscosity"). String type, required.

**Related:** [Messages](03-MESSAGES.md#message-structure), Value, Message

---

### Message ID
**Unique identifier (UUID)** for each message. Auto-generated if not provided by source. Used for tracing, deduplication, and audit. Preserved through transformations (if message is passed through).

**Related:** [Messages](03-MESSAGES.md#message-id), Trace ID

---

### Metadata Filtering
Filtering messages based on **tag values** (in addition to channel pattern matching). V1.0 supports exact match + OR logic. Applied at destination level.

**Related:** [Channels & Routing](07-CHANNELS-ROUTING.md#metadata-filtering), Tags

---

### Ordering Guarantee
COD3S Data **does not guarantee message ordering**. Messages may arrive out of timestamp order due to network delays, parallel processing, retries. Applications should sort by timestamp if order matters.

**Related:** [Messages](03-MESSAGES.md#message-ordering), Out-of-Order Messages

---

### Out-of-Order Messages
Messages that arrive with **timestamps older than previously seen messages**. Default: accepted with warning. Optional: rejected (strict mode) and sent to DLQ.

**Related:** [Messages](03-MESSAGES.md#out-of-order-messages), Ordering Guarantee

---

### Retry Strategy
Configuration for **automatic retry** of failed operations (message delivery, destination writes). Strategies: exponential backoff (default), fixed backoff. Configurable attempts, delays, and DLQ channel.

**Related:** [Messages](03-MESSAGES.md#retry-strategies), Dead Letter Queue, Backpressure

---

### Trace ID
**Unique identifier** attached to a message for **end-to-end tracking** through the pipeline. All logs for same message share trace_id. Enables correlation across components.

**Related:** [Observability](10-OBSERVABILITY.md#tracing), Message ID

---

### Value
The **actual measurement** in a message. Can be: number, string, boolean, JSON object, array. No schema enforcement in V1.0 - destinations handle type mismatches.

**Related:** [Messages](03-MESSAGES.md#message-structure), Key, Message

---

## Configuration

### Configuration Hierarchy
**Override order** for configuration (highest to lowest priority):
1. Python API (programmatic)
2. Environment Variables (runtime)
3. YAML Files (declarative)
4. Framework Defaults (built-in)

**Related:** [Configuration](09-CONFIGURATION.md#configuration-hierarchy)

---

### Environment Variable Substitution
Mechanism to **inject environment variables** into YAML configuration using `${VAR_NAME}` syntax. Used for secrets, deployment-specific values.

**Related:** [Configuration](09-CONFIGURATION.md#environment-variables)

---

### YAML Configuration
**Declarative configuration** format for defining sources, transformations, destinations, broker settings. Human-readable, version-controllable. Supports environment variable substitution.

**Related:** [Configuration](09-CONFIGURATION.md#yaml-configuration), Python API Configuration

---

### Python API Configuration
**Programmatic configuration** via Python code. Allows dynamic configuration, custom logic, conditional setup. Alternative or complement to YAML configuration.

**Related:** [Configuration](09-CONFIGURATION.md#python-api-configuration), YAML Configuration

---

## Operations

### Buffer
**Bounded queue** for storing messages temporarily. Used in:
- **Destinations**: Handle rate mismatches (slow consumers)
- **Broker History**: Recent messages for late-joining subscribers

Prevents memory exhaustion via size limits and overflow strategies.

**Related:** [Destinations](06-DESTINATIONS.md#buffering-and-backpressure), History Buffer, Overflow Strategy

---

### CLI Mode
**Deployment mode** where COD3S Data runs as **command-line tool** for ad-hoc tasks, testing, validation, batch processing. Short-lived execution.

**Related:** [Deployment](11-DEPLOYMENT.md#cli-tool-mode), Embedded Mode, Standalone Mode

---

### Debug Mode
**Logging mode** with verbose output (DEBUG level). Logs message contents, channel activity, internal state. Higher overhead - use for troubleshooting only.

**Related:** [Observability](10-OBSERVABILITY.md#debug-mode), Logging

---

### Embedded Mode
**Deployment mode** where COD3S Data is used as a **library** within existing Python application. Same process, shared resources. Direct API access.

**Related:** [Deployment](11-DEPLOYMENT.md#embedded-library-mode), Standalone Mode, CLI Mode

---

### History Buffer
**Bounded buffer** in broker storing recent messages per channel. Enables **late-joining subscribers** to receive context (recent history) when subscribing. Configurable size and TTL.

**Related:** [Broker](08-BROKER.md#history-buffer), Subscription, Buffer

---

### Metrics as Messages
**Observability pattern** where framework metrics are **published as regular messages** on `_metrics.*` channels. Enables metrics consumption using same subscription model as data.

**Related:** [Observability](10-OBSERVABILITY.md#metrics-as-messages), System Channels

---

### Overflow Strategy
**Behavior when buffer is full**:
- **drop_oldest** (default): Discard oldest message, add new
- **drop_newest**: Reject incoming message
- **block**: Wait until space available (with timeout)

**Related:** [Destinations](06-DESTINATIONS.md#overflow-strategies), Buffer, Backpressure

---

### Record and Replay
**Testing pattern** where production data is **captured** (recorded to file) and later **replayed** in tests using TRANSPOSE mode. Enables testing with realistic data.

**Related:** [Testing](12-TESTING.md#record-and-replay), TRANSPOSE Mode

---

### Standalone Mode
**Deployment mode** where COD3S Data runs as **separate process** (service). Managed by OS (systemd) or orchestrator (Docker, Kubernetes). Process isolation.

**Related:** [Deployment](11-DEPLOYMENT.md#standalone-service-mode), Embedded Mode, CLI Mode

---

### System Channels
**Reserved channels** (prefix `_`) for framework internal use:
- `_dlq.*` - Dead Letter Queue
- `_metrics.*` - Framework metrics
- `_logs.*` - Structured logs (optional)
- `_control.*` - Control commands (future)

**Related:** [Channels & Routing](07-CHANNELS-ROUTING.md#system-channels), Dead Letter Queue, Metrics

---

### Timezone Normalization
Process of **converting timestamps to UTC** internally. COD3S Data accepts ISO 8601 timestamps with any timezone, normalizes to UTC for processing. Original timezone not preserved.

**Related:** [Messages](03-MESSAGES.md#timezone-handling), Timestamp

---

## Performance

### Latency (p99)
**99th percentile latency** - time for 99% of messages to traverse pipeline (publish to subscriber notification). V1.0 target: <50ms p99.

**Related:** [Broker](08-BROKER.md#performance-characteristics), Throughput

---

### Throughput
**Message rate** (messages per second). V1.0 target: 10,000 msg/s single-instance. Measured at broker level.

**Related:** [Broker](08-BROKER.md#performance-characteristics), Latency

---

### Time Window
**State helper** for stateful transformations. Collects messages within fixed time intervals (e.g., 5 minutes). Used for time-based aggregations (averages, sums, counts).

**Related:** [Transformations](05-TRANSFORMATIONS.md#timewindow), Count Window, Stateful Transformation

---

### Count Window
**State helper** for stateful transformations. Collects N messages before processing (sliding or tumbling window). Used for moving averages, count-based aggregations.

**Related:** [Transformations](05-TRANSFORMATIONS.md#countwindow), Time Window, Stateful Transformation

---

### Cache
**State helper** for stateful transformations. In-memory dictionary with TTL (time-to-live) expiration. Used for deduplication, lookups, rate limiting.

**Related:** [Transformations](05-TRANSFORMATIONS.md#cache), Deduplication, Stateful Transformation

---

## Acronyms

### API
**Application Programming Interface** - Programmatic interface for interacting with COD3S Data (Python API, HTTP API in V2.0).

---

### CEP
**Complex Event Processing** - Advanced pattern detection and correlation across multiple event streams. Planned for V3.0+.

**Related:** [Future Roadmap](13-FUTURE-V2-V3.md#complex-event-processing-cep)

---

### CLI
**Command-Line Interface** - Terminal-based interface for running COD3S Data commands (run, validate, test, monitor).

**Related:** [Deployment](11-DEPLOYMENT.md#cli-tool-mode)

---

### CSV
**Comma-Separated Values** - File format for tabular data. Supported by CSVSource and FileDestination.

---

### DLQ
**Dead Letter Queue** - Channels (`_dlq.*`) receiving failed messages after retry exhaustion.

**Related:** [Dead Letter Queue](#dead-letter-queue)

---

### ETL
**Extract, Transform, Load** - Data integration pattern. COD3S Data supports ETL workflows (extract via sources, transform via transformations, load via destinations).

---

### HTTP
**Hypertext Transfer Protocol** - Web protocol. V2.0 adds HTTP sources (polling), HTTP destinations (webhooks), and HTTP management API.

**Related:** [Future Roadmap](13-FUTURE-V2-V3.md#http-and-websocket)

---

### IoT
**Internet of Things** - Network of physical devices with sensors. COD3S Data designed for IoT sensor data processing.

---

### ISO 8601
**International standard** for date/time representation. Format: `2024-01-15T10:30:45Z`. Required timestamp format in COD3S Data.

---

### JSON
**JavaScript Object Notation** - Text-based data format. Used for message serialization, configuration, logging.

---

### JSONL
**JSON Lines** - Text format with one JSON object per line. Used by FileSource and FileDestination.

---

### ML
**Machine Learning** - Planned for V3.0+ (model inference, online learning, feature store integration).

**Related:** [Future Roadmap](13-FUTURE-V2-V3.md#ml-model-integration)

---

### MQTT
**Message Queuing Telemetry Transport** - Lightweight pub/sub protocol for IoT. V2.0 adds MQTT source and destination.

**Related:** [Future Roadmap](13-FUTURE-V2-V3.md#message-brokers)

---

### TTL
**Time-To-Live** - Expiration time for cached data (history buffer, deduplication cache, state).

---

### UTC
**Coordinated Universal Time** - Timezone-agnostic time standard. All timestamps normalized to UTC in COD3S Data.

**Related:** [Timezone Normalization](#timezone-normalization)

---

### UUID
**Universally Unique Identifier** - 128-bit identifier. Used for message IDs and trace IDs.

---

### YAML
**YAML Ain't Markup Language** - Human-readable data serialization format. Primary configuration format for COD3S Data.

**Related:** [YAML Configuration](#yaml-configuration)

---

## Cross-References

### See Also

For comprehensive coverage, explore:

- **[Architecture](02-ARCHITECTURE.md)** - System design and component interactions
- **[Messages](03-MESSAGES.md)** - Core message model and guarantees
- **[Sources](04-SOURCES.md)** - Data ingestion patterns
- **[Transformations](05-TRANSFORMATIONS.md)** - Processing capabilities
- **[Destinations](06-DESTINATIONS.md)** - Data output patterns
- **[Channels & Routing](07-CHANNELS-ROUTING.md)** - Message routing concepts
- **[Broker](08-BROKER.md)** - Central message distribution
- **[Configuration](09-CONFIGURATION.md)** - System configuration approaches
- **[Observability](10-OBSERVABILITY.md)** - Monitoring and debugging
- **[Deployment](11-DEPLOYMENT.md)** - Deployment modes and packaging
- **[Testing](12-TESTING.md)** - Testing strategies and patterns
- **[Future Roadmap](13-FUTURE-V2-V3.md)** - Planned V2.0 and V3.0+ features

---

## Navigation

| Previous | Up | Next |
|----------|-----|------|
| [← 13-FUTURE-V2-V3](13-FUTURE-V2-V3.md) | [OVERVIEW](00-OVERVIEW.md) | - |

---

*This glossary provides comprehensive terminology for COD3S Data Framework v1.0.*
