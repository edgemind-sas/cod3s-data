# COD3S Data Framework - Specification Q&A Session

**Date:** 2026-01-23
**Status:** In Progress
**Progress:** 6/45+ questions completed

---

## ✅ Completed Questions & Decisions

### Theme 1: Message Delivery Guarantees & Reliability

#### **Q1.1: Message Delivery Semantics**
**Question:** What guarantees should the framework provide when delivering messages?

**Decision:** **Option F - Configurable per source**
- **Default:** At-most-once (fire-and-forget)
- **Opt-in:** At-least-once (source waits for ACK, retries on failure)
- **Failed retries:** Send to Dead Letter Queue (DLQ)
- **Rationale:** Flexibility - critical sources get guarantees, non-critical stay fast

**Key Details:**
```yaml
source:
  delivery_guarantee: "at-least-once"  # or "at-most-once" (default)
  retry_attempts: 3
  retry_timeout: 5s
  dead_letter_channel: "_dlq.failed_messages"
```

---

#### **Q1.2: Message Ordering Guarantees**
**Question:** Should the framework guarantee message ordering?

**Decision:** **Option A - No ordering guarantee**
- Messages can arrive in any order
- Applications sort by timestamp if order matters
- **Rationale:** Simplest, most scalable, matches distributed reality

**Key Details:**
- Each message has timestamp
- Applications handle ordering at their level if needed
- Acceptable for temporal data (timestamps provide logical order)

---

#### **Q1.3: Failure Recovery Strategy**
**Question:** What happens when a destination fails to process a message?

**Decision:** **Option F - Retry + Dead Letter Queue**
- Retry with exponential backoff (configurable attempts)
- If all retries exhausted → send to DLQ
- Circuit breaker: Deferred to Phase 2
- **Rationale:** Production-ready, handles transient failures, captures permanent failures

**Key Details:**
```yaml
destination:
  retry_attempts: 3                    # 0 = no retries
  retry_backoff: "exponential"         # or "fixed"
  retry_initial_delay: 1s
  retry_max_delay: 60s
  dead_letter_channel: "_dlq.db_failures"  # optional
```

---

### Theme 2: Data Flow Control & Backpressure

#### **Q2.1: Slow Consumer Handling**
**Question:** What happens when a destination cannot keep up with message rate?

**Decision:** **Option F - Configurable per destination**
- **Default:** Bounded buffer (1000 messages) + drop oldest + warning
- **Configurable:** buffer_size and overflow_strategy per destination
- **Rationale:** Memory-safe by default, flexible for different needs

**Key Details:**
```yaml
destination:
  buffer_size: 1000                    # default
  overflow_strategy: "drop_oldest"     # default (or "drop_newest")
  overflow_warning_rate: 60s           # log warning rate
```

**Deferred:**
- Backpressure to sources (Phase 2 - complex coordination)
- Destination bypass (Phase 2)

---

#### **Q2.2: Batch Processing Cancellation**
**Question:** Should long-running batch sources (REALTIME/TRANSPOSE) be controllable?

**Decision:** **Option D - Full control**
- Cancel (stop immediately)
- Pause/Resume (temporary pause)
- Progress monitoring (status, completion %)
- **Rationale:** REALTIME mode can run for days, users need control and visibility

**Key Details:**
```python
handle = source.start()

# Control
handle.cancel()
handle.pause()
handle.resume()

# Observability
status = handle.get_status()
# Returns: total_messages, sent, remaining, state, elapsed_time, eta

# Synchronization
handle.wait_for_completion(timeout=3600)
handle.is_complete()
```

---

#### **Q2.3: Historical Message Access**
**Question:** When a destination subscribes, what messages should it receive?

**Decision:** **Option D - Configurable per destination**
- **Default:** Recent history (last N messages from buffer, e.g., 100)
- **Options:**
  - `history="none"` - new messages only (real-time)
  - `history="recent"` - last N messages + new (default)
  - `history="all"` - full replay from beginning (if broker supports)
- **Rationale:** Good default (context for late-joiners), flexibility when needed

**Key Details:**
```python
# Default (recent history)
destination = Destination(channel="sensors.temp")
# → Receives last 100 messages + new messages

# Real-time only
destination = Destination(channel="sensors.temp", history="none")

# Full replay (if supported)
destination = Destination(channel="sensors.temp", history="all")

# Custom buffer size
destination = Destination(
    channel="sensors.temp",
    history="recent",
    history_size=1000
)
```

---

---

### Theme 3: Filtering & Routing Advanced Features

#### **Q3.1: Filter Expressiveness**
**Question:** How powerful should the metadata filtering system be?

**Decision:** **Option G - Start simple, design for extension**
- **Phase 1 (v1.0):** Exact match + OR support
  - AND logic across different keys
  - OR logic within same key (list of values)
  - All values are strings (exact match)
- **Phase 2 (future):** Wildcards, NOT logic, comparisons, custom filter plugins
- **Rationale:** Solves 80% of use cases, simple implementation, clear extension path

**Key Details:**
```python
# Exact match (AND across keys)
filter = {"location": "warehouse_A", "sensor_type": "temperature"}

# OR support via lists
filter = {
    "location": ["warehouse_A", "warehouse_B", "warehouse_C"],  # OR
    "sensor_type": "temperature"                                 # AND
}
# Matches: (location=A OR location=B OR location=C) AND sensor_type=temperature
```

**Deferred to Phase 2:**
- Wildcard patterns (`"sensor_id": "TH*"`)
- NOT logic (`"status!": "maintenance"`)
- Value comparisons (`"priority": ">= 5"`)
- Full expression language

---

#### **Q3.2: Dynamic Routing**
**Question:** How should channels be created and how should destinations subscribe to them?

**Decision:** **Option E - Dynamic creation + hierarchical wildcards**
- **Dynamic creation:** Channels created implicitly on first use (no predeclaration)
- **Hierarchical naming:** Recommended convention `domain.subdomain.metric`
- **Wildcard subscriptions:**
  - `*` = single-level wildcard (e.g., `sensors.*.temperature`)
  - `**` = multi-level wildcard (e.g., `sensors.**`)
- **Rationale:** Flexible for dynamic systems, reduces configuration, industry standard pattern

**Key Details:**
```python
# Source creates channel dynamically
source = Source(channel="sensors.warehouse_A.temperature")

# Exact subscription
dest1 = Destination(channel="sensors.warehouse_A.temperature")

# Wildcard subscriptions
dest2 = Destination(channel="sensors.*.temperature")      # All warehouses, temp only
dest3 = Destination(channel="sensors.warehouse_A.*")      # Warehouse A, all types
dest4 = Destination(channel="sensors.**")                 # All sensors
```

**Channel naming rules:**
- Valid characters: `a-z, A-Z, 0-9, -, _, .`
- Separator: `.` (dot for hierarchy)
- Reserved prefix: `_` (for system channels: `_dlq`, `_metrics`)
- Max length: 255 characters

**Deferred to Phase 2:**
- Content-based routing (use transformations instead)
- Static channel validation mode

---

#### **Q3.3: Transformation Rules**
**Question:** What capabilities should transformations have? How flexible should they be in consuming and producing messages?

**Decision:** **Option F-Extended - Stateful transformations with multi-channel support**
- **Stateless single-channel:** Simple 1:N transformations (filtering, alerts, splitting)
- **Stateful multi-channel:** N:M transformations consuming from multiple channels
- **Framework-managed state:** Helpers for common patterns (latest values, windows, caching)
- **Rationale:** Supports simple alarms AND complex computed indicators from multiple sensors (e.g., viscosity from temp+speed+force)

**Key Details:**

**A. Stateless Single-Channel (Simple):**
```python
# 1:N transformation (returns 0, 1, or N messages)
def transform(message: Message) -> List[Message]:
    if message.value > threshold:
        return [message, alert_message]  # Original + Alert
    return [message]  # Just original

# Patterns: filtering (1:0), pass-through (1:1), splitting (1:N)
```

**B. Stateful Multi-Channel (Complex):**
```python
class ViscosityComputer(StatefulTransform):
    input_channels = ["sensors.temp", "sensors.speed", "sensors.force"]
    output_channel = "indicators.viscosity"

    def transform(self, message: Message) -> List[Message]:
        # self.latest = {channel: latest_message} (framework-managed)

        if len(self.latest) < 3:
            return []  # Wait for all sensors

        viscosity = compute(
            self.latest["sensors.temp"].value,
            self.latest["sensors.speed"].value,
            self.latest["sensors.force"].value
        )

        return [Message(key="viscosity", value=viscosity)]
```

**C. Framework-Provided State Helpers:**
- `self.latest` - Dictionary of latest message per input channel
- `TimeWindow(duration)` - Collect messages in time windows
- `CountWindow(size)` - Collect N messages
- `Cache(ttl)` - Deduplication/caching with TTL

**Use Cases:**
- **Simple:** Threshold alarms, unit conversion, filtering
- **Complex:** Computed indicators from multiple sensors, ML inference, aggregations

**Deferred to Phase 2:**
- Multi-channel join/correlation patterns (event matching)
- Complex event processing (pattern detection)
- Persistent state backends
- Distributed stateful transformations

---

### Theme 4: Time Handling & Edge Cases

#### **Q4.1: Out-of-Order Timestamp Handling**
**Question:** What should the framework do when messages arrive with out-of-order timestamps?

**Decision:** **Hybrid - Accept as-is (default) + Optional rejection + Always warn**
- **Default behavior:** Accept all messages regardless of timestamp order (no buffering, no rejection)
- **Optional mode:** Can enable "reject older than latest" per channel/destination
- **Always:** Emit warnings and metrics when out-of-order detected
- **Rationale:** Simple default for most cases, strict mode for critical channels, full visibility

**Key Details:**

**Default Mode (Accept All):**
```python
# Messages processed in arrival order, regardless of timestamp
# All messages accepted and processed
# No buffering, no latency added
# self.latest in transformations = most recently ARRIVED (not latest timestamp)
```

**Strict Mode (Reject Older - Optional):**
```yaml
channel:
  "sensors.critical.temperature":
    reject_out_of_order: true  # Enable strict mode

# Or per destination:
destination:
  critical_analyzer:
    channel: "sensors.temp"
    reject_out_of_order: true
```

**Behavior:**
```python
# Channel tracks latest timestamp seen
# Messages with timestamp < latest are rejected

Channel "sensors.temp" (strict mode enabled):
  msg@11:00:01 → Accepted (latest=11:00:01)
  msg@11:00:02 → Accepted (latest=11:00:02)
  msg@11:00:00 → REJECTED (older than latest)
    → Sent to DLQ: "_dlq.out_of_order.sensors.temp"
    → Warning logged
    → Metric: out_of_order_rejected++
```

**Monitoring (Always Active):**
```python
# Metrics emitted for all channels (both modes):
metrics = {
    "messages_out_of_order": 42,           # Count of out-of-order messages
    "out_of_order_accepted": 35,           # Default mode: accepted
    "out_of_order_rejected": 7,            # Strict mode: rejected
    "max_timestamp_skew_ms": 1500          # Worst skew observed
}

# Warnings logged:
WARNING: Out-of-order message on channel 'sensors.temp'
  Current timestamp: 11:00:00.000
  Expected after: 11:00:02.000
  Skew: -2000ms
  Action: Accepted (default mode) | Rejected (strict mode)
```

**Transformation Helpers:**
```python
class ViscosityComputer(StatefulTransform):
    def transform(self, message):
        # Check timestamp alignment across multi-channel inputs
        skew = self.get_timestamp_skew()  # Helper: max - min timestamp

        if skew > 1.0:  # More than 1 second skew
            log.warning(f"Sensor timestamp skew: {skew}s")
            return []  # Skip computation until aligned

        # Compute with current values
        return [compute_viscosity(...)]
```

**Configuration Example:**
```yaml
# Global default
broker:
  reject_out_of_order: false  # Default: accept all
  warn_out_of_order: true     # Always warn

# Critical channels override
channels:
  "sensors.safety.*":
    reject_out_of_order: true  # Safety-critical: strict ordering

  "sensors.debug.*":
    warn_out_of_order: false   # Debug: don't spam logs
```

**Deferred to Phase 2:**
- Buffering/reordering within time windows (adds latency)
- Configurable buffer strategies

---

#### **Q4.2: Duplicate Message Detection**
**Question:** Should the framework detect and filter duplicate messages?

**Decision:** **Option E - Deduplication as transformation (not framework core)**
- **No built-in deduplication** in broker/channels (keeps core simple)
- **Built-in deduplication transformation** provided for explicit use
- **Users opt-in** when using at-least-once sources
- **Rationale:** Most sources use at-most-once (no duplicates), at-least-once sources can add explicit dedup step

**Key Details:**

**Framework Core:**
- No automatic deduplication
- All messages passed through as received
- Applications/transformations handle if needed

**Built-in Deduplication Transformation:**
```python
class DeduplicationTransform(StatefulTransform):
    """Built-in transformation for filtering duplicate messages"""

    def __init__(self, window=60, strategy="key+timestamp"):
        self.cache = Cache(ttl=window)
        self.strategy = strategy

    def transform(self, message):
        # Generate deduplication key based on strategy
        if self.strategy == "key+timestamp":
            dedup_key = (message.key, message.timestamp)
        elif self.strategy == "key+timestamp+value":
            dedup_key = (message.key, message.timestamp, message.value)

        if dedup_key in self.cache:
            return []  # Duplicate - filter out

        self.cache.add(dedup_key)
        return [message]  # First occurrence - pass through
```

**Configuration Example:**
```yaml
# For at-least-once sources, add explicit dedup step
source:
  type: temperature_sensor
  channel: "sensors.temp.raw"
  delivery_guarantee: "at-least-once"  # May produce duplicates

transformations:
  - type: deduplication
    input_channel: "sensors.temp.raw"
    output_channel: "sensors.temp.clean"
    window: 60s
    strategy: "key+timestamp"

destinations:
  - channel: "sensors.temp.clean"  # Receives deduplicated messages
```

**Deduplication Strategies:**
- `"key+timestamp"` - Same key and timestamp = duplicate (default)
- `"key+timestamp+value"` - Same key, timestamp, AND value = duplicate
- Future: `"message_id"` if message ID field added

**Monitoring:**
```python
# Dedup transformation emits metrics
metrics = {
    "messages_received": 1000,
    "duplicates_filtered": 42,
    "unique_messages": 958
}
```

**Recommended Pattern:**
```
At-most-once source:
  Source → Channel → Destinations (no dedup needed)

At-least-once source:
  Source → Raw Channel → Dedup Transform → Clean Channel → Destinations
```

---

#### **Q4.3: Timezone Strategy**
**Question:** How should the framework handle timezones in message timestamps?

**Decision:** **Option B - Accept any timezone, normalize to UTC internally**
- **Accept:** ISO 8601 timestamps with any valid timezone offset
- **Normalize:** All timestamps converted to UTC for internal storage/processing
- **No preservation:** Original timezone information not kept
- **Missing timezone:** Assume UTC (with warning logged)
- **Rationale:** Flexible for sources, simple for applications, industry standard

**Key Details:**

**Accepted Formats:**
```python
# Valid timestamp formats (all accepted)
"2024-01-15T10:00:00Z"           # UTC with Z suffix (preferred)
"2024-01-15T10:00:00+00:00"      # UTC explicit
"2024-01-15T10:00:00+01:00"      # Paris time
"2024-01-15T04:00:00-05:00"      # New York time
"2024-01-15T10:00:00"            # No timezone (assumed UTC, warning)
```

**Normalization Behavior:**
```python
# All timestamps converted to UTC internally
Source (Paris):     "2024-01-15T10:00:00+01:00"
Stored/Processed:   "2024-01-15T09:00:00Z"

Source (New York):  "2024-01-15T04:00:00-05:00"
Stored/Processed:   "2024-01-15T09:00:00Z"

# Both represent same instant, normalized for easy comparison
```

**Missing Timezone Handling:**
```python
# Timestamp without timezone indicator
Input: "2024-01-15T10:00:00"

Behavior:
  - Assume UTC (treat as "2024-01-15T10:00:00Z")
  - Log warning: "Timestamp missing timezone, assumed UTC"
  - Emit metric: timestamps_missing_timezone++
  - Process normally (not rejected)
```

**Recommendations:**
```yaml
# Best practice for sources
timestamp_format: ISO 8601 with UTC
examples:
  preferred: "2024-01-15T10:00:00Z"
  acceptable: "2024-01-15T10:00:00+01:00"  # Will be normalized
  avoid: "2024-01-15T10:00:00"  # Missing timezone (ambiguous)
```

**For Applications/Transformations:**
```python
# All received timestamps are UTC
class ViscosityComputer(StatefulTransform):
    def transform(self, message):
        # message.timestamp is always UTC (already normalized)
        # No timezone conversion needed
        # Direct comparison works:

        if message.timestamp > self.last_computation_time:
            # Simple comparison (both UTC)
            compute()
```

**Benefits:**
- Sources can use local timezone (framework converts)
- All internal processing in UTC (no timezone complexity)
- Easy timestamp comparison (all same timezone)
- Multi-location deployments supported (automatic normalization)

---

### Theme 5: Default Component Catalog

#### **Q5.1: Default Sources Priority**
**Question:** Which source implementations should be included by default in v1.0?

