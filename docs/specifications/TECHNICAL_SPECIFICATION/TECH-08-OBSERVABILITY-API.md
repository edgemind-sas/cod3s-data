# Observability Implementation

**Document**: TECH-08-OBSERVABILITY-API.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [10-OBSERVABILITY](../FUNCTIONAL_SPECIFICATION/10-OBSERVABILITY.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-07](TECH-07-CONFIGURATION-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-09 →](TECH-09-SERIALIZATION.md) |

---

## Table of Contents

1. [Structured Logging](#structured-logging)
2. [Metrics as Messages](#metrics-as-messages)
3. [Trace ID Propagation](#trace-id-propagation)
4. [Debug Mode](#debug-mode)

---

## Structured Logging

### structlog Configuration

```python
import structlog
import sys

def configure_logging(debug: bool = False):
    """
    Configure structured logging with structlog.

    Args:
        debug: Enable debug-level logging
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

# Usage
configure_logging(debug=True)
logger = structlog.get_logger()
```

### Logging Examples

```python
# Simple log
logger.info("framework_starting")

# With context
logger.info("message_published",
           channel="sensors.temp",
           message_id="a3b7c9d1-...",
           subscriber_count=3)

# Error logging
try:
    await some_operation()
except Exception as e:
    logger.error("operation_failed",
                error=str(e),
                exc_info=True)  # Include stack trace

# Bind context to logger
component_logger = logger.bind(
    component="CSVSource",
    channel="sensors.raw"
)
component_logger.info("source_starting")  # Includes component and channel
```

### Log Output (JSON)

```json
{
  "event": "message_published",
  "channel": "sensors.temp",
  "message_id": "a3b7c9d1-e4f6-4a8b-9c1d-e2f3a4b5c6d7",
  "subscriber_count": 3,
  "level": "info",
  "timestamp": "2026-01-24T10:30:45.123456Z"
}

{
  "event": "operation_failed",
  "error": "Connection refused",
  "exception": "Traceback (most recent call last)...",
  "level": "error",
  "timestamp": "2026-01-24T10:30:46.123456Z"
}
```

---

## Metrics as Messages

### Metric Channels

All framework components emit metrics to reserved `_metrics.*` channels:

| Channel Pattern | Metric | Description |
|----------------|--------|-------------|
| `_metrics.broker.published` | messages_published | Total messages published |
| `_metrics.broker.subscriptions` | subscription_added | Subscription registered |
| `_metrics.broker.subscriptions` | subscription_removed | Subscription removed |
| `_metrics.broker.errors` | callback_error | Subscriber callback failed |
| `_metrics.source.{name}.produced` | messages_produced | Messages from source |
| `_metrics.destination.{name}.success` | write_success | Successful writes |
| `_metrics.destination.{name}.failure` | write_failure | Failed writes |

### Metric Message Format

```python
@dataclass
class MetricMessage:
    """Metric represented as a standard message"""
    key: str              # Metric name
    timestamp: datetime   # When metric was recorded
    value: float          # Metric value
    tags: dict[str, str]  # Component, type, etc.
    id: UUID

# Example metric
metric = Message(
    key="messages_published",
    timestamp=datetime.now(timezone.utc),
    value=1,
    tags={"channel": "sensors.temp", "component": "broker"}
)
```

### Subscribe to Metrics

```python
# Monitor all metrics
async def metrics_handler(msg: Message):
    print(f"Metric: {msg.key} = {msg.value} {msg.tags}")

broker.subscribe("_metrics.**", metrics_handler)

# Monitor specific component
broker.subscribe("_metrics.broker.**", broker_metrics_handler)

# Monitor failures
async def failure_handler(msg: Message):
    logger.warning("failure_detected",
                  key=msg.key,
                  value=msg.value,
                  tags=msg.tags)

broker.subscribe("_metrics.**.failure", failure_handler)
```

### Metric Aggregation Example

```python
class MetricsAggregator:
    """
    Aggregate metrics and expose via HTTP.

    Example observability component.
    """

    def __init__(self, broker: Broker):
        self.broker = broker
        self.metrics: dict[str, float] = {}

    async def start(self):
        """Subscribe to all metrics"""
        self.broker.subscribe("_metrics.**", self._handle_metric)

    async def _handle_metric(self, message: Message):
        """Aggregate metric values"""
        metric_name = f"{message.tags.get('component', 'unknown')}.{message.key}"
        self.metrics[metric_name] = message.value

    def get_metrics(self) -> dict[str, float]:
        """Get current metric values"""
        return self.metrics.copy()

    def prometheus_format(self) -> str:
        """Export metrics in Prometheus format"""
        lines = []
        for name, value in self.metrics.items():
            # Prometheus format: metric_name value
            lines.append(f"{name.replace('.', '_')} {value}")
        return "\n".join(lines)
```

---

## Trace ID Propagation

### Trace ID in Messages

```python
class Message(BaseModel):
    # ... public fields ...

    # Internal tracing (excluded from serialization)
    _trace_id: str | None = Field(default=None, exclude=True)

# Generate trace ID for message
import uuid

message = Message(
    key="temperature",
    timestamp=datetime.now(timezone.utc),
    value=42.5,
    tags={}
)
message._trace_id = str(uuid.uuid4())

# Propagate trace ID through transformations
class MyTransform(StatelessTransform):
    async def transform(self, message: Message) -> list[Message]:
        result = Message(
            key="transformed",
            timestamp=message.timestamp,
            value=message.value * 2,
            tags=message.tags
        )
        # Propagate trace ID
        result._trace_id = message._trace_id
        return [result]
```

### Trace ID in Logs

```python
# Bind trace ID to logger context
logger = structlog.get_logger()

async def handle_message(message: Message):
    # Bind trace ID to logger
    log = logger.bind(trace_id=message._trace_id or "none")

    log.info("processing_message", key=message.key)

    # All subsequent logs include trace_id
    log.debug("calling_transformation")
    log.info("processing_complete")

# Log output
{
  "event": "processing_message",
  "key": "temperature",
  "trace_id": "a3b7c9d1-e4f6-4a8b-9c1d-e2f3a4b5c6d7",
  "level": "info"
}
```

### Distributed Tracing (V2.0)

```python
# Future: OpenTelemetry integration
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def handle_message(message: Message):
    with tracer.start_as_current_span("handle_message") as span:
        span.set_attribute("message.key", message.key)
        span.set_attribute("message.id", str(message.id))

        await process_message(message)
```

---

## Debug Mode

### Enable Debug Mode

```python
# Framework-level debug
framework = Framework(debug=True)

# Enables:
# - DEBUG-level logging
# - Verbose message tracing
# - Performance timing logs
# - Subscription matching details
```

### Debug Logging Output

```python
class Framework:
    def __init__(self, debug: bool = False):
        self.debug = debug

        # Configure logging
        configure_logging(debug=debug)

        if debug:
            logger.warning("debug_mode_enabled",
                          warning="Performance may be reduced")

    async def _publish_message(self, message: Message):
        if self.debug:
            start = time.perf_counter()

        await self.broker.publish(channel, message)

        if self.debug:
            elapsed = time.perf_counter() - start
            logger.debug("publish_timing",
                        channel=channel,
                        elapsed_ms=elapsed * 1000)
```

### Verbose Subscription Matching

```python
class SubscriptionRegistry:
    def match_channel(self, channel: str) -> list[Callback]:
        if self.debug:
            logger.debug("matching_channel",
                        channel=channel,
                        exact_patterns=len(self._exact_matches),
                        wildcard_patterns=len(self._single_wildcards))

        callbacks = []

        # Exact match
        if channel in self._exact_matches:
            matched = self._exact_matches[channel]
            if self.debug:
                logger.debug("exact_match_found",
                            channel=channel,
                            callback_count=len(matched))
            callbacks.extend(matched)

        # Wildcard matching
        for pattern, cbs in self._single_wildcards.items():
            if pattern.fullmatch(channel):
                if self.debug:
                    logger.debug("wildcard_match",
                                channel=channel,
                                pattern=pattern.pattern,
                                callback_count=len(cbs))
                callbacks.extend(cbs)

        return callbacks
```

### Performance Profiling

```python
# Built-in performance metrics (debug mode)
class Source:
    async def _publish_message(self, message: Message):
        if self.debug:
            start = time.perf_counter()

        await self.broker.publish(self.channel, message)

        if self.debug:
            elapsed = time.perf_counter() - start

            # Emit performance metric
            await self.broker.publish(
                "_metrics.source.performance",
                Message(
                    key="publish_latency",
                    timestamp=datetime.now(timezone.utc),
                    value=elapsed * 1000,  # ms
                    tags={"source": self.__class__.__name__}
                )
            )
```

---

## References

- **Functional Spec**: [10-OBSERVABILITY](../FUNCTIONAL_SPECIFICATION/10-OBSERVABILITY.md)
- **QA Decisions**: [Q8.1-Q8.2](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) - structlog in technology stack
  - [TECH-03-BROKER-API](TECH-03-BROKER-API.md) - Metrics emission

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-07](TECH-07-CONFIGURATION-API.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-09 →](TECH-09-SERIALIZATION.md) |