**Decision:** **Start with essentials, expand based on needs**
- **Priority 1 (Must-have v1.0):** Core set for testing and data replay
- **Priority 2 (Nice-to-have v1.0):** Common integration patterns
- **Priority 3 (v2.0+):** Specialized/enterprise sources added as needed
- **Rationale:** Start lean, add sources based on real user needs

**Priority 1 - Must-Have v1.0:**

1. **CSV File Source**
   ```python
   CSVSource(
       file_path="historical_data.csv",
       timestamp_column="timestamp",
       key_column="sensor_id",
       value_column="temperature",
       metadata_columns=["location", "printer_id"],
       mode="BATCH" | "REALTIME" | "TRANSPOSE"
   )
   ```
   **Use case:** Historical data replay, testing with real data

2. **Synthetic Data Generator**
   ```python
   SyntheticSource(
       channel="sensors.temp",
       pattern="sine" | "random" | "step" | "constant" | "linear",
       base_value=200,
       amplitude=20,
       rate=10  # messages/sec
   )
   ```
   **Use case:** Algorithm testing, load testing, demos

3. **Timer/Heartbeat Source**
   ```python
   TimerSource(
       channel="system.heartbeat",
       interval=1.0,  # seconds
       payload={"status": "alive"}
   )
   ```
   **Use case:** Periodic triggers, health checks

**Priority 2 - Nice-to-Have v1.0:**

4. **Console/Manual Input Source**
   ```python
   ConsoleSource(channel="sensors.temp")
   # Interactive: user types values
   ```
   **Use case:** Manual testing, debugging

5. **HTTP Polling Source**
   ```python
   HTTPPollingSource(
       url="http://device/api/sensors",
       interval=1.0,
       json_path="$.temperature"
   )
   ```
   **Use case:** IoT devices with REST APIs

6. **MQTT Source**
   ```python
   MQTTSource(
       broker="mqtt.local",
       topic="sensors/+/temperature",
       channel="sensors.temp"
   )
   ```
   **Use case:** IoT sensors, 3D printers (common protocol)

**Deferred to v2.0+ (Add as needed):**
- JSON/JSONL File Source
- Serial Port Source (for direct sensor connections)
- WebSocket Source
- Directory Watcher
- HTTP Webhook Receiver
- Database Query Source
- Kafka Consumer
- Other industrial protocols (OPC-UA, Modbus, etc.)

---

#### **Q5.2: Default Destinations Priority**
**Question:** Which destination implementations should be included by default in v1.0?

**Decision:** **Start simple for framework development, add complex integrations later**
- **Priority 1 (v1.0):** Simple destinations for development/testing
- **Priority 2 (v2.0 - Important):** Database and message brokers for production
- **Priority 3 (v2.0+ - As needed):** Advanced integrations
- **Rationale:** Build framework core with simple destinations, add production integrations when core is stable

**Priority 1 - Must-Have v1.0 (Development/Testing):**

1. **Console/Stdout Destination**
   ```python
   ConsoleDestination(
       channel="sensors.temp",
       format="json" | "table" | "simple",
       filter={"location": "Paris"}
   )
   ```
   **Use case:** Debugging, development, quick inspection

2. **File Writer (CSV/JSON)**
   ```python
   FileDestination(
       channel="indicators.viscosity",
       file_path="/data/viscosity_log.csv",
       format="csv" | "json" | "jsonl",
       mode="append" | "overwrite",
       rotation="daily" | "size:100MB"  # Optional
   )
   ```
   **Use case:** Data logging, offline analysis, simple storage

3. **In-Memory Buffer Destination**
   ```python
   BufferDestination(
       channel="sensors.temp",
       max_size=1000
   )
   # Later: messages = dest.get_messages()  # For testing/assertions
   ```
   **Use case:** Unit testing, assertions, inspection

4. **Null/Discard Destination**
   ```python
   NullDestination(channel="sensors.temp")
   ```
   **Use case:** Benchmarking, load testing, placeholder

**Priority 2 - v2.0 Important (Production Use):**

5. **Database Destination (Time-Series)**
   ```python
   InfluxDBDestination(
       channel="sensors.**",
       connection_string="http://localhost:8086",
       database="sensor_data"
   )

   # Or generic SQL
   DatabaseDestination(
       connection_string="postgresql://...",
       table="measurements"
   )
   ```
   **Use case:** Persistent storage, historical queries, production data

6. **Message Broker Destinations**
   ```python
   # Kafka
   KafkaDestination(
       bootstrap_servers="kafka:9092",
       topic="sensor-data"
   )

   # MQTT
   MQTTDestination(
       broker="mqtt.local",
       topic="sensors/viscosity"
   )
   ```
   **Use case:** Enterprise integration, distributed systems

**Deferred to v2.0+ (Add as needed):**
- Logging Destination (structured logging integration)
- Email/SMTP Destination (alerts)
- Webhook/HTTP POST Destination (external integrations)
- Real-Time Dashboard Destination (web UI)
- Slack/Teams Notification Destination
- Cloud storage (S3, GCS, Azure Blob)

---

#### **Q5.3: Default Transformations Priority**
**Question:** Which transformation implementations should be included by default in v1.0?

**Decision:** **Essential generic transformations for v1.0, advanced features later**
- **Priority 1 (v1.0 must-have):** Core transformations for common patterns
- **Priority 2 (v1.0 nice-to-have):** Useful but not critical
- **Priority 3 (v2.0+):** Advanced/specialized transformations
- **Rationale:** Focus on reusable, generic transformations; domain-specific logic (e.g., viscosity) implemented by users

**Priority 1 - Must-Have v1.0:**

1. **Threshold Alert** (Already in original spec - UC-003)
   ```python
   ThresholdAlertTransform(
       input_channel="sensors.temp",
       output_channel="alerts.high_temp",
       threshold=250,
       comparison=">" | ">=" | "<" | "<=",
       emit_original=True  # Emit both original + alert
   )
   ```
   **Use case:** Critical alerts, monitoring thresholds

2. **Filter/Pass-Through**
   ```python
   FilterTransform(
       input_channel="sensors.temp.raw",
       output_channel="sensors.temp.valid",
       filter={"location": "Paris"},  # Metadata filter
       condition=lambda msg: msg.value > 0  # Value filter
   )

   # Or range filter
   RangeFilterTransform(
       min_value=-50,
       max_value=400
   )
   ```
   **Use case:** Data cleaning, remove invalid readings

3. **Deduplication** (From Q4.2)
   ```python
   DeduplicationTransform(
       input_channel="sensors.temp.raw",
       output_channel="sensors.temp.clean",
       window=60,
       strategy="key+timestamp"
   )
   ```
   **Use case:** Remove duplicates from at-least-once sources

4. **Map/Enrich**
   ```python
   EnrichTransform(
       add_tags={"unit": "celsius", "source": "printer_1"}
   )

   MapTransform(
       function=lambda msg: Message(
           ...msg,
           value=msg.value * 1.8 + 32,  # Custom transformation
           tags={**msg.tags, "unit": "fahrenheit"}
       )
   )
   ```
   **Use case:** Add metadata, modify values, general-purpose transformation

**Priority 2 - Nice-to-Have v1.0:**

5. **Sampling/Rate Limiter**
   ```python
   SamplingTransform(
       sample_rate=0.1  # Keep 10%
       # or
       sample_every=10  # Every 10th message
   )

   RateLimiterTransform(
       max_rate=10  # Max 10 msg/sec
   )
   ```
   **Use case:** Reduce data volume, prevent overload

6. **Moving Average** (Stateful)
   ```python
   MovingAverageTransform(
       input_channel="sensors.temp.noisy",
       output_channel="sensors.temp.smooth",
       window_size=10  # Last 10 messages
   )
   ```
   **Use case:** Smoothing noisy sensors

7. **Unit Conversion**
   ```python
   UnitConversionTransform(
       from_unit="celsius",
       to_unit="fahrenheit"
   )
   # Supports: temperature, length, speed, force, etc.
   ```
   **Use case:** Standardize units

**Deferred to v2.0+ (Add as needed):**
- Time Window Aggregation (hourly/daily summaries)
- Statistical Summary (mean, std, min, max over windows)
- Rate of Change / Derivative (velocity from position)
- Join/Correlate (multi-channel event correlation)
- Complex Event Processing (pattern detection)

**Note:** Domain-specific transformations (e.g., viscosity computation from temp+speed+force) are implemented by users using the stateful multi-channel transformation framework (Q3.3).

---

### Theme 6: Observability & Operations

#### **Q6.1: Metrics Collection Strategy**
**Question:** How should the framework expose metrics and operational data for monitoring?

**Decision:** **Metrics as messages (v1.0) + industry standard later**
- **v1.0:** Metrics published as messages to special system channels
- **v2.0:** Add Prometheus exporter or other industry standards
- **Flexibility:** Both can coexist or migrate to one after development
- **Rationale:** Elegant self-monitoring for v1.0, production-ready options for v2.0

**v1.0 Implementation - Metrics as Messages:**

**Framework auto-publishes to system channels:**
```python
# System channels (reserved prefix: _)
_metrics.channels.{channel_name}      # Per-channel metrics
_metrics.destinations.{dest_name}     # Per-destination metrics
_metrics.transformations.{trans_name} # Per-transformation metrics
_metrics.broker                       # Global broker metrics
```

**Example Metrics Messages:**
```python
# Channel throughput
Message(
    key="messages_total",
    timestamp=now,
    value=1234,
    tags={"channel": "sensors.temp", "type": "metric"}
)

# Destination buffer size
Message(
    key="buffer_size",
    timestamp=now,
    value=42,
    tags={"destination": "db_writer", "type": "metric"}
)
```

**Consuming Metrics (Development):**
```python
# Print to console
ConsoleDestination(channel="_metrics.**")

# Log to file
FileDestination(
    channel="_metrics.**",
    file_path="/var/log/cod3s/metrics.jsonl",
    format="jsonl"
)

# Filter specific metrics
ConsoleDestination(
    channel="_metrics.channels.**",
    filter=lambda msg: msg.key == "messages_rate"
)
```

**Key Metrics Exposed:**

**Per Channel:**
- `messages_total` - Total messages sent
- `messages_rate` - Messages/sec (1min avg)
- `last_message_time` - Last message timestamp

**Per Destination:**
- `messages_received` - Total received
- `messages_processed` - Successfully processed
- `messages_failed` - Failures (sent to DLQ)
- `buffer_size` - Current buffer size
- `buffer_dropped` - Dropped due to overflow
- `processing_latency_ms` - Avg processing time

**Per Transformation:**
- `messages_input` - Input count
- `messages_output` - Output count
- `processing_errors` - Error count

**Global Broker:**
- `uptime_seconds` - Broker uptime
- `channels_active` - Active channel count
- `destinations_active` - Active destination count

**Programmatic Access (Testing):**
```python
# For assertions in tests
stats = broker.get_metrics()
assert stats["channels"]["sensors.temp"]["messages_total"] == 100
```

**v2.0 Extension - Industry Standard Exporters:**

**Prometheus Exporter:**
```python
# Built-in Prometheus exporter (subscribes to _metrics.** channels)
PrometheusExporterDestination(
    channel="_metrics.**",
    port=9090
)

# Or as framework feature:
broker.start_prometheus_exporter(port=9090)

# Exposes standard Prometheus format at /metrics:
# cod3s_messages_total{channel="sensors.temp"} 1234
# cod3s_buffer_size{destination="db_writer"} 42
```

**Other Options (v2.0+):**
- StatsD push exporter
- InfluxDB line protocol
- OpenTelemetry integration
- CloudWatch/Datadog integrations

**Benefits:**
- **v1.0:** Simple, self-contained, uses framework's own capabilities
- **v2.0:** Production-ready standard monitoring
- **Coexistence:** Prometheus exporter reads from metrics channels (both work together)
- **Testing:** Easy to assert on metrics (subscribe to channel)

---

#### **Q6.2: Health Checks**
**Question:** What health check mechanisms should the framework provide?

**Decision:** **Option B - Simple HTTP health endpoint**
- Basic liveness/readiness check via HTTP endpoint
- Works with Docker HEALTHCHECK, Kubernetes probes, load balancers
- Detailed health monitoring via metrics (Q6.1)
- **Rationale:** Simple for containers, sufficient for orchestration, production monitoring via Prometheus

**v1.0 Implementation:**

**HTTP Health Endpoint:**
```python
# Start health server
broker.start_health_server(port=8080)

# GET http://localhost:8080/health
# Returns:
#   200 OK: {"status": "healthy"}
#   503 Service Unavailable: {"status": "unhealthy", "reason": "..."}
```

**Basic Health Criteria:**
1. **Broker is running** (process alive, not crashed)
2. **No critical failures** (not all destinations failing)
3. **Activity detected** (messages processed in last 60 seconds)

**Docker Integration:**
```dockerfile
# Dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
```

**Kubernetes Integration:**
```yaml
# k8s deployment
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```

**Response Format:**
```json
// Healthy
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "timestamp": "2024-01-15T10:00:00Z"
}

// Unhealthy
{
  "status": "unhealthy",
  "reason": "No message activity in last 60 seconds",
  "uptime_seconds": 3600,
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Deployment Scenarios:**

**Production (Docker + Kafka):**
```yaml
# docker-compose.yml
services:
  cod3s-broker:
    image: cod3s-data:latest
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 3s
      retries: 3
    environment:
      - BROKER_MODE=distributed
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

**Testing/Light Deployment (Local Broker):**
```python
# Local mode - simple in-memory broker
broker = LocalBroker()
broker.start_health_server(port=8080)

# Quick health check
$ curl http://localhost:8080/health
{"status": "healthy"}
```

**Detailed Health Monitoring:**
- Use metrics (Q6.1) for detailed component health
- Subscribe to `_metrics.**` channels
- Set up Prometheus alerts on metric thresholds
- Health endpoint is just basic liveness for orchestration

**Configuration:**
```yaml
health:
  enabled: true
  port: 8080
  path: /health
  activity_timeout: 60  # Seconds without messages = unhealthy
```

**Deferred to v2.0:**
- Component-level health (per destination/transformation)
- Configurable health check rules
- Health as messages (publish to `_health.**` channels)

---

#### **Q6.3: Debugging & Tracing**
**Question:** What debugging and tracing capabilities should the framework provide?

**Decision:** **Option C + B - Debug mode + Message tracing IDs**
- **Debug mode:** Configurable log levels for detailed troubleshooting
- **Trace IDs:** Optional message IDs to follow specific messages through pipeline
- **Rationale:** Debug mode for general troubleshooting, trace IDs for tracking specific message flows

**v1.0 Implementation:**

**Message Structure with Trace ID:**
```python
Message(
    id=None,           # Optional trace ID (auto-generated if None)
    key="temp",
    timestamp="2024-01-15T10:00:00Z",
    value=220,
    tags={"location": "Paris"}
)

# Framework auto-generates UUID if id=None
# Users can provide specific ID for messages they want to trace
```

**Debug Mode (Log Levels):**
```python
# Standard operation (INFO level)
broker = Broker()

# Enable debug mode
broker = Broker(log_level="DEBUG")
# or
broker.set_log_level("DEBUG")

# Per-component debugging
transformation.set_log_level("DEBUG")
destination.set_log_level("DEBUG")
channel.set_log_level("DEBUG")
```

**Debug Output with Trace IDs:**
```
# Standard INFO logs
[INFO] [abc-123] Message received on channel 'sensors.temp'
[INFO] [abc-123] Destination 'file_writer' processed successfully

# DEBUG logs (verbose)
[DEBUG] [abc-123] Channel 'sensors.temp': buffer_size=10, subscribers=3
[DEBUG] [abc-123] Message content: {"key": "temp", "value": 220, "tags": {...}}
[DEBUG] [abc-123] [ViscosityComputer] Received message on sensors.temp
[DEBUG] [abc-123] [ViscosityComputer] State: temp=220, speed=50, force=None
[DEBUG] [abc-123] [ViscosityComputer] Waiting for force (have 2/3 inputs)
[DEBUG] [def-456] [ViscosityComputer] Received message on sensors.force
[DEBUG] [def-456] [ViscosityComputer] All inputs ready, computing
[DEBUG] [def-456] [ViscosityComputer] Emitted viscosity=1.234 to indicators.viscosity
[DEBUG] [def-456] Destination 'file_writer': write took 15ms
```

**Trace ID Propagation:**
```python
# Transformations preserve/propagate trace IDs
class ViscosityComputer(StatefulTransform):
    def transform(self, message):
        # Input message has trace_id

        # Output inherits or derives trace ID
        return [Message(
            id=message.id,  # Preserve original trace ID
            # or
            id=generate_derived_id(message.id),  # New ID linked to original
            key="viscosity",
            value=compute(...),
            tags={**message.tags, "derived_from": message.id}
        )]
```

**Tracing Specific Messages:**
```python
# Mark specific message for tracing
debug_message = Message(
    id="DEBUG-temp-reading-1",  # Explicit ID for easy grepping
    key="temp",
    value=220,
    tags={"debug": "true"}
)

source.emit(debug_message)

# Later, find in logs:
$ grep "DEBUG-temp-reading-1" logs.txt
[INFO] [DEBUG-temp-reading-1] Message received on 'sensors.temp'
[DEBUG] [DEBUG-temp-reading-1] [ViscosityComputer] Processing
[INFO] [DEBUG-temp-reading-1] Emitted to 'indicators.viscosity'
```

**Benefits:**
- **Debug mode:** General troubleshooting, enable when needed
- **Trace IDs:** Follow specific messages through entire pipeline
- **Automatic:** IDs generated if not provided (no burden on simple sources)
- **Flexible:** Users control which messages to trace explicitly
- **Standard tooling:** Use grep, log aggregators to trace flows

**Logging Configuration:**
```yaml
logging:
  level: INFO              # Default log level
  format: "[{levelname}] [{trace_id}] {message}"

  # Per-component overrides
  components:
    broker: INFO
    transformations.viscosity_computer: DEBUG  # Debug specific transformation
    destinations.db_writer: DEBUG
```

**Use Cases:**

**General Debugging:**
```python
# Enable debug mode, see everything
broker.set_log_level("DEBUG")
# Analyze logs to understand system behavior
```

**Specific Message Tracing:**
```python
# Trace problematic sensor reading
source.emit(Message(
    id="trace-issue-42",
    key="temp",
    value=999  # Suspicious value
))

# Grep logs to see what happened:
$ grep "trace-issue-42" logs.txt
```

**Production Monitoring:**
```python
# INFO level in production (low overhead)
# Trace IDs in logs for incident investigation
# Enable DEBUG mode temporarily for specific issues
```

**Deferred to v2.0:**
- Correlation IDs (link multiple related messages)
- Distributed tracing integration (OpenTelemetry, Jaeger)
- Sampling/filtering (reduce log volume in production)
- Replay from logs (reproduce scenarios)

---

### Theme 7: Security & Data Integrity

#### **Q7.1: Authentication & Authorization**
**Question:** Should the framework include authentication and authorization in Phase 1?

**Decision:** **Option A - Defer to Phase 2**
- **v1.0:** No built-in authentication/authorization
- **Assumes:** Trusted environment (localhost, private network, Docker internal network)
- **Production guidance:** Use network-level security until v2.0
- **Rationale:** Focus on core functionality first, add security when production requirements are clear

**v1.0 Security Posture:**

**No Built-in Security:**
- No authentication (sources/destinations not verified)
- No authorization (no channel access control)
- No encryption (messages in plaintext)
- Assumes trusted network environment

**Deployment Security Recommendations:**

**Local/Development:**
```yaml
# Run on localhost only
broker:
  bind: 127.0.0.1  # Not 0.0.0.0
  port: 8080

# No external exposure
# Trusted users only
```

**Docker/Container:**
```yaml
# docker-compose.yml
services:
  cod3s-broker:
    networks:
      - internal  # Internal Docker network only
    # Don't expose ports to host unless needed
```

**Production (Network-Level Security):**
```
Options for securing v1.0 in production:

1. VPN/Private Network:
   - Deploy in private network (VPC, VPN)
   - No public internet exposure
   - Firewall rules limit access

2. Reverse Proxy with Auth:
   - Nginx/HAProxy in front of broker
   - HTTP Basic Auth, OAuth, mTLS
   - Proxy handles authentication

3. Service Mesh:
   - Istio, Linkerd for mTLS
   - Automatic encryption between services

4. Message Broker Security:
   - Kafka: Use SASL/ACLs
   - MQTT: Use username/password
   - Broker handles authentication
```

**Extension Points (for v2.0):**
```python
# Framework designed with auth hooks for future
class Source:
    def authenticate(self, credentials):
        # Hook for future authentication
        pass

class Broker:
    def authorize(self, principal, channel, operation):
        # Hook for future authorization
        pass
```

**v2.0 Security Roadmap:**
- **Authentication:** API keys, JWT tokens, OAuth integration
- **Authorization:** Channel-level ACLs (who can publish/subscribe)
- **Encryption:** TLS for distributed broker connections
- **Enterprise integration:** LDAP, Active Directory, SSO
- **Audit logging:** Track all security events

**Security Notice in Documentation:**
```
⚠️ SECURITY WARNING:

COD3S Data v1.0 has NO built-in security mechanisms.

For production deployments:
- Deploy in trusted networks only (private VPC, VPN)
- Use network firewalls to restrict access
- Consider reverse proxy for authentication (Nginx, API Gateway)
- For distributed mode, use broker's security (Kafka ACLs, MQTT auth)

v2.0 will include built-in authentication and authorization.
```

---

#### **Q7.2: Data Validation & Schema**
**Question:** Should the framework provide schema validation for messages?

**Decision:** **Option B (modified) - Type enforcement for structure, flexible value**
- **Typed fields:** key (string), timestamp (datetime), tags (dict)
- **Flexible field:** value (any type - number, string, JSON, binary, etc.)
- **Rationale:** Framework routes on structure; value is opaque application data that framework just passes through

**v1.0 Implementation:**

**Message Structure:**
```python
class Message:
    def __init__(self,
                 key: str,              # REQUIRED: string
                 timestamp: datetime|str,  # REQUIRED: datetime or ISO 8601 string
                 value: Any,            # REQUIRED: any type (no validation)
                 tags: dict = None,     # OPTIONAL: dict if provided
                 id: str = None):       # OPTIONAL: trace ID (from Q6.3)

        # Validate structure (framework needs these for routing)
        if not isinstance(key, str):
            raise TypeError(f"key must be str, got {type(key).__name__}")

        if tags is not None and not isinstance(tags, dict):
            raise TypeError(f"tags must be dict, got {type(tags).__name__}")

        # Timestamp: parse and normalize to UTC (from Q4.3)
        self.timestamp = self._parse_timestamp(timestamp)

        # ID: auto-generate if not provided (from Q6.3)
        self.id = id or self._generate_id()

        # Store validated fields
        self.key = key
        self.tags = tags or {}

        # Value: NO VALIDATION - accept any type
        self.value = value  # Can be int, float, str, dict, bytes, object, etc.
```

**Valid Messages (Value Flexibility):**
```python
# Numeric value (sensor reading)
Message(key="temp", timestamp=now, value=220.5)

# String value
Message(key="status", timestamp=now, value="running")

# JSON/dict value (complex data)
Message(key="sensor_reading", timestamp=now, value={
    "temperature": 220,
    "humidity": 45,
    "pressure": 1013
})

# Binary value (image, file)
Message(key="photo", timestamp=now, value=b'\x89PNG\r\n...')

# Custom object (application-specific)
Message(key="model_output", timestamp=now, value=MyCustomClass())

# List/array
Message(key="measurements", timestamp=now, value=[220, 225, 230])

# Boolean
Message(key="alarm_active", timestamp=now, value=True)

# None (explicit null)
Message(key="placeholder", timestamp=now, value=None)
```

**Invalid Messages (Structure Errors):**
```python
# Wrong key type
Message(key=123, ...)
→ TypeError: key must be str, got int

# Wrong tags type
Message(key="temp", timestamp=now, value=220, tags="invalid")
→ TypeError: tags must be dict, got str

# Invalid timestamp
Message(key="temp", timestamp="not-a-date", value=220)
→ ValueError: Invalid timestamp format

# Missing required fields
Message(key="temp")
→ TypeError: Missing required argument 'timestamp'
```

**Why Value is Flexible:**

1. **Different data types per use case:**
   ```python
   # Temperature: float
   Message(key="temp", value=220.5)

   # Status: string
   Message(key="status", value="operational")

   # Viscosity computation: dict with metadata
   Message(key="viscosity", value={
       "result": 1.234,
       "confidence": 0.95,
       "inputs": {"temp": 220, "speed": 50, "force": 100}
   })

   # Image from camera: bytes
   Message(key="image", value=camera.capture())
   ```

2. **Framework doesn't need to know:**
   - Framework routes based on: channel, key, tags, timestamp
   - Value is just payload - passed through unchanged
   - Transformations interpret value as needed

3. **Applications validate:**
   ```python
   class ViscosityComputer(StatefulTransform):
       def transform(self, message):
           # Application validates value as needed
           if not isinstance(message.value, (int, float)):
               raise ValueError(f"Expected numeric value, got {type(message.value)}")

           if not (-50 <= message.value <= 400):
               raise ValueError(f"Value out of range: {message.value}")

           # Process...
   ```

**Timestamp Validation (from Q4.3):**
```python
def _parse_timestamp(self, timestamp):
    """Parse and normalize timestamp to UTC"""
    if isinstance(timestamp, datetime):
        # Already datetime, normalize to UTC
        return timestamp.astimezone(timezone.utc)

    if isinstance(timestamp, str):
        # Parse ISO 8601 string
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.astimezone(timezone.utc)
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {timestamp}")

    raise TypeError(f"timestamp must be str or datetime, got {type(timestamp).__name__}")
```

**Benefits:**

- **Catch structural errors early:** Wrong key type, invalid tags
- **Flexible value:** Support any data type (numeric, text, binary, JSON, custom objects)
- **Clear errors:** Know immediately if structure is wrong
- **Type hints:** IDE autocomplete and type checking
- **Future-proof:** Can add value validation later if needed (v2.0)

**Deferred to v2.0:**
- Schema registry (per-channel schemas)
- Value type validation (if value must be specific type)
- Value range constraints (min/max for numeric values)
- Required tag validation (tags must include specific keys)
- Custom validators (user-defined validation functions)

---

### Theme 8: Extensibility & Plugin Architecture

#### **Q8.1: Plugin System Design**
**Question:** How should users extend the framework with custom components?

**Decision:** **Option E - Combination (Interface-based + Configuration-based)**
- **Primary:** Interface-based - implement Python classes (Source, Destination, Transform)
- **Secondary:** Configuration-based - YAML/JSON for built-in components
- **Rationale:** Code for custom logic (full control), config for built-ins (simplicity)

**v1.0 Implementation:**

**Interface-Based Extension (Primary):**

**Base Classes:**
```python
# Framework provides base classes
from cod3s import Source, Destination, StatefulTransform, Message

class Source:
    """Base class for message sources"""
    def __init__(self, channel: str):
        self.channel = channel
        self.running = False

    def emit(self, message: Message):
        """Emit message to channel (framework provides)"""
        ...

    def start(self):
        """Start producing messages (user implements)"""
        raise NotImplementedError

    def stop(self):
        """Stop and cleanup (user implements)"""
        pass

class Destination:
    """Base class for message destinations"""
    def __init__(self, channel: str, filter: dict = None):
        self.channel = channel
        self.filter = filter

    def process(self, message: Message):
        """Process message (user implements)"""
        raise NotImplementedError

class StatefulTransform:
    """Base class for transformations"""
    input_channels: List[str]
    output_channel: str

    # Framework-provided state helpers
    latest: Dict[str, Message]  # Latest message per input channel

    def transform(self, message: Message) -> List[Message]:
        """Transform message (user implements)"""
        raise NotImplementedError
```

**User Implementation:**
```python
# Custom source
class My3DPrinterSource(Source):
    """Read from 3D printer serial port"""

    def __init__(self, channel, port, baudrate=115200):
        super().__init__(channel)
        self.port = port
        self.baudrate = baudrate
        self.serial = None

    def start(self):
        import serial
        self.serial = serial.Serial(self.port, self.baudrate)

        while self.running:
            line = self.serial.readline().decode('utf-8')
            message = self.parse_gcode(line)
            if message:
                self.emit(message)

    def stop(self):
        if self.serial:
            self.serial.close()

    def parse_gcode(self, line):
        # Custom parsing logic
        if line.startswith('T:'):
            temp = float(line.split(':')[1])
            return Message(
                key="temp",
                timestamp=datetime.now(timezone.utc),
                value=temp,
                tags={"source": "printer", "port": self.port}
            )
        return None

# Custom transformation
class ViscosityComputer(StatefulTransform):
    """Compute viscosity from temp, speed, force"""

    input_channels = ["sensors.temp", "sensors.speed", "sensors.force"]
    output_channel = "indicators.viscosity"

    def transform(self, message: Message) -> List[Message]:
        # Wait for all inputs
        if len(self.latest) < 3:
            return []

        # Compute viscosity
        temp = self.latest["sensors.temp"].value
        speed = self.latest["sensors.speed"].value
        force = self.latest["sensors.force"].value

        viscosity = self.compute_viscosity(temp, speed, force)

        return [Message(
            key="viscosity",
            timestamp=message.timestamp,
            value=viscosity,
            tags={
                "temp": temp,
                "speed": speed,
                "force": force
            }
        )]

    def compute_viscosity(self, temp, speed, force):
        # Your domain-specific formula
        return (force * temp) / (speed + 1e-6)

# Custom destination
class MyDatabaseWriter(Destination):
    """Write to custom database"""

    def __init__(self, channel, connection_string):
        super().__init__(channel)
        self.connection_string = connection_string
        self.db = None

    def start(self):
        self.db = MyDatabase.connect(self.connection_string)

    def process(self, message: Message):
        self.db.insert({
            "timestamp": message.timestamp,
            "key": message.key,
            "value": message.value,
            "tags": message.tags
        })

    def stop(self):
        if self.db:
            self.db.close()

# Use custom components
broker = Broker()
broker.register(My3DPrinterSource(channel="printer.raw", port="/dev/ttyUSB0"))
broker.register(ViscosityComputer())
broker.register(MyDatabaseWriter(channel="indicators.**", connection_string="..."))
broker.start()
```

**Configuration-Based (Secondary):**

**YAML Configuration:**
```yaml
# config.yaml
broker:
  mode: local
  log_level: INFO

sources:
  # Built-in CSV source
  - type: csv_file
    channel: sensors.temp
    config:
      file_path: historical_data.csv
      timestamp_column: timestamp
      value_column: temperature
      mode: REALTIME

  # Built-in synthetic source
  - type: synthetic
    channel: sensors.speed
    config:
      pattern: sine
      base_value: 50
      amplitude: 10
      rate: 10

transformations:
  # Built-in threshold alert
  - type: threshold_alert
    input_channel: sensors.temp
    output_channel: alerts.high_temp
    config:
      threshold: 250
      comparison: ">"
      emit_original: true

  # Built-in filter
  - type: filter
    input_channel: sensors.temp
    output_channel: sensors.temp.valid
    config:
      min_value: -50
      max_value: 400

destinations:
  # Built-in console
  - type: console
    channel: "**"
    config:
      format: json

  # Built-in file writer
  - type: file_writer
    channel: indicators.viscosity
    config:
      file_path: /data/viscosity.csv
      format: csv
      mode: append
```

**Mixed Approach (Code + Config):**
```python
# Load built-in components from config
broker = Broker()
broker.load_config("config.yaml")

# Add custom components programmatically
broker.register(My3DPrinterSource(channel="printer.raw", port="/dev/ttyUSB0"))
broker.register(ViscosityComputer())
broker.register(MyDatabaseWriter(channel="indicators.**", connection_string="..."))

# Start
broker.start()
```

**Benefits:**

**Interface-Based:**
- Full control (any Python code)
- Type safe (IDE autocomplete, type checking)
- Testable (unit tests for components)
- Powerful (access all framework APIs)

**Configuration-Based:**
- Simple for built-ins (no code needed)
- Declarative (what, not how)
- Version control (config files)
- Hot-reload potential (change config without code changes)

**Component Registry:**
```python
# Framework maintains registry of built-in types
COMPONENT_REGISTRY = {
    "sources": {
        "csv_file": CSVSource,
        "synthetic": SyntheticSource,
        "timer": TimerSource,
        # ...
    },
    "destinations": {
        "console": ConsoleDestination,
        "file_writer": FileDestination,
        "buffer": BufferDestination,
        # ...
    },
    "transformations": {
        "threshold_alert": ThresholdAlertTransform,
        "filter": FilterTransform,
        "deduplication": DeduplicationTransform,
        # ...
    }
}

# Users can register custom types
broker.register_component_type("sources", "my_printer", My3DPrinterSource)
```

**Documentation Pattern:**
```python
# Each base class has clear documentation
class Source:
    """
    Base class for message sources.

    To create a custom source:
    1. Inherit from Source
    2. Implement start() method
    3. Call self.emit(message) to send messages
    4. Implement stop() for cleanup

    Example:
        class MySource(Source):
            def start(self):
                while self.running:
                    message = self.read_data()
                    self.emit(message)
    """
```

**Deferred to v2.0:**
- Plugin discovery (entry points, auto-loading from directories)
- Hot reload (update components without restart)
- Scripting support (embedded Python/Lua for simple transformations)
- Plugin marketplace/registry (distribute via pip)
- Sandboxing (restrict plugin capabilities)

---

#### **Q8.2: Multi-Language Support**
**Question:** Should the framework support components in languages other than Python?

**Decision:** **Option D - Python only for v1.0, protocol support in v2.0 if needed**
- **v1.0:** Python only (custom components must be Python classes)
- **v2.0:** Add gRPC/REST protocol for multi-language support (if requested by users)
- **Rationale:** Simplicity for initial development, focus on core functionality, add multi-language when requirements clear

**v1.0 Language Support:**

**Implementation Language:**
- Python 3.9+ (framework core)
- Type hints throughout (IDE support, type checking)

**Custom Components:**
```python
# All custom components in Python
from cod3s import Source, Destination, StatefulTransform

class MyCustomSource(Source):
    """Python class implementing Source interface"""
    ...

class MyCustomDestination(Destination):
    """Python class implementing Destination interface"""
    ...

class MyCustomTransform(StatefulTransform):
    """Python class implementing Transform interface"""
    ...
```

**Benefits:**
- **Simplicity:** No cross-language complexity, no IPC overhead
- **Performance:** In-process, no serialization overhead
- **Debugging:** Single language stack, easier to debug
- **Type Safety:** Python type hints, IDE autocomplete
- **Rich Ecosystem:** Python has excellent libraries for IoT, data processing, ML

**Workaround for External Programs (v1.0):**

If needed, can wrap external programs via subprocess:

```python
class ExternalProcessSource(Source):
    """Wrapper for external program that outputs JSON"""

    def __init__(self, channel, command):
        super().__init__(channel)
        self.command = command

    def start(self):
        import subprocess
        import json

        # Start external program
        proc = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            text=True
        )

        # Read JSON lines from stdout
        for line in proc.stdout:
            data = json.loads(line)
            self.emit(Message(**data))

# Use external Go/Rust/C++ program
source = ExternalProcessSource(
    channel="sensors.external",
    command=["./my-program", "--config", "config.json"]
)
```

**v2.0 Multi-Language Roadmap (If Requested):**

**Option 1: gRPC Protocol**
```protobuf
// cod3s.proto
service SourceService {
    rpc StreamMessages(SourceConfig) returns (stream Message);
}

service DestinationService {
    rpc ProcessMessage(Message) returns (Ack);
}

service TransformService {
    rpc Transform(Message) returns (stream Message);
}
```

**Option 2: REST API**
```
POST /api/v1/sources/{source_id}/messages
GET  /api/v1/channels/{channel}/subscribe
POST /api/v1/transformations/{transform_id}/process
```

**Option 3: Language SDKs**
- Python (reference implementation)
- Java SDK
- Go SDK
- JavaScript/TypeScript SDK
- Rust SDK

**When to Add Multi-Language:**
- User requests for specific language
- Need to integrate existing non-Python code
- Performance-critical components need compiled language
- Community contributions in other languages

**Documentation:**
```
LANGUAGE SUPPORT

v1.0: Python Only
  - All custom components must be Python classes
  - Implements Source, Destination, or StatefulTransform interfaces
  - Python 3.9+ required
  - External programs can be wrapped via subprocess (JSON output)

Future (v2.0): Multi-Language Support
  - Will add if users request specific languages
  - Likely via gRPC protocol (language-agnostic)
  - SDKs for popular languages (Java, Go, JavaScript, Rust)
  - Backward compatible with v1.0 Python components

Rationale:
  - Start simple: Get core functionality solid in single language
  - Learn requirements: Understand what languages users actually need
  - Add when needed: Don't prematurely add complexity
```

---

### Theme 9: Batch Processing Modes - Clarifications

#### **Q9.1: TRANSPOSE Mode Semantics**
**Question:** Lorsque des données historiques sont rejouées en mode TRANSPOSE, comment les timestamps doivent-ils être recalculés ?

**Decision:** **Option A - Décalage Temporel Relatif** ✅

**Principe:**
Le mode TRANSPOSE émet **tous les messages immédiatement** (pas de délai de replay comme REALTIME), mais **recalcule les timestamps** en préservant les intervalles temporels relatifs.

**Comportement:**
- Le **premier message** reçoit le timestamp "maintenant" (au moment du début du replay)
- Les **messages suivants** préservent leurs **écarts relatifs** par rapport au premier
- La **durée totale** de la séquence est préservée (1 heure de données = span de 1 heure dans le futur)

**Exemple Concret:**

```python
# DONNÉES ORIGINALES (enregistrées le 15 janvier 2024 à 10h)
messages_originaux = [
    Message(timestamp="2024-01-15 10:00:00", key="temp", value=25),  # t0
    Message(timestamp="2024-01-15 10:30:00", key="temp", value=30),  # t0 + 30min
    Message(timestamp="2024-01-15 11:00:00", key="temp", value=35)   # t0 + 1h
]
# Durée totale: 1 heure

# REPLAY EN MODE TRANSPOSE (le 20 janvier 2024 à 14h00)
# ✅ Tous émis IMMÉDIATEMENT (pas d'attente)
# ✅ Mais timestamps RECALCULÉS

messages_transpose = [
    Message(timestamp="2024-01-20 14:00:00", key="temp", value=25),  # now
    Message(timestamp="2024-01-20 14:30:00", key="temp", value=30),  # now + 30min
    Message(timestamp="2024-01-20 15:00:00", key="temp", value=35)   # now + 1h
]
# ✅ Émission: Immédiate (< 1 seconde pour tout émettre)
# ✅ Timestamps: Décalés de 5 jours, mais écarts préservés
# ✅ Durée totale: Toujours 1 heure (dans les timestamps)
```

**Comparaison des 3 modes:**

| Mode | Émission | Timestamps |
|------|----------|------------|
| **BATCH** | Immédiate | Originaux (2024-01-15 10:00-11:00) |
| **REALTIME** | Avec délais (1h pour rejouer) | Originaux (2024-01-15 10:00-11:00) |
| **TRANSPOSE** | Immédiate | Recalculés (2024-01-20 14:00-15:00) |

**Use Case - Calcul de Viscosité:**

Pour le calcul de viscosité qui combine température + vitesse + force sur plusieurs channels :

```python
# Données originales avec écarts entre capteurs
temp_data = [
    Message(timestamp="2024-01-15 10:00:00", value=25),
    Message(timestamp="2024-01-15 10:30:00", value=30),
]
speed_data = [
    Message(timestamp="2024-01-15 10:05:00", value=100),  # +5min après temp
    Message(timestamp="2024-01-15 10:35:00", value=120),
]
force_data = [
    Message(timestamp="2024-01-15 10:10:00", value=50),   # +10min après temp
    Message(timestamp="2024-01-15 10:40:00", value=60),
]

# Mode TRANSPOSE replay à 14:00
# ✅ Les écarts de 5min et 10min sont PRÉSERVÉS
temp_replay   -> 14:00:00, 14:30:00
speed_replay  -> 14:05:00, 14:35:00  # Toujours +5min après temp
force_replay  -> 14:10:00, 14:40:00  # Toujours +10min après temp

# 🎯 Le calcul de viscosité voit les MÊMES patterns temporels
# = Analyse fidèle même sur données historiques
```

**Rationale:**
- **"Rejouer à l'identique"**: Préserve la structure temporelle originale
- **Transformation stateful**: Les transformations multi-channel voient les mêmes corrélations temporelles
- **Analyse temporelle**: Les calculs basés sur les écarts de temps restent valides
- **Performance**: Émission rapide (important pour gros volumes)
- **Timestamps cohérents**: Les timestamps reflètent "quand aurait eu lieu ce scénario s'il se passait maintenant"

**Alternatives Rejetées:**
- **Option B (Tout à "maintenant")**: Perd toute information temporelle, impossible de distinguer l'ordre
- **Option C (Facteur de compression)**: Plus complexe, cas d'usage peu clair pour v1.0

**Implementation Hint:**
```python
def transpose_replay(messages: List[Message], start_time: datetime = None):
    """Replay messages in TRANSPOSE mode"""
    if not messages:
        return

    # Calculer le décalage temporel
    start_time = start_time or datetime.now(timezone.utc)
    original_start = messages[0].timestamp
    time_offset = start_time - original_start

    # Émettre tous les messages immédiatement
    # avec timestamps décalés
    for msg in messages:
        new_msg = Message(
            key=msg.key,
            timestamp=msg.timestamp + time_offset,  # Décalage
            value=msg.value,
            tags=msg.tags,
            id=msg.id
        )
        broker.publish(channel, new_msg)
```

---

#### **Q9.2: Gestion de la Dérive d'Horloge en Mode REALTIME**
**Question:** Le mode REALTIME rejoue les messages en préservant les délais temporels originaux. Comment gérer la dérive d'horloge et garantir la précision du timing ?

**Decision:** **Option B - Horloge monotone avec resynchronisation automatique** ✅

**Principe:**
Utiliser `time.monotonic()` (horloge monotone insensible aux ajustements système) et calculer le délai **absolu depuis le début du replay** pour chaque message, ce qui évite l'accumulation de drift.

**Comportement:**
- Calculer le timestamp cible absolu pour chaque message (basé sur le début du replay)
- Attendre jusqu'au moment exact avant d'émettre
- Pas de correction manuelle nécessaire : se resynchronise automatiquement à chaque message
- Précision suffisante pour la plupart des cas d'usage (drift < 1ms par heure)

**Implémentation:**

```python
import time
from datetime import timezone

class RealtimeReplayer:
    """Replay messages in REALTIME mode with monotonic clock"""

    def __init__(self, channel: str, messages: List[Message]):
        self.channel = channel
        self.messages = messages

    def replay(self):
        """Replay with automatic drift correction"""
        if not self.messages:
            return

        # Point de départ (horloge monotone)
        start_real = time.monotonic()
        start_original = self.messages[0].timestamp

        # Émettre le premier message immédiatement
        broker.publish(self.channel, self.messages[0])

        # Émettre les suivants avec timing précis
        for msg in self.messages[1:]:
            # Calculer QUAND ce message devrait être émis
            elapsed_original = (msg.timestamp - start_original).total_seconds()
            target_time = start_real + elapsed_original

            # Attendre jusqu'au moment exact
            now = time.monotonic()
            delay = target_time - now

            if delay > 0:
                time.sleep(delay)
            # Si delay < 0, on est en retard → émettre immédiatement

            broker.publish(self.channel, msg)

# Utilisation
replayer = RealtimeReplayer(
    channel="sensors.temp",
    messages=load_batch_data("temp_20240115.jsonl")
)
replayer.replay()  # Rejoue avec timing précis
```

**Exemple Concret:**

```python
# Données originales: 3 messages sur 1 heure
messages = [
    Message(timestamp="2024-01-15 10:00:00", value=25),
    Message(timestamp="2024-01-15 10:30:00", value=30),  # +30 min
    Message(timestamp="2024-01-15 11:00:00", value=35)   # +1 heure
]

# Replay à 14:00:00 le 20 janvier
# start_real = 1000.0 (monotonic)
# start_original = 2024-01-15 10:00:00

# Message 1:
# - elapsed = 0s
# - target = 1000.0
# - delay = 0s → Émet immédiatement à 14:00:00

# Message 2:
# - elapsed = 1800s (30 min)
# - target = 2800.0
# - now = 1000.1 (juste après msg 1)
# - delay = 1799.9s → sleep(1799.9) → Émet à ~14:30:00

# Message 3:
# - elapsed = 3600s (1h)
# - target = 4600.0
# - now = 2800.1 (juste après msg 2)
# - delay = 1799.9s → sleep(1799.9) → Émet à ~15:00:00

# ✅ Même si sleep(1799.9) prend 1800.2s en réalité
#    Le message 3 se resynchronise automatiquement
#    car le délai est recalculé depuis start_real
```

**Gestion des Retards:**

```python
# Si le système est surchargé et ne peut pas tenir le timing
if delay < 0:
    # On est en retard
    warnings.warn(
        f"REALTIME replay running behind schedule: "
        f"{-delay:.2f}s late at message {msg.id}"
    )
    # Émettre quand même (pas de catch-up, continuer au rythme possible)
    broker.publish(self.channel, msg)

# Possibilité d'exposer une métrique
broker.publish(
    "_metrics.batch.realtime",
    Message(
        key="timing_drift",
        value=delay,  # Négatif si en retard
        tags={"channel": self.channel}
    )
)
```

**Comparaison des Approches:**

| Approche | Précision | Complexité | Pausable | Use Case |
|----------|-----------|------------|----------|----------|
| **Simple sleep()** | ±10-60s/heure | Très simple | Non | Tests rapides |
| **Monotonic + resync (B)** ✅ | ±1ms/heure | Simple | Non | Production standard |
| **High-precision + pause** | ±1µs/heure | Complexe | Oui | Debugging interactif |

**Rationale:**
- **Précision suffisante**: ±1ms/heure largement suffisant pour IoT/monitoring
- **Simplicité**: Code simple, pas de state management complexe
- **Robustesse**: Insensible aux ajustements d'horloge système (NTP, DST, etc.)
- **Performance**: Overhead négligeable vs sleep() simple
- **v1.0 suffisant**: La pausabilité (Option C) peut être ajoutée en v2.0 si besoin

**Alternative Rejetée:**
- **Option A (Simple sleep)**: Accumule le drift, imprécis pour replays longs (>1h)
- **Option C (High-precision pausable)**: Sur-ingénierie pour v1.0, complexité non justifiée
- **Option D (Configurable)**: Ajoute de la complexité de configuration sans bénéfice clair

**Note pour v2.0:**
Si le besoin apparaît, ajouter support pause/resume :
```python
replayer.pause()   # Suspend le replay
replayer.resume()  # Continue sans skip (compense le temps de pause)
replayer.cancel()  # Arrête complètement
```

---

### Theme 10: Edge Cases & Ambiguity Resolution

#### **Q10.1: Comportement des Canaux Vides**
**Question:** Comment le framework doit-il gérer les canaux qui n'ont jamais reçu de messages ? Création implicite à la première utilisation ou pré-déclaration obligatoire ?

**Decision:** **Option A - Création Implicite / Lazy** ✅

**Principe:**
Les canaux sont créés **automatiquement** à la première utilisation, sans nécessité de pré-déclaration. Un canal existe dès qu'une source y émet ou qu'une destination y souscrit.

**Comportement:**
- **Pas de déclaration explicite requise**
- Canal créé à la première utilisation (source émettant OU destination souscrivant)
- Aucune erreur si un canal est vide (pas de messages)
- Support naturel des canaux dynamiques et des wildcards
- Mode strict optionnel pour validation en production

**Implémentation:**

```python
class Broker:
    def __init__(self, strict_mode: bool = False):
        self.channels = {}  # {channel_name: Channel}
        self.strict_mode = strict_mode
        self.on_new_channel = None  # Optional callback

    def _ensure_channel(self, channel_name: str) -> Channel:
        """Create channel lazily if it doesn't exist"""
        if channel_name not in self.channels:
            # Création automatique
            self.channels[channel_name] = Channel(channel_name)

            # En mode strict, notifier
            if self.strict_mode and self.on_new_channel:
                self.on_new_channel(channel_name)

            # Ou logger
            if self.strict_mode:
                warnings.warn(
                    f"New channel created: '{channel_name}'",
                    category=RuntimeWarning
                )

        return self.channels[channel_name]

    def publish(self, channel_name: str, message: Message):
        """Publish to a channel (creates it if needed)"""
        channel = self._ensure_channel(channel_name)
        channel.publish(message)

    def subscribe(self, channel_pattern: str, destination: Destination):
        """Subscribe to a channel pattern (creates channels if needed)"""
        # Pour wildcards, ne crée pas à la souscription
        # Crée seulement quand un message est publié
        if '*' in channel_pattern:
            # Enregistre le pattern pour matching futur
            self._register_pattern(channel_pattern, destination)
        else:
            # Canal spécifique: peut créer immédiatement
            channel = self._ensure_channel(channel_pattern)
            channel.add_subscriber(destination)
```

**Exemple Concret:**

```python
# 🚀 Utilisation simple - Pas de setup requis

# Source émet sur un canal → canal créé automatiquement
mqtt_source = MQTTSource(
    channel="sensors.temp",
    broker_url="mqtt://localhost"
)
# ✅ Canal "sensors.temp" créé automatiquement

# Destination souscrit → canal créé si nécessaire
console = ConsoleDestination(channel="sensors.temp")
# ✅ Si le canal n'existait pas, il est créé maintenant

# Wildcards fonctionnent naturellement
file_dest = FileDestination(
    channel="sensors.**",  # Tous les sous-canaux
    file_path="all_sensors.jsonl"
)
# ✅ Pattern enregistré, canaux créés quand messages arrivent
```

**Cas d'Usage - Imprimantes 3D Dynamiques:**

```python
# Monitoring de N imprimantes 3D
# Chaque imprimante crée ses propres canaux à la volée

class PrinterMonitor(Source):
    def __init__(self, printer_id: str):
        self.printer_id = printer_id
        super().__init__(f"printers.{printer_id}.status")

    def start(self):
        while self.running:
            # Émet sur plusieurs canaux (créés automatiquement)
            broker.publish(
                f"printers.{self.printer_id}.temp",
                Message(key="temp", value=self.read_temp())
            )
            broker.publish(
                f"printers.{self.printer_id}.speed",
                Message(key="speed", value=self.read_speed())
            )
            broker.publish(
                f"printers.{self.printer_id}.force",
                Message(key="force", value=self.read_force())
            )
            time.sleep(1)

# ✅ Démarrer 10 imprimantes - 30 canaux créés automatiquement
printers = [PrinterMonitor(f"P{i}") for i in range(10)]
for p in printers:
    p.start()

# ✅ Souscrire à tout avec wildcard
all_temps = ConsoleDestination(channel="printers.**.temp")
# → Reçoit température de toutes les imprimantes
```

**Mode Strict (Optionnel pour Production):**

```python
# En production, activer le mode strict pour validation
broker = Broker(strict_mode=True)

# Callback personnalisé pour nouveaux canaux
def on_new_channel(channel_name: str):
    logger.warning(f"Unexpected channel created: {channel_name}")
    # Publier métrique
    broker.publish(
        "_metrics.broker.channels",
        Message(
            key="new_channel_created",
            value=channel_name,
            tags={"severity": "warning"}
        )
    )

broker.on_new_channel = on_new_channel

# Canal inattendu → warning mais continue de fonctionner
source = RandomSource(channel="sensors.unexpected")
# ⚠️ Warning logged: "Unexpected channel created: sensors.unexpected"
# ✅ Mais fonctionne quand même (pas d'erreur)
```

**Avantages:**

1. **Simplicité**: Pas de boilerplate, pas de configuration préalable
2. **Flexibilité**: Support naturel des canaux dynamiques
3. **Wildcards**: Fonctionne parfaitement avec `*` et `**`
4. **Développement Rapide**: Test/prototypage sans friction
5. **Production-Ready**: Mode strict optionnel pour monitoring

**Gestion Mémoire:**

```python
# Les canaux vides (sans subscribers ni messages) peuvent être nettoyés
class Broker:
    def cleanup_empty_channels(self):
        """Remove channels with no subscribers and no recent activity"""
        to_remove = []
        for name, channel in self.channels.items():
            if (len(channel.subscribers) == 0 and
                channel.last_message_time is None):
                to_remove.append(name)

        for name in to_remove:
            del self.channels[name]
            logger.debug(f"Cleaned up empty channel: {name}")

# Cleanup périodique (optionnel)
scheduler.every(1).hour.do(broker.cleanup_empty_channels)
```

**Introspection:**

```python
# Liste des canaux existants
broker.list_channels()
# → ["sensors.temp", "sensors.speed", "printers.P0.temp", ...]

# Vérifier si un canal existe
broker.has_channel("sensors.temp")  # True
broker.has_channel("sensors.xyz")   # False

# Statistiques par canal
broker.get_channel_stats("sensors.temp")
# → {
#     "message_count": 1234,
#     "subscriber_count": 3,
#     "last_message_time": "2024-01-24T14:30:00Z"
#   }
```

**Rationale:**
- **Cohérent avec la philosophie**: Framework simple et flexible
- **Support dynamique**: Essentiel pour IoT avec devices variables
- **Wildcards**: Nécessite création lazy pour fonctionner
- **Production**: Mode strict donne visibilité sans bloquer
- **Convention over Configuration**: Fonctionne sans setup

**Alternatives Rejetées:**
- **Option B (Pré-déclaration obligatoire)**: Trop verbeux, incompatible avec wildcards dynamiques
- **Option C (Pré-déclaration optionnelle)**: Complexité non justifiée pour v1.0
- **Option D (Hybrid)**: Asymétrie confusante pour les utilisateurs

---

#### **Q10.2: Dépendances Circulaires**
**Question:** Le framework doit-il détecter et empêcher les dépendances circulaires entre transformations ? Ou les autoriser avec des garde-fous ?

**Decision:** **Option A - Interdire Complètement (v1.0)** ✅

**Principe:**
Détecter les cycles dans le graphe de flux de données au moment de la **configuration** et **lever une erreur** si un cycle est trouvé. Aucune boucle autorisée en v1.0.

**Comportement:**
- Analyse du graphe de flux au démarrage (ou à chaque ajout de transformation)
- Détection des cycles directs et indirects
- **Erreur immédiate** si cycle détecté (empêche le démarrage)
- Message d'erreur clair indiquant le cycle trouvé

**Rationale:**
- **Simplicité v1.0**: Commencer avec la solution la plus sûre
- **Éviter les bugs**: Prévient les boucles infinies accidentelles
- **Cas d'usage actuels**: Aucun besoin identifié pour des cycles légitimes
- **Évolutif**: Peut être assoupli en v2.0 si besoin (feedback loops, control systems)

**Implémentation:**

```python
class Broker:
    def __init__(self):
        self.transformations = []
        self.dataflow_graph = {}  # {channel: [channels]}

    def add_transformation(self, transformation):
        """Add transformation and check for cycles"""
        # Mettre à jour le graphe
        input_channels = (
            transformation.input_channels
            if hasattr(transformation, 'input_channels')
            else [transformation.input_channel]
        )
        output_channel = transformation.output_channel

        # Ajouter les arêtes au graphe
        for input_ch in input_channels:
            if input_ch not in self.dataflow_graph:
                self.dataflow_graph[input_ch] = []
            self.dataflow_graph[input_ch].append(output_channel)

        # Détecter les cycles
        cycle = self._detect_cycle()
        if cycle:
            # Annuler l'ajout
            for input_ch in input_channels:
                self.dataflow_graph[input_ch].remove(output_channel)

            # Lever une erreur explicite
            raise ValueError(
                f"Circular dependency detected: {' -> '.join(cycle)}\n"
                f"Transformation rejected: {transformation}\n"
                f"COD3S does not allow circular dependencies in v1.0.\n"
                f"Please restructure your dataflow to avoid cycles."
            )

        # Pas de cycle, ajouter la transformation
        self.transformations.append(transformation)

    def _detect_cycle(self) -> Optional[List[str]]:
        """Detect cycles using DFS (Depth-First Search)"""
        visited = set()
        rec_stack = set()

        def dfs(node, path):
            if node in rec_stack:
                # Cycle détecté, retourner le chemin
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]

            if node in visited:
                return None

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            # Explorer les voisins
            for neighbor in self.dataflow_graph.get(node, []):
                cycle = dfs(neighbor, path[:])
                if cycle:
                    return cycle

            rec_stack.remove(node)
            return None

        # Tester depuis chaque nœud
        for node in self.dataflow_graph:
            cycle = dfs(node, [])
            if cycle:
                return cycle

        return None
```

**Exemples:**

**Cas 1 - Cycle Direct (Self-Loop):**
```python
# ❌ Erreur: Cycle détecté
MapTransform(
    input_channel="data.process",
    output_channel="data.process",  # Retour vers soi-même
    map_fn=lambda msg: Message(key="loop", value=msg.value + 1)
)

# Résultat:
# ValueError: Circular dependency detected: data.process -> data.process
# Transformation rejected: MapTransform(data.process -> data.process)
# COD3S does not allow circular dependencies in v1.0.
# Please restructure your dataflow to avoid cycles.
```

**Cas 2 - Cycle Indirect (A → B → C → A):**
```python
# Transformation 1: sensors.raw → stage1
FilterTransform(
    input_channel="sensors.raw",
    output_channel="stage1",
    filter_fn=lambda msg: msg.value > 0
)

# Transformation 2: stage1 → stage2
MapTransform(
    input_channel="stage1",
    output_channel="stage2",
    map_fn=lambda msg: Message(key=msg.key, value=msg.value * 2)
)

# Transformation 3: stage2 → sensors.raw (cycle!)
# ❌ Erreur
MapTransform(
    input_channel="stage2",
    output_channel="sensors.raw",  # Retour vers l'origine
    map_fn=lambda msg: Message(key=msg.key, value=msg.value + 1)
)

# Résultat:
# ValueError: Circular dependency detected: sensors.raw -> stage1 -> stage2 -> sensors.raw
```

**Cas 3 - Graphe Valide (Pas de Cycle):**
```python
# ✅ Pas de cycle, OK
# sensors.temp → processed.temp → alerts
#             ↘ metrics

FilterTransform(
    input_channel="sensors.temp",
    output_channel="processed.temp",
    filter_fn=lambda msg: msg.value > 20
)

ThresholdTransform(
    input_channel="processed.temp",
    output_channel="alerts",
    threshold=50
)

MetricsTransform(
    input_channel="sensors.temp",  # Même source, pas de cycle
    output_channel="metrics"
)

# ✅ Aucun cycle, démarrage réussi
broker.start()
```

**Visualisation du Graphe (Debug):**

```python
# Helper pour visualiser le dataflow
def visualize_dataflow(broker):
    """Print the dataflow graph for debugging"""
    print("Dataflow Graph:")
    for source, destinations in broker.dataflow_graph.items():
        for dest in destinations:
            print(f"  {source} → {dest}")

# Exemple:
# Dataflow Graph:
#   sensors.temp → processed.temp
#   processed.temp → alerts
#   sensors.temp → metrics
```

**Migration Path pour v2.0 (Si Besoin):**

Si des cas d'usage légitimes apparaissent (control loops, feedback systems), v2.0 pourra ajouter:

```python
# v2.0: Support optionnel des cycles avec protection
class Broker:
    def __init__(self, allow_cycles: bool = False, max_depth: int = 10):
        self.allow_cycles = allow_cycles
        self.max_depth = max_depth

# Ou marquage explicite des cycles autorisés
@allow_cycle
class PIDControllerTransform(StatefulTransform):
    input_channels = ["sensors.temp", "setpoint.temp"]
    output_channel = "actuator.heater"  # Peut créer un cycle
```

**Alternatives Rejetées (pour v1.0):**
- **Option B (Autoriser sans restriction)**: Trop risqué, peut causer des freezes
- **Option C (Limite de profondeur)**: Complexité non justifiée sans cas d'usage
- **Option D (Warning seulement)**: Insuffisant, l'erreur devrait être bloquante
- **Option E (Mode configurable)**: Sur-ingénierie pour v1.0

**Note:** Cette décision peut être reconsidérée en v2.0 si des besoins de feedback loops ou control systems émergent.

---

#### **Q10.3: Limites sur les Messages Volumineux**
**Question:** Le framework doit-il imposer des limites sur la taille des messages (valeur, nombre de tags, profondeur de nesting) ? Si oui, quelles limites ?

**Decision:** **Option B - Limites Raisonnables avec Configuration** ✅

**Principe:**
Imposer des **limites par défaut raisonnables** pour prévenir les problèmes de mémoire et de performance, tout en permettant de les **configurer** au niveau du Broker si besoin.

**Limites par Défaut:**
- **Taille de la valeur**: 1 MB (1 048 576 bytes)
- **Nombre de tags**: 100 tags maximum
- **Longueur clé de tag**: 256 caractères
- **Longueur valeur de tag**: 1 KB (1024 caractères)
- **Profondeur JSON**: 10 niveaux d'imbrication

**Rationale:**
- **Protection OOM**: Empêche les messages géants de saturer la mémoire
- **Performance**: Limite le coût de sérialisation/désérialisation
- **IoT/Monitoring**: Les limites par défaut couvrent 99% des cas d'usage
- **Flexibilité**: Configurable pour les cas particuliers

**Comportement:**
- Messages dépassant les limites → **rejetés**
- Warning loggé avec détails du dépassement
- Message routé vers **DLQ** (`_dlq.oversized`)
- Métrique publiée sur `_metrics.broker.rejected`

**Implémentation:**

```python
class Broker:
    """Message broker with configurable size limits"""

    # Limites par défaut (IoT/Monitoring friendly)
    DEFAULT_MAX_VALUE_SIZE = 1 * 1024 * 1024      # 1 MB
    DEFAULT_MAX_TAGS_COUNT = 100                  # 100 tags
    DEFAULT_MAX_TAG_KEY_LENGTH = 256              # 256 chars
    DEFAULT_MAX_TAG_VALUE_LENGTH = 1024           # 1 KB
    DEFAULT_MAX_JSON_DEPTH = 10                   # 10 niveaux

    def __init__(self,
                 max_value_size: int = None,
                 max_tags_count: int = None,
                 max_tag_key_length: int = None,
                 max_tag_value_length: int = None,
                 max_json_depth: int = None):
        """
        Initialize broker with size limits.

        Args:
            max_value_size: Maximum value size in bytes (default 1MB)
            max_tags_count: Maximum number of tags (default 100)
            max_tag_key_length: Maximum tag key length (default 256)
            max_tag_value_length: Maximum tag value length (default 1KB)
            max_json_depth: Maximum JSON nesting depth (default 10)
        """
        self.max_value_size = max_value_size or self.DEFAULT_MAX_VALUE_SIZE
        self.max_tags_count = max_tags_count or self.DEFAULT_MAX_TAGS_COUNT
        self.max_tag_key_length = (max_tag_key_length or
                                   self.DEFAULT_MAX_TAG_KEY_LENGTH)
        self.max_tag_value_length = (max_tag_value_length or
                                     self.DEFAULT_MAX_TAG_VALUE_LENGTH)
        self.max_json_depth = max_json_depth or self.DEFAULT_MAX_JSON_DEPTH

    def publish(self, channel: str, message: Message):
        """Publish message with size validation"""
        # Valider la taille
        validation_error = self._validate_message_size(message)

        if validation_error:
            # Rejeter le message
            warnings.warn(
                f"Message rejected on channel '{channel}': {validation_error}\n"
                f"Message ID: {message.id}"
            )

            # Router vers DLQ
            self._publish_to_dlq(channel, message, validation_error)

            # Publier métrique
            self.publish(
                "_metrics.broker.rejected",
                Message(
                    key="message_rejected",
                    timestamp=datetime.now(timezone.utc),
                    value=1,
                    tags={
                        "channel": channel,
                        "reason": "oversized",
                        "error": validation_error
                    }
                )
            )
            return

        # Message OK, publier normalement
        self._do_publish(channel, message)

    def _validate_message_size(self, message: Message) -> Optional[str]:
        """
        Validate message against size limits.

        Returns:
            Error message if validation fails, None if OK
        """
        # 1. Vérifier la taille de la valeur
        value_size = self._estimate_size(message.value)
        if value_size > self.max_value_size:
            return (f"Value too large: {value_size:,} bytes "
                    f"(max {self.max_value_size:,} bytes)")

        # 2. Vérifier le nombre de tags
        if len(message.tags) > self.max_tags_count:
            return (f"Too many tags: {len(message.tags)} "
                    f"(max {self.max_tags_count})")

        # 3. Vérifier les tags individuels
        for key, value in message.tags.items():
            if len(key) > self.max_tag_key_length:
                return (f"Tag key too long: '{key[:50]}...' "
                        f"({len(key)} chars, max {self.max_tag_key_length})")

            value_str = str(value)
            if len(value_str) > self.max_tag_value_length:
                return (f"Tag value too long for key '{key}': "
                        f"{len(value_str)} chars "
                        f"(max {self.max_tag_value_length})")

        # 4. Vérifier la profondeur JSON si valeur est dict/list
        if isinstance(message.value, (dict, list)):
            depth = self._json_depth(message.value)
            if depth > self.max_json_depth:
                return (f"JSON too deeply nested: {depth} levels "
                        f"(max {self.max_json_depth})")

        return None  # Validation OK

    def _estimate_size(self, obj) -> int:
        """Estimate object size in bytes"""
        import sys
        if isinstance(obj, (str, bytes)):
            return len(obj.encode('utf-8') if isinstance(obj, str) else obj)
        return sys.getsizeof(obj)

    def _json_depth(self, obj, current_depth=0) -> int:
        """Calculate maximum depth of nested dict/list"""
        if not isinstance(obj, (dict, list)):
            return current_depth

        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(self._json_depth(v, current_depth + 1)
                       for v in obj.values())

        if isinstance(obj, list):
            if not obj:
                return current_depth
            return max(self._json_depth(item, current_depth + 1)
                       for item in obj)

        return current_depth

    def _publish_to_dlq(self, original_channel: str, message: Message,
                        error: str):
        """Publish rejected message to Dead Letter Queue"""
        dlq_message = Message(
            key="oversized_message",
            timestamp=message.timestamp,
            value={
                "original_channel": original_channel,
                "original_message_id": message.id,
                "original_key": message.key,
                "error": error,
                "estimated_size_bytes": self._estimate_size(message.value),
                "tags_count": len(message.tags),
                # Ne PAS inclure la valeur originale (trop grosse)
            },
            tags={
                "error_type": "oversized",
                "original_channel": original_channel
            }
        )
        self._do_publish("_dlq.oversized", dlq_message)
```

**Exemples:**

**✅ Messages Normaux (Passent):**
```python
# Capteur température (quelques bytes)
Message(
    key="temp",
    value=25.5,
    tags={"sensor": "T01", "location": "extruder"}
)
# ✅ OK: ~100 bytes

# Configuration JSON (< 1MB, < 10 niveaux)
Message(
    key="printer.config",
    value={
        "id": "P01",
        "settings": {
            "temperature": {
                "nozzle": 220,
                "bed": 60
            },
            "speed": {
                "print": 50,
                "travel": 150
            }
        }
    },
    tags={"type": "config"}
)
# ✅ OK: ~500 bytes, 4 niveaux
```

**❌ Messages Rejetés (Dépassent):**
```python
# Image raw (> 1MB)
Message(
    key="camera.snapshot",
    value=raw_image_5MB,  # 5 MB
    tags={"camera": "CAM01"}
)
# ❌ Rejeté: "Value too large: 5,242,880 bytes (max 1,048,576 bytes)"
# → Routé vers _dlq.oversized

# Trop de tags
Message(
    key="telemetry",
    value="data",
    tags={f"metric_{i}": i for i in range(500)}  # 500 tags
)
# ❌ Rejeté: "Too many tags: 500 (max 100)"

# JSON trop profond
deeply_nested = {"level1": {"level2": {"level3": {...}}}}  # 15 niveaux
Message(key="config", value=deeply_nested)
# ❌ Rejeté: "JSON too deeply nested: 15 levels (max 10)"
```

**Configuration Personnalisée:**

```python
# Cas d'usage spécial nécessitant des messages plus gros
broker = Broker(
    max_value_size=10 * 1024 * 1024,  # 10 MB pour images compressées
    max_tags_count=200,                # Plus de tags pour métadonnées riches
    max_json_depth=20                  # Configurations complexes
)

# Ou ultra-restrictif pour edge devices
broker = Broker(
    max_value_size=10 * 1024,  # 10 KB seulement
    max_tags_count=10,         # Minimal
    max_json_depth=3           # Plat
)
```

**Pattern Recommandé pour Gros Fichiers:**

```python
# ✅ Au lieu d'embarquer les données, utiliser des références
Message(
    key="camera.snapshot",
    value={
        "type": "reference",
        "storage": "s3",
        "bucket": "cod3s-snapshots",
        "path": "2024-01-24/cam01_143000.jpg",
        "size_bytes": 5242880,
        "mime_type": "image/jpeg",
        "checksum": "sha256:abc123def456..."
    },
    tags={
        "camera": "CAM01",
        "timestamp": "2024-01-24T14:30:00Z"
    }
)

# Les consommateurs téléchargent depuis S3 si besoin
class ImageProcessor(Destination):
    def process(self, message: Message):
        if message.value.get("type") == "reference":
            # Télécharger le fichier depuis le storage
            storage = message.value["storage"]
            if storage == "s3":
                image_data = s3_client.download(
                    message.value["bucket"],
                    message.value["path"]
                )
                # Traiter l'image...
                self.process_image(image_data)
```

**Monitoring:**

```python
# Surveiller les rejets
ConsoleDestination(channel="_dlq.oversized")

# Métriques de rejets
MetricsDestination(channel="_metrics.broker.rejected")

# Dashboard
broker.get_stats()
# → {
#     "messages_published": 10000,
#     "messages_rejected": 5,
#     "rejection_reasons": {
#         "oversized_value": 3,
#         "too_many_tags": 1,
#         "json_too_deep": 1
#     }
# }
```

**Documentation pour Utilisateurs:**

```
MESSAGE SIZE LIMITS

Default Limits:
  - Value size: 1 MB
  - Tags count: 100
  - Tag key length: 256 chars
  - Tag value length: 1 KB
  - JSON depth: 10 levels

These limits prevent memory issues and ensure good performance.

For Large Files:
  - Use the "reference" pattern (store in S3/filesystem, reference in message)
  - Configure larger limits if needed (broker = Broker(max_value_size=...))

Messages exceeding limits are:
  - Rejected with clear error message
  - Routed to _dlq.oversized
  - Counted in _metrics.broker.rejected
```

**Alternatives Rejetées:**
- **Option A (Pas de limites)**: Risque OOM et freeze sur messages géants
- **Option C (Limites strictes)**: Trop inflexible, bloque des cas légitimes
- **Option D (Limites par canal)**: Complexité excessive pour v1.0

---

#### **Q10.4: Valeurs Null et Manquantes**
**Question:** Les messages peuvent-ils avoir des valeurs null ou manquantes ? Comment distinguer entre null explicite, chaîne vide, et valeur absente ?

**Decision:** **Option B - Valeur Obligatoire, null Autorisé** ✅

**Principe:**
Le paramètre `value` est **obligatoire** lors de la création d'un message (pas de valeur par défaut), mais **None est une valeur valide** qui représente explicitement "pas de donnée" ou "donnée non disponible".

**Sémantique Claire:**
- **`value=None`**: Valeur null explicite = "pas de donnée disponible"
- **`value=""`**: Chaîne vide légitime (différent de null)
- **`value=0`**: Zéro numérique (différent de null)
- **`value=False`**: Booléen faux (différent de null)
- **`value=[]` ou `value={}`**: Collections vides (différent de null)
- **Paramètre omis**: Erreur (TypeError)

**Rationale:**
- **Flexibilité**: Permet de représenter les capteurs HS, données manquantes
- **Clarté**: None a une sémantique explicite et distincte
- **Sécurité**: Paramètre obligatoire évite les oublis accidentels
- **Standard**: Cohérent avec JSON/Python (null est une valeur valide)

**Implémentation:**

```python
class Message:
    """Message with required value (None allowed)"""

    def __init__(self,
                 key: str,
                 timestamp: Union[datetime, str],
                 value: Any,  # REQUIRED (but None is valid)
                 tags: dict = None,
                 id: str = None):
        """
        Create a message.

        Args:
            key: Message key (required, non-empty string)
            timestamp: UTC timestamp (required)
            value: Message value (required parameter, but None is a valid value)
            tags: Optional metadata dict
            id: Optional trace ID

        Raises:
            ValueError: If key or timestamp is missing/invalid
            TypeError: If value parameter is not provided
        """
        # Validation
        if not key or not isinstance(key, str):
            raise ValueError("Message key must be a non-empty string")

        if timestamp is None:
            raise ValueError("Message timestamp is required")

        # value is REQUIRED as parameter
        # But None is a valid value (no validation here)
        # This allows value to be: None, "", 0, False, [], {}, or any object

        # Tags: None transformed to empty dict
        if tags is None:
            tags = {}

        # Individual tag values CAN be None (optional fields)
        if not isinstance(tags, dict):
            raise ValueError("Message tags must be a dict")

        self.key = key
        self.timestamp = self._normalize_timestamp(timestamp)
        self.value = value  # Can be None, "", 0, False, {}, [], etc.
        self.tags = tags
        self.id = id or generate_trace_id()

    def _normalize_timestamp(self, ts):
        """Normalize timestamp to UTC datetime"""
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                # Assume UTC if naive
                return ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        raise ValueError(f"Invalid timestamp: {ts}")
```

**Exemples d'Utilisation:**

**Cas 1 - Capteur Normal vs Défaillant:**
```python
# ✅ Capteur fonctionne - valeur numérique
Message(
    key="temp",
    timestamp=now,
    value=25.5,
    tags={"sensor": "T01", "status": "ok"}
)

# ✅ Capteur HS - valeur null explicite
Message(
    key="temp",
    timestamp=now,
    value=None,
    tags={"sensor": "T01", "status": "disconnected"}
)

# ❌ Paramètre manquant - erreur
Message(
    key="temp",
    timestamp=now
    # TypeError: __init__() missing 1 required positional argument: 'value'
)
```

**Cas 2 - Distinction Sémantique:**
```python
# Différentes valeurs avec sémantiques différentes

# 1. Null = pas de donnée
Message(key="sensor.reading", value=None)

# 2. Chaîne vide = chaîne vide légitime (commande vide, etc.)
Message(key="gcode.command", value="")

# 3. Zéro = valeur numérique zéro
Message(key="motor.speed", value=0)

# 4. False = booléen faux
Message(key="heater.on", value=False)

# 5. Liste vide = aucune erreur (différent de "erreur inconnue")
Message(key="errors", value=[])

# 6. Dict vide = configuration vide
Message(key="settings", value={})
```

**Cas 3 - Tags avec Valeurs Null:**
```python
# ✅ Tags peuvent aussi avoir None (champs optionnels absents)
Message(
    key="user.login",
    timestamp=now,
    value="success",
    tags={
        "user_id": "U123",
        "email": "user@example.com",
        "phone": None,      # Pas de téléphone renseigné
        "address": None,    # Pas d'adresse
        "country": "FR"     # Pays renseigné
    }
)
```

**Gestion dans les Transformations:**

```python
# Pattern 1: Skip les messages avec valeur null
class SkipNullTransform(Transform):
    """Skip messages with null values"""

    def transform(self, message: Message):
        if message.value is None:
            # Log et skip
            logger.debug(f"Skipping null value for key '{message.key}'")
            return []  # Pas de message en sortie

        # Traiter normalement
        return [Message(
            key=message.key,
            value=self.process(message.value)
        )]

# Pattern 2: Remplacer null par défaut
class NullToDefaultTransform(Transform):
    """Replace null with default value"""

    def __init__(self, input_channel, output_channel, default_value):
        super().__init__(input_channel, output_channel)
        self.default_value = default_value

    def transform(self, message: Message):
        value = (message.value if message.value is not None
                 else self.default_value)

        return [Message(
            key=message.key,
            timestamp=message.timestamp,
            value=value,
            tags={**message.tags, "defaulted": message.value is None}
        )]

# Utilisation pour capteurs
NullToDefaultTransform(
    input_channel="sensors.temp",
    output_channel="sensors.temp.normalized",
    default_value=20.0  # Température ambiante par défaut
)

# Pattern 3: Convertir null en alerte
class NullToAlertTransform(Transform):
    """Generate alert for null values"""

    def transform(self, message: Message):
        if message.value is None:
            # Générer une alerte
            return [Message(
                key="sensor.offline",
                timestamp=message.timestamp,
                value={
                    "sensor_key": message.key,
                    "last_seen": message.timestamp
                },
                tags={**message.tags, "alert_type": "missing_data"}
            )]

        # Valeur présente, passer tel quel
        return [message]
```

**Sérialisation JSON:**

```python
# JSON supporte null nativement
message = Message(
    key="temp",
    timestamp=datetime(2024, 1, 24, 14, 30, tzinfo=timezone.utc),
    value=None,
    tags={"sensor": "T01", "location": None}
)

# Sérialisation
json_str = json.dumps(message.to_dict())
# → '{"key":"temp","timestamp":"2024-01-24T14:30:00Z","value":null,"tags":{"sensor":"T01","location":null},"id":"..."}'

# Désérialisation préserve None
loaded = Message.from_json(json_str)
assert loaded.value is None           # ✅ Préservé
assert loaded.tags["location"] is None  # ✅ Préservé
```

**Use Case Imprimante 3D:**

```python
# Impression en cours - toutes les valeurs présentes
Message(
    key="extruder.force",
    timestamp=now,
    value=120.5,  # Newton
    tags={"printer": "P01", "state": "printing"}
)

# Impression arrêtée - force non applicable
Message(
    key="extruder.force",
    timestamp=now,
    value=None,   # Pas de force (imprimante idle)
    tags={"printer": "P01", "state": "idle"}
)

# Transformation pour calcul de viscosité
class ViscosityComputer(StatefulTransform):
    input_channels = ["sensors.temp", "sensors.speed", "sensors.force"]
    output_channel = "indicators.viscosity"

    def transform(self, message: Message) -> List[Message]:
        # Vérifier que tous les capteurs ont des valeurs
        if any(msg.value is None for msg in self.latest.values()):
            # Au moins un capteur HS, pas de calcul possible
            return []

        # Tous les capteurs OK, calculer
        viscosity = self.compute_viscosity(
            self.latest["sensors.temp"].value,
            self.latest["sensors.speed"].value,
            self.latest["sensors.force"].value
        )

        return [Message(
            key="viscosity",
            timestamp=message.timestamp,
            value=viscosity
        )]
```

**Documentation:**

```
MESSAGE VALUES

Required Parameter:
  - The 'value' parameter is REQUIRED when creating a message
  - Omitting it raises TypeError

Valid Values:
  - None: Explicitly represents "no data" or "not available"
  - "" (empty string): Different from None, represents legitimate empty string
  - 0: Different from None, represents numeric zero
  - False: Different from None, represents boolean false
  - [] or {}: Different from None, represents empty collection
  - Any other Python object

Semantic Distinction:
  value=None    → "No data available" (sensor offline, etc.)
  value=""      → "Empty string" (valid empty command, etc.)
  value=0       → "Numeric zero" (motor stopped, etc.)
  value=False   → "Boolean false" (heater off, etc.)

Tags:
  - Individual tag values CAN also be None (optional metadata)

Example:
  # Sensor offline
  Message(key="temp", value=None, tags={"status": "offline"})

  # Motor stopped
  Message(key="speed", value=0, tags={"status": "ok"})
```

**Alternatives Rejetées:**
- **Option A (null interdit)**: Trop restrictif, empêche de représenter données manquantes
- **Option C (value optionnel)**: Peut cacher des bugs (oubli du paramètre)
- **Option D (sentinel MISSING)**: Sur-ingénierie, None suffit pour v1.0

---

#### **Q10.5: Conventions de Nommage des Canaux**
**Question:** Quelles sont les règles et restrictions pour les noms de canaux ? Caractères autorisés, longueur, mots réservés, casse ?

**Decision:** **Option B - Conventions Strictes mais Flexibles** ✅

**Principe:**
Définir des **règles claires et strictes** pour les noms de canaux avec validation au runtime, tout en restant **flexible** pour les cas d'usage pratiques.

**Règles de Nommage:**

1. **Séparateur hiérarchique**: Point (`.`) obligatoire, pas de slash (`/`)
2. **Caractères autorisés**:
   - Lettres: `a-z`, `A-Z`
   - Chiffres: `0-9`
   - Underscore: `_`
   - Point: `.` (séparateur uniquement, pas au début/fin)
   - Tiret: `-` (au milieu uniquement, pas au début/fin)
3. **Casse**: Sensible (`sensors.temp` ≠ `sensors.TEMP`)
4. **Longueur**: 1 à 256 caractères
5. **Format**: Doit commencer par `[a-zA-Z0-9_]`, finir par `[a-zA-Z0-9_]`
6. **Préfixes réservés**: `_metrics`, `_dlq`, `_system` (warning mais pas bloquant)

**Pattern de Validation:**
```python
import re

CHANNEL_SEPARATOR = "."
CHANNEL_MIN_LENGTH = 1
CHANNEL_MAX_LENGTH = 256
RESERVED_PREFIXES = ["_metrics", "_dlq", "_system"]

# Commence par alphanum/_, contient alphanum/_/./-,  finit par alphanum/_
CHANNEL_PATTERN = re.compile(r"^[a-zA-Z0-9_]([a-zA-Z0-9_.-]*[a-zA-Z0-9_])?$")
```

**Exemples Valides:**
```python
# ✅ Noms valides
"sensors.temp"                     # Simple
"sensors.printer_01.temperature"   # Underscore OK
"data.raw.2024"                    # Chiffres OK
"ALERTS.HIGH"                      # Uppercase OK
"a"                                # 1 caractère OK
"sensors.temp-external"            # Tiret au milieu OK
"_metrics.broker"                  # Système (réservé mais valide avec warning)
"My_Channel.Sub_1"                 # Mixed case + underscore OK
```

**Exemples Invalides:**
```python
# ❌ Noms invalides avec messages d'erreur
"sensors/temp"           # → "Use dots (.) as separators, not slashes (/)"
"sensors.temp."          # → "Cannot start or end with a dot"
".sensors.temp"          # → "Cannot start or end with a dot"
"sensors..temp"          # → "Cannot contain consecutive dots (..)"
"sensors temp"           # → "Cannot contain spaces"
"sensors.temp.°C"        # → "Invalid character: '°'"
"-sensors.temp"          # → "Invalid format (cannot start with hyphen)"
"sensors.temp-"          # → "Invalid format (cannot end with hyphen)"
"a" * 300                # → "Too long (max 256 chars): 300 chars"
""                       # → "Cannot be empty"
"sensors.*"              # → "Wildcards not allowed in channel names (publication)"
```

**Implémentation:**

```python
import re
import warnings
from typing import Optional

class ChannelValidator:
    """Validate channel names against naming conventions"""

    # Configuration
    SEPARATOR = "."
    MIN_LENGTH = 1
    MAX_LENGTH = 256
    RESERVED_PREFIXES = ["_metrics", "_dlq", "_system"]

    # Pattern regex
    PATTERN = re.compile(r"^[a-zA-Z0-9_]([a-zA-Z0-9_.-]*[a-zA-Z0-9_])?$")

    @classmethod
    def validate(cls, channel_name: str,
                 allow_wildcards: bool = False) -> Optional[str]:
        """
        Validate channel name against naming rules.

        Args:
            channel_name: Channel name to validate
            allow_wildcards: Allow * and ** (for subscriptions only)

        Returns:
            Error message if invalid, None if valid

        Examples:
            >>> ChannelValidator.validate("sensors.temp")
            None  # Valid

            >>> ChannelValidator.validate("sensors/temp")
            "Use dots (.) as separators, not slashes (/)"

            >>> ChannelValidator.validate("sensors.*", allow_wildcards=True)
            None  # Valid for subscriptions
        """
        # 1. Check empty
        if not channel_name:
            return "Channel name cannot be empty"

        # 2. Check length
        if len(channel_name) < cls.MIN_LENGTH:
            return f"Channel name too short (min {cls.MIN_LENGTH} char)"

        if len(channel_name) > cls.MAX_LENGTH:
            return (f"Channel name too long (max {cls.MAX_LENGTH} chars): "
                    f"{len(channel_name)} chars")

        # 3. Handle wildcards
        if "*" in channel_name:
            if not allow_wildcards:
                return ("Wildcards (* or **) not allowed in channel names "
                        "(use for subscriptions only)")

            # Validate wildcard usage
            # Replace ** with placeholder for validation
            temp_name = channel_name.replace("**", "XX").replace("*", "X")
        else:
            temp_name = channel_name

        # 4. Validate against pattern
        if not cls.PATTERN.match(temp_name):
            return cls._get_pattern_error(channel_name)

        # 5. Check for consecutive separators
        if ".." in channel_name:
            return "Channel name cannot contain consecutive dots (..)"

        # 6. Check start/end with separator
        if channel_name.startswith(".") or channel_name.endswith("."):
            return "Channel name cannot start or end with a dot"

        return None  # Valid!

    @classmethod
    def _get_pattern_error(cls, channel_name: str) -> str:
        """Generate helpful error message for pattern mismatch"""
        # Check for common mistakes
        if " " in channel_name:
            return "Channel name cannot contain spaces"

        if "/" in channel_name:
            return "Use dots (.) as separators, not slashes (/)"

        if channel_name.startswith("-") or channel_name.endswith("-"):
            return "Channel name cannot start or end with a hyphen"

        # Find first invalid character
        for char in channel_name:
            if not (char.isalnum() or char in "._-"):
                return (f"Invalid character in channel name: '{char}' "
                        f"(allowed: a-z, A-Z, 0-9, _, ., -)")

        return ("Channel name format invalid "
                "(must match: [a-zA-Z0-9_]([a-zA-Z0-9_.-]*[a-zA-Z0-9_])?)")

    @classmethod
    def is_system_channel(cls, channel_name: str) -> bool:
        """Check if channel uses reserved system prefix"""
        return any(channel_name.startswith(prefix)
                   for prefix in cls.RESERVED_PREFIXES)

    @classmethod
    def warn_if_system_channel(cls, channel_name: str):
        """Warn user if using a system channel"""
        if cls.is_system_channel(channel_name):
            warnings.warn(
                f"Channel '{channel_name}' uses reserved system prefix. "
                f"Reserved prefixes: {cls.RESERVED_PREFIXES}",
                category=RuntimeWarning
            )
```

**Utilisation dans le Broker:**

```python
class Broker:
    def publish(self, channel: str, message: Message):
        """Publish message with channel validation"""
        # Valider le nom de canal
        error = ChannelValidator.validate(channel, allow_wildcards=False)
        if error:
            raise ValueError(
                f"Invalid channel name '{channel}': {error}\n"
                f"See documentation for naming conventions."
            )

        # Warning si canal système
        ChannelValidator.warn_if_system_channel(channel)

        # Publier
        self._do_publish(channel, message)

    def subscribe(self, channel_pattern: str, destination: Destination):
        """Subscribe to channel pattern with validation"""
        # Valider le pattern (wildcards autorisés)
        error = ChannelValidator.validate(channel_pattern,
                                          allow_wildcards=True)
        if error:
            raise ValueError(
                f"Invalid channel pattern '{channel_pattern}': {error}"
            )

        # Subscribe
        self._do_subscribe(channel_pattern, destination)
```

**Exemples d'Utilisation:**

```python
# ✅ Publications valides
broker.publish("sensors.temp", msg)
broker.publish("sensors.printer_01.temp", msg)
broker.publish("ALERTS.HIGH_TEMP", msg)

# ❌ Publications invalides
try:
    broker.publish("sensors/temp", msg)
except ValueError as e:
    print(e)
    # ValueError: Invalid channel name 'sensors/temp':
    #   Use dots (.) as separators, not slashes (/)

try:
    broker.publish("sensors..temp", msg)
except ValueError as e:
    print(e)
    # ValueError: Invalid channel name 'sensors..temp':
    #   Cannot contain consecutive dots (..)

# ✅ Souscriptions avec wildcards
broker.subscribe("sensors.*", console_dest)      # OK
broker.subscribe("sensors.**", file_dest)        # OK
broker.subscribe("sensors.*.temp", db_dest)      # OK

# ❌ Publication avec wildcard (interdit)
try:
    broker.publish("sensors.*", msg)
except ValueError as e:
    print(e)
    # ValueError: Invalid channel name 'sensors.*':
    #   Wildcards not allowed in channel names (use for subscriptions only)
```

**Cas Spéciaux:**

```python
# Casse sensible - deux canaux différents
broker.publish("sensors.temp", msg1)  # Canal 1
broker.publish("sensors.TEMP", msg2)  # Canal 2 (différent!)

# Underscore au début (système) - warning
broker.publish("_metrics.custom", msg)
# ⚠️ RuntimeWarning: Channel '_metrics.custom' uses reserved system prefix
# ✅ Mais publication réussie

# Un seul caractère - valide
broker.publish("a", msg)  # ✅ OK

# Longueur maximale
broker.publish("a" * 256, msg)   # ✅ OK (exactement 256)
broker.publish("a" * 257, msg)   # ❌ ValueError: Too long
```

**Convention Recommandée (Best Practices):**

```
CHANNEL NAMING BEST PRACTICES

Hierarchical Format:
  namespace.category.subcategory.item

Examples:
  Good:
    sensors.temp                    # Simple sensor
    sensors.printer_01.temp         # Specific device
    sensors.printer_01.temp.nozzle  # Specific component
    alerts.high_temp                # Alert type
    events.user.login               # Event category
    _metrics.broker.throughput      # System metrics

  Avoid:
    Temp                            # Too generic
    sensors_temp                    # Use dots, not underscores
    sensors.Temp.Current            # Inconsistent casing
    s.t                             # Too cryptic

Naming Tips:
  - Use lowercase for consistency (temp, not TEMP)
  - Use dots for hierarchy (sensors.temp.nozzle)
  - Use underscores within words (printer_01, high_temp)
  - Be descriptive but concise
  - Group related channels (sensors.*, alerts.*)

Reserved Prefixes (avoid unless system use):
  _metrics.**   → Framework metrics
  _dlq.**       → Dead letter queues
  _system.**    → System channels
```

**Documentation Utilisateur:**

```
CHANNEL NAMING RULES

Format:
  [a-zA-Z0-9_]([a-zA-Z0-9_.-]*[a-zA-Z0-9_])?

Rules:
  ✅ Allowed: a-z, A-Z, 0-9, _, ., - (hyphen in middle only)
  ✅ Separator: dots (.) for hierarchy
  ✅ Length: 1-256 characters
  ✅ Case: sensitive (temp ≠ TEMP)

  ❌ Forbidden: spaces, slashes, special characters
  ❌ Cannot: start/end with dot, consecutive dots (..)
  ❌ Cannot: start/end with hyphen

Examples:
  ✅ sensors.temp
  ✅ sensors.printer_01.temperature
  ✅ ALERTS.HIGH
  ❌ sensors/temp (use dots, not slashes)
  ❌ sensors..temp (no consecutive dots)
  ❌ sensors temp (no spaces)

Wildcards (subscriptions only):
  *    → Match single level (sensors.* → sensors.temp)
  **   → Match multiple levels (sensors.** → sensors.temp.external)

Reserved Prefixes:
  _metrics, _dlq, _system (system use, warning if used)
```

**Alternatives Rejetées:**
- **Option A (Très permissif)**: Risque de noms ambigus et problèmes d'interopérabilité
- **Option C (Ultra-restrictif)**: Trop contraignant, bloque des cas légitimes (uppercase, tirets)
- **Option D (Configurable)**: Complexité non justifiée, mieux vaut un standard clair

---

### Additional Questions: Scope & Configuration

#### **Q11: Périmètre du Framework**
**Question:** Qu'est-ce qui est explicitement DANS et HORS du scope de COD3S Data par version ?

**Decision:** **Approche progressive par versions** ✅

**Vision par Version:**

**✅ V1.0 - Core + Configuration YAML**

Scope:
```
Message Management:
  ✅ Message structure (key, timestamp, value, tags, id)
  ✅ Publish/Subscribe via broker in-memory
  ✅ Wildcard subscriptions (*, **)
  ✅ Delivery guarantees (at-most-once, at-least-once)
  ✅ Dead Letter Queue (DLQ)
  ✅ Message size limits
  ✅ Null value handling

Components:
  ✅ Sources: MQTT, HTTP, File, Console, Random
  ✅ Destinations: Console, File, In-Memory, HTTP POST
  ✅ Transformations: Filter, Map, Stateful Multi-Channel
  ✅ Plugin system (Python class-based)

Data Flow:
  ✅ Channel routing (hierarchical avec dots)
  ✅ Dynamic channel creation (lazy)
  ✅ Batch replay (BATCH, REALTIME, TRANSPOSE modes)
  ✅ Backpressure (bounded buffers, drop-oldest)
  ✅ Cycle detection (interdiction stricte)
  ✅ Channel naming validation

Configuration:
  ✅ YAML configuration complète
  ✅ Programmatic configuration (Python code)
  ✅ Environment variables pour secrets
  ✅ Configuration validation au démarrage

Observability:
  ✅ Metrics as messages (_metrics.**)
  ✅ Debug mode + trace IDs
  ✅ DLQ for failed messages
  ✅ Logging (standard Python logging)

Deployment:
  ✅ Embedded (import cod3s_data)
  ✅ Standalone script
  ✅ Single process
```

Hors Scope V1.0:
```
  ❌ Message broker externe (Redis/Kafka) - V2.0
  ❌ Base de données intégrée - V2.0
  ❌ Déploiement Docker packagé - V2.0
  ❌ Clustering / HA
  ❌ GUI / Dashboard
  ❌ Multi-language support
```

**🚀 V2.0 - Production Ready (Docker + Broker + BDD)**

Ajouts par rapport à V1.0:
```
Infrastructure:
  ✅ Docker image officielle
  ✅ Docker Compose templates
  ✅ Support broker externe (Redis, Kafka, RabbitMQ)
  ✅ Support base de données (PostgreSQL, MongoDB)
  ✅ Destinations BDD (PostgreSQL, MongoDB, InfluxDB)
  ✅ Prometheus metrics exporter (en plus de metrics-as-messages)

Deployment:
  ✅ Multi-container deployment
  ✅ Kubernetes manifests (exemples)
  ✅ Health checks
  ✅ Graceful shutdown

Advanced Features:
  ✅ Backpressure to sources
  ✅ Circuit breaker pattern
  ✅ Control loops / Feedback systems (cycles contrôlés)
  ✅ Schema validation (optionnel)

Configuration:
  ✅ Configuration hot-reload
  ✅ Remote configuration (etcd, Consul)
```

Hors Scope V2.0:
```
  ❌ GUI / Dashboard - V3.0+
  ❌ Multi-tenancy
  ❌ Multi-language SDKs
  ❌ Workflow orchestration (DAG)
```

**💡 Idées Futures (V3.0+) - Documentées pour Référence**

Catégorie 1: User Interface
```
  - Web dashboard pour monitoring
  - Visual dataflow designer (drag & drop)
  - Configuration UI
  - Real-time metrics visualization
```

Catégorie 2: Advanced Processing
```
  - Machine Learning intégré (anomaly detection, forecasting)
  - Complex Event Processing (CEP) avancé
  - Window aggregations (tumbling, sliding, session)
  - Stream joins SQL-like
  - Stateful aggregations (sum, avg, percentiles)
```

Catégorie 3: Enterprise Features
```
  - Multi-tenancy (isolation entre organisations)
  - Authentification/Autorisation (OAuth, LDAP, RBAC)
  - Audit logging complet
  - Compliance features (GDPR, encryption at rest)
  - Quota management
```

Catégorie 4: Platform Features
```
  - Schema registry
  - Data versioning
  - Time-travel queries
  - Workflow orchestration (DAG-based comme Airflow)
  - Scheduler cron-like intégré
  - Service mesh integration
```

Catégorie 5: Multi-Language
```
  - Java SDK
  - Go SDK
  - JavaScript/TypeScript SDK
  - Rust SDK
  - gRPC protocol pour interop
```

Catégorie 6: Advanced Reliability
```
  - Exactly-once delivery semantics
  - Distributed tracing (OpenTelemetry)
  - Automatic failover
  - Active-active replication
  - ACID transactions
```

**Philosophy:**

```
COD3S Data Philosophy:

V1.0 - "Get it Working"
  → Core features solides
  → Configuration simple (YAML + code)
  → Development-friendly
  → Single process, embedded ou standalone

V2.0 - "Get it to Production"
  → Docker packaging
  → External broker/database support
  → Production deployment patterns
  → Observability & reliability

V3.0+ - "Get it to Scale"
  → Based on real user feedback
  → Add features that users actually need
  → Don't over-engineer upfront

Core Principle:
  "Integration over Implementation"
  → Use best-of-breed external tools
  → Focus on what makes COD3S unique: temporal dataflow + simplicity
  → Don't reinvent databases, brokers, auth systems
```

**Deliverables par Version:**

V1.0 Deliverables:
```
- Python package (pip install cod3s-data)
- CLI tool (cod3s-data run config.yaml)
- Documentation complète
- Exemples YAML
- Tutorial Getting Started
- Plugin development guide
```

V2.0 Deliverables:
```
- Docker image (docker pull cod3s/cod3s-data:2.0)
- Docker Compose templates
- Kubernetes manifests (examples)
- Broker integration guides (Redis, Kafka, RabbitMQ)
- Database integration guides (PostgreSQL, MongoDB)
- Production deployment guide
- Performance tuning guide
```

V3.0+ Deliverables:
```
- Based on user demand
- Prioritized by feedback
```

**Decision Matrix:**

| Feature | V1.0 | V2.0 | V3.0+ | Never |
|---------|------|------|-------|-------|
| Core routing | ✅ | | | |
| YAML config | ✅ | | | |
| Python plugins | ✅ | | | |
| In-memory broker | ✅ | | | |
| Docker image | | ✅ | | |
| External broker | | ✅ | | |
| Database support | | ✅ | | |
| Backpressure | | ✅ | | |
| Web UI | | | ✅ | |
| Multi-language | | | ✅ | |
| ML intégré | | | ✅ | |
| Auth/RBAC | | | ✅ | |
| Workflow DAG | | | | ❌ |
| Own message broker | | | | ❌ |
| Own database | | | | ❌ |

**Rationale:**

V1.0 Focus:
- Valider le concept et l'architecture core
- Permettre le développement rapide
- Configuration simple mais complète (YAML)
- Utilisable immédiatement pour prototypage

V2.0 Focus:
- Production-ready deployment
- Scalabilité via brokers/BDD externes
- Patterns de déploiement cloud-native
- Basé sur feedback V1.0

V3.0+ Focus:
- Features avancées basées sur demande réelle
- Ne pas sur-engineer V1.0/V2.0
- Rester agile et réactif aux besoins

**Documentation Future Ideas (pour ne pas oublier):**

Créer un document séparé `FUTURE_IDEAS.md` qui liste:
- Toutes les idées V3.0+
- Features proposées mais rejetées
- Feedback utilisateurs
- Wishlist communauté

Ce document servira de backlog pour les futures versions sans polluer le scope V1.0/V2.0.

---

#### **Q12: Objectifs de Performance**
**Question:** Quels sont les objectifs de performance pour COD3S Data v1.0 ? Latence, throughput, limites de scalabilité ?

**Decision:** **Option B - Objectifs Réalistes pour v1.0** ✅

**Principe:**
Définir des objectifs de performance **réalistes et mesurables** pour v1.0 (single process, in-memory), suffisants pour 90% des cas d'usage IoT/monitoring. V2.0 visera la vraie scalabilité production.

**V1.0 Performance Targets:**

**Latence End-to-End:**
- **p50**: < 10ms (médiane)
- **p99**: < 50ms (99ème percentile)
- **p999**: < 100ms (pire cas)

**Throughput:**
- Small messages (< 1 KB): **10,000 msg/s** sustained
- Medium messages (10 KB): **1,000 msg/s** sustained
- Large messages (100 KB - 1 MB): **100 msg/s** sustained

**Scalabilité (Single Process):**
- Channels actifs: **1,000 max**
- Transformations actives: **100 max**
- Destinations actives: **50 max**
- Messages en buffer: **10,000 msg/canal** (configurable)
- Mémoire: **< 512 MB** (workload typique)

**Batch Replay:**
- BATCH/TRANSPOSE mode: **50,000 msg/s**
- REALTIME mode: **±1ms/heure** de précision

**Startup:**
- Framework init: **< 1s**
- YAML loading: **< 100ms**
- Components init (50 items): **< 5s**

**Memory:**
- Base framework: **< 50 MB**
- Typical workload: **< 200 MB**
- Per-message overhead: **< 1 KB**

**Use Case Validation (Imprimante 3D):**
```
Configuration:
  - 10 sensors × 10 Hz = 100 msg/s
  - 3 transformations
  - 2 destinations

Performance attendue:
  - Latency: ~5ms (p99) ✅ << 50ms target
  - Throughput: 100 msg/s ✅ 1% de capacité
  - Memory: ~100 MB ✅ << 512 MB limit

→ V1.0 largement suffisant ✅
```

**V2.0 Targets (Production avec Broker):**
- Throughput: **100,000 msg/s** (10x v1.0)
- Channels: **10,000+**
- Multi-process scaling

**Non-Goals v1.0:**
- ❌ Sub-millisecond latency
- ❌ Millions msg/s
- ❌ Hard real-time guarantees

**Testing:**
- Benchmarks: latency (p50/p99/p999), throughput, memory
- CI/CD: regression tests, performance tracking
- Tools: pytest-benchmark, memory_profiler

**Rationale:**
- Réaliste et atteignable sans sur-optimisation
- Suffisant pour 90% des cas IoT
- V2.0 scale horizontalement si besoin

---

#### **Q13: Modèles de Déploiement**
**Question:** Quels modes de déploiement COD3S Data doit-il supporter ? Embedded, standalone, Docker, Kubernetes, serverless ?

**Decision:** **Option A - V1.0 Focus (Embedded + Standalone + CLI)** ✅

**Principe:**
V1.0 se concentre sur les **déploiements simples et accessibles** pour démarrer rapidement. V2.0 ajoute les **déploiements production** (Docker, Kubernetes).

**✅ V1.0 - Déploiements Supportés:**

**1. Mode Embedded (Library):**
```python
# Import dans une application Python existante
import cod3s_data as cod3s

broker = cod3s.Broker()
mqtt = cod3s.sources.MQTTSource(channel="sensors.temp", ...)
console = cod3s.destinations.ConsoleDestination(channel="**")
broker.start()
```
**Use Case:** Application Python existante qui a besoin de routing

**2. Mode Standalone (Python Script):**
```python
# my_dataflow.py - Script complet
from cod3s_data import Broker, sources, destinations

broker = Broker()
# ... configuration complète en code

if __name__ == "__main__":
    broker.start()
```
```bash
python my_dataflow.py
```
**Use Case:** Script dédié pour un workflow spécifique

**3. Mode CLI (YAML Configuration):**
```yaml
# config.yaml
broker:
  max_value_size: 1048576

sources:
  - type: mqtt
    channel: sensors.temp
    broker_url: mqtt://localhost

transformations:
  - type: filter
    input_channel: sensors.temp
    output_channel: sensors.temp.filtered
    filter: "value > 20"

destinations:
  - type: console
    channel: "**"
```
```bash
# Installation
pip install cod3s-data

# Exécution
cod3s-data run config.yaml
cod3s-data run config.yaml --debug
```
**Use Case:** Configuration déclarative, prototypage rapide

**Installation V1.0:**
```bash
# PyPI package
pip install cod3s-data

# Avec extras optionnels
pip install cod3s-data[mqtt]      # MQTT support
pip install cod3s-data[postgres]  # PostgreSQL support
pip install cod3s-data[all]       # Tout installer
```

**✅ V2.0 - Déploiements Production:**

**4. Mode Docker:**
```dockerfile
FROM cod3s/cod3s-data:2.0
COPY config.yaml /app/
CMD ["cod3s-data", "run", "/app/config.yaml"]
```
```bash
docker run -d -v /data:/data cod3s/cod3s-data:2.0
```

**5. Docker Compose:**
```yaml
services:
  cod3s-data:
    image: cod3s/cod3s-data:2.0
    depends_on: [redis, postgres]
```

**6. Kubernetes:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cod3s-data
spec:
  replicas: 3
  # ...
```
```bash
# Helm chart
helm install cod3s cod3s/cod3s-data
```

**❌ Hors Scope (Toutes Versions):**

**Serverless (Lambda, Azure Functions):**
- ❌ Architecture incompatible (COD3S = long-running, Lambda = event-driven)
- ❌ COD3S a des sources actives (MQTT, polling), pas stateless
- **Alternative:** Utiliser COD3S sur EC2/ECS/Fargate

**Managed Service / SaaS:**
- ❌ Hors scope pour projet open-source
- Peut être considéré comme offre commerciale future

**Comparaison:**

| Mode | V1.0 | V2.0 | Use Case | Complexité |
|------|------|------|----------|------------|
| Embedded | ✅ | ✅ | App Python | Faible |
| Standalone | ✅ | ✅ | Script dédié | Faible |
| CLI + YAML | ✅ | ✅ | Config simple | Faible |
| Docker | ❌ | ✅ | Production | Moyenne |
| Docker Compose | ❌ | ✅ | Stack complète | Moyenne |
| Kubernetes | ❌ | ✅ | Scalable | Élevée |
| Serverless | ❌ | ❌ | N/A | N/A |

**Rationale:**
- **V1.0 Accessible**: Démarrage rapide (5 min), pas de Docker requis
- **V1.0 Flexible**: Embedded, script, ou CLI selon besoin
- **V2.0 Production**: Docker + K8s pour déploiements réels
- **Progressif**: Apprendre avec V1.0, déployer avec V2.0

---

#### **Q14: Gestion de la Configuration**
**Question:** Comment la configuration de COD3S Data doit-elle être gérée ? Code Python, fichiers YAML, variables d'environnement, combinaison ?

**Decision:** **Option A - YAML + Python + Env Vars (Triple Approche)** ✅

**Principe:**
Supporter **trois modes de configuration** complémentaires pour maximiser la flexibilité : YAML pour la structure déclarative, Python pour la logique custom, variables d'environnement pour les secrets.

**✅ V1.0 - Configuration Management:**

**1. YAML Configuration (Principal):**
```yaml
# config.yaml - Configuration déclarative

broker:
  max_value_size: 1048576        # 1 MB
  max_tags_count: 100
  strict_mode: false

sources:
  - type: mqtt
    channel: sensors.temp
    broker_url: ${MQTT_BROKER_URL}  # Variable d'environnement
    topic: sensors/temperature

  - type: file
    channel: logs.app
    file_path: /var/log/app.log
    format: jsonl

transformations:
  - type: filter
    input_channel: sensors.temp
    output_channel: sensors.temp.filtered
    filter: "value > 20"

  # Custom transformation (classe Python)
  - type: custom
    class: myapp.transforms.ViscosityComputer
    input_channels: [sensors.temp, sensors.speed, sensors.force]
    output_channel: indicators.viscosity

destinations:
  - type: console
    channel: "**"

  - type: file
    channel: sensors.**
    file_path: /data/sensors-${DATE}.jsonl
    format: jsonl
```

```bash
# Exécution avec YAML
cod3s-data run config.yaml
```

**2. Environment Variables (Secrets):**
```bash
# .env file (gitignored)
MQTT_BROKER_URL=mqtt://broker.example.com:1883
API_TOKEN=secret_token_123
POSTGRES_URL=postgresql://user:pass@localhost/db
DATE=$(date +%Y%m%d)

# Load et run
export $(cat .env | xargs)
cod3s-data run config.yaml
```

**Syntaxe:** `${VAR_NAME}` ou `${VAR_NAME:default_value}`

**3. Programmatic Configuration (Python):**
```python
# Pour logique custom complexe
from cod3s_data import Broker, sources, destinations

broker = Broker(max_value_size=1024*1024)

mqtt = sources.MQTTSource(
    channel="sensors.temp",
    broker_url=os.getenv("MQTT_BROKER_URL")
)
broker.add_source(mqtt)

# Transformation custom avec code
class MyTransform(StatefulTransform):
    def transform(self, message):
        # Logique métier complexe
        return [...]

broker.add_transformation(MyTransform())
broker.start()
```

**4. Hybrid (YAML + Python):**
```yaml
# config.yaml - Structure
transformations:
  - type: custom
    class: myapp.transforms.ViscosityComputer  # Charge classe Python
```

```python
# myapp/transforms.py - Logique custom
class ViscosityComputer(StatefulTransform):
    input_channels = ["sensors.temp", "sensors.speed"]
    output_channel = "indicators.viscosity"

    def transform(self, message):
        # Calcul complexe
        return [...]
```

**Configuration Validation:**
```bash
# Valider avant de démarrer
cod3s-data validate config.yaml

# Output:
# ✅ Configuration valid
#   - 3 sources configured
#   - 2 transformations configured
#   - All required env vars present
#   - All custom classes loadable

# Ou si erreur:
# ❌ Configuration invalid:
#   - Missing env var: MQTT_BROKER_URL
#   - Invalid channel name: sensors/temp
#   - Custom class not found: myapp.Unknown
```

**✅ V2.0 - Configuration Avancée:**

**Hot-Reload (Sans Redémarrage):**
```python
broker = Broker(config_file="config.yaml", hot_reload=True)
# Auto-reload si config.yaml modifié
```

```bash
# Ou signal manuel
kill -HUP <pid>

# Ou API
curl -X POST http://localhost:8080/api/reload
```

**Configuration Distante:**
```yaml
config_source:
  type: etcd
  endpoints: [etcd1:2379]
  key: /cod3s/config
```

**Formats Supportés:**

| Format | V1.0 | V2.0 | Use Case |
|--------|------|------|----------|
| YAML | ✅ | ✅ | Configuration principale |
| Python code | ✅ | ✅ | Logique custom |
| Env vars | ✅ | ✅ | Secrets |
| JSON | ❌ | ✅ | API, programmatic |
| Remote (etcd) | ❌ | ✅ | Config centralisée |

**Best Practices:**
```
Configuration Best Practices:

Structure:
  ✅ YAML pour configuration déclarative
  ✅ Env vars pour secrets (never commit!)
  ✅ Python code pour logique métier complexe

Secrets:
  ✅ ${ENV_VAR} dans YAML
  ✅ .env file (gitignored) pour dev
  ✅ K8s Secrets / Vault pour production

Organization:
  ✅ config/dev.yaml, config/prod.yaml
  ✅ Shared base + env-specific overrides

Validation:
  ✅ cod3s-data validate avant deploy
  ✅ CI/CD config checks
```

**Rationale:**
- **Flexibilité**: Triple approche couvre tous les cas d'usage
- **Sécurité**: Secrets jamais en clair dans YAML
- **Simplicité**: YAML pour 90% des cas
- **Puissance**: Python pour logique custom complexe
- **Standard**: Patterns familiers (env vars, YAML)

---

#### **Q15: Testing & Simulation**
**Question:** Quelles capacités de test et simulation COD3S Data doit-il fournir pour faciliter le développement et le debugging ? Record/replay, chaos testing, assertions ?

**Decision:** **Option A - Essentials v1.0, Advanced v2.0** ✅

**Principe:**
V1.0 fournit les **outils essentiels** pour tester et debugger (test sources, record/replay, assertions). V2.0 ajoute les **features avancées** (chaos testing, time travel, benchmarking).

**✅ V1.0 - Testing Essentials:**

**1. Test Sources (Données Synthétiques):**
```python
# Random source pour tests
from cod3s_data.sources import RandomSource

random_temp = RandomSource(
    channel="sensors.temp",
    message_fn=lambda: Message(
        key="temp",
        value=random.uniform(20, 30),
        tags={"sensor": "test"}
    ),
    rate=10,    # 10 msg/s
    count=100   # Stop après 100 messages
)

# Sequence source (données prédéterminées)
from cod3s_data.sources import SequenceSource

test_data = [
    Message(key="temp", value=25),
    Message(key="temp", value=26),
    Message(key="temp", value=27),
]

seq = SequenceSource(
    channel="sensors.temp",
    messages=test_data,
    repeat=False
)
```

**2. Record/Replay (Capture Production):**
```python
# RECORD: Capturer données réelles
from cod3s_data.destinations import RecordDestination

recorder = RecordDestination(
    channel="sensors.**",
    output_file="/data/capture.jsonl"
)

# REPLAY: Rejouer données capturées
from cod3s_data.sources import ReplaySource

replay = ReplaySource(
    channel="sensors.temp",
    input_file="/data/capture.jsonl",
    mode="REALTIME",  # ou BATCH, TRANSPOSE
    filter={"channel": "sensors.temp"}
)
```

**3. Assertions (Vérifications):**
```python
# Assert destination - vérifie comportement
from cod3s_data.destinations import AssertDestination

assert_dest = AssertDestination(
    channel="sensors.temp.filtered",
    assertions=[
        lambda msg: msg.value > 20,
        lambda msg: msg.value < 100,
        lambda msg: "sensor" in msg.tags,
    ],
    on_failure="raise"  # ou "warn", "log"
)
```

**4. Collect Destination (Tests d'Intégration):**
```python
# Collect messages pour assertions
from cod3s_data.destinations import CollectDestination

collector = CollectDestination(channel="sensors.temp")

broker.start()
broker.wait_completion()

# Assertions
messages = collector.get_messages()
assert len(messages) == 10
assert all(msg.value > 20 for msg in messages)
```

**5. Integration Testing Pattern:**
```python
# test_viscosity_flow.py
def test_viscosity_computation():
    """Test end-to-end viscosity computation"""
    broker = Broker()

    # Test data
    temps = [Message(key="temp", value=v) for v in [220, 225, 230]]
    speeds = [Message(key="speed", value=v) for v in [50, 55, 60]]
    forces = [Message(key="force", value=v) for v in [100, 105, 110]]

    # Sources
    broker.add_source(SequenceSource("sensors.temp", temps))
    broker.add_source(SequenceSource("sensors.speed", speeds))
    broker.add_source(SequenceSource("sensors.force", forces))

    # Transformation
    broker.add_transformation(ViscosityComputer())

    # Collect results
    collector = CollectDestination("indicators.viscosity")
    broker.add_destination(collector)

    # Run
    broker.start()
    broker.wait_completion()

    # Assertions
    results = collector.get_messages()
    assert len(results) == 3
    assert all(r.key == "viscosity" for r in results)
```

**✅ V2.0 - Advanced Testing:**

**6. Chaos Testing (Fault Injection):**
```python
from cod3s_data.testing import ChaosSource

chaos = ChaosSource(
    base_source=mqtt_source,
    failures={
        "random_disconnect": 0.05,   # 5% déconnexions
        "delayed_message": 0.10,      # 10% retards
        "corrupted_message": 0.02,    # 2% corruptions
    }
)
```

**7. Time Travel (Simulation Temporelle):**
```python
from cod3s_data.testing import MockClock

with MockClock() as clock:
    broker.start()
    clock.advance(seconds=60)  # Avancer de 60s
    # Tester timeouts
```

**8. Performance Benchmarking:**
```python
from cod3s_data.testing import Benchmark

benchmark = Benchmark()
with benchmark.measure("throughput"):
    # Run workload
    broker.start()
    broker.wait_completion()

print(f"Throughput: {benchmark.throughput()} msg/s")
print(f"Latency p99: {benchmark.latency_p99()} ms")
```

**Comparaison:**

| Feature | V1.0 | V2.0 | Use Case |
|---------|------|------|----------|
| Test Sources | ✅ | ✅ | Données synthétiques |
| Record/Replay | ✅ | ✅ | Données réelles |
| Assertions | ✅ | ✅ | Vérifications |
| Collect Dest | ✅ | ✅ | Tests intégration |
| Chaos Testing | ❌ | ✅ | Résilience |
| Time Travel | ❌ | ✅ | Simulation temps |
| Benchmarking | ❌ | ✅ | Performance |

**CLI Testing:**
```bash
# Record production data
cod3s-data run config.yaml --record /data/capture.jsonl

# Replay for debugging
cod3s-data replay /data/capture.jsonl --mode REALTIME

# Validate config
cod3s-data validate config.yaml
```

**Rationale:**
- **V1.0 Essentials**: Outils de base pour développement et debugging
- **V1.0 Pratique**: Record/replay crucial pour debugger avec données réelles
- **V2.0 Advanced**: Chaos et benchmarking une fois framework stable
- **Progressif**: Apprendre avec v1.0, tester résilience en v2.0

---

## 📋 Questions Complètes ✅

**🎉 TOUTES LES QUESTIONS ONT ÉTÉ RÉPONDUES ! 🎉**

### Theme 4: Time Handling & Edge Cases
✅ Complete

### Theme 5: Default Component Catalog
✅ Complete

### Theme 6: Observability & Operations
✅ Complete

### Theme 7: Security & Data Integrity
✅ Complete

### Theme 8: Extensibility & Plugin Architecture
✅ Complete

### Theme 9: Batch Processing Modes Clarification (2 questions)
- [x] **Q9.1:** TRANSPOSE mode semantics (compression, timing details?) ✅
- [x] **Q9.2:** REALTIME mode clock drift (accuracy, pausability?) ✅

### Theme 10: Edge Cases & Ambiguity Resolution (5+ questions)
- [x] **Q10.1:** Empty channel behavior (lazy creation, pre-creation?) ✅
- [x] **Q10.2:** Circular dependencies (detect, allow, limit?) ✅
- [x] **Q10.3:** Large messages (limits on size, metadata count, nesting?) ✅
- [x] **Q10.4:** Null/missing values (allowed? distinguished?) ✅
- [x] **Q10.5:** Channel naming conventions (restrictions, patterns?) ✅

### Additional Open Questions (5 questions)
- [x] **Q11:** Framework scope - what's explicitly out of scope? ✅
- [x] **Q12:** Performance targets (still <100ms local, <1s distributed?) ✅
- [x] **Q13:** Deployment models (embedded, standalone, serverless, K8s?) ✅
- [x] **Q14:** Configuration management (code, files, env vars?) ✅
- [x] **Q15:** Testing & simulation (record/replay, chaos, assertions?) ✅

---

## 📊 Progress Summary

**🎉 INTERVIEW COMPLÈTE ! 🎉**

**Completed Themes:** 10/10 ✅
**Completed Questions:** 33/33 ✅
**Status:** Toutes les questions ont été répondues ! Prêt pour la rédaction de la spécification finale.

---

## 🎯 Key Architectural Decisions Made

1. **Delivery Guarantees:** Configurable per source (at-most-once default, at-least-once opt-in)
2. **Ordering:** No guarantees (timestamp-based ordering at application level)
3. **Error Handling:** Retry + DLQ pattern
4. **Backpressure:** Bounded buffers with drop-oldest strategy (configurable)
5. **Batch Control:** Full control API (cancel, pause/resume, progress)
6. **History Access:** Recent history by default (configurable: none/recent/all)

---

## 📝 Notes & Patterns

### Emerging Design Patterns:
- **Sensible defaults + Configurability:** Framework works out-of-box but flexible when needed
- **Phase 1 focus:** Core features solid, defer complex features (circuit breaker, backpressure) to Phase 2
- **Production-ready:** DLQ, retries, bounded buffers prevent data loss and OOM
- **Observability-first:** Progress monitoring, status checks, warnings on issues

### Deferred to Phase 2:
- Circuit breaker pattern
- Backpressure to sources
- Destination bypass on slow consumer
- Exactly-once delivery semantics

---

**Last Updated:** 2026-01-24 (after Q15 - INTERVIEW COMPLÈTE ! 🎉)
