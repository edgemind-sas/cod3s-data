# Testing Infrastructure and Patterns

**Document**: TECH-10-TESTING.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [12-TESTING](../FUNCTIONAL_SPECIFICATION/12-TESTING.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-09](TECH-09-SERIALIZATION.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-11 →](TECH-11-DEPLOYMENT.md) |

---

## Table of Contents

1. [Testing Framework Setup](#testing-framework-setup)
2. [Test Utilities](#test-utilities)
3. [Unit Testing](#unit-testing)
4. [Integration Testing](#integration-testing)
5. [Performance Testing](#performance-testing)

---

## Testing Framework Setup

### pytest Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # Auto-detect async tests
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--cov=cod3s_data",
    "--cov-report=html",
    "--cov-report=term-missing",
]
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (slower, full pipeline)",
    "benchmark: Performance benchmarks",
]
```

### Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "pytest-benchmark>=5.0",
    "pytest-timeout>=2.3",
]
```

---

## Test Utilities

### CollectDestination (Test Helper)

```python
# cod3s_data/testing.py

class CollectDestination(Destination):
    """
    Collect messages in memory for testing.

    Provides assertion helpers for test validation.
    """

    def __init__(self, broker: Broker, channel_pattern: str):
        super().__init__(broker, channel_pattern)
        self.messages: list[Message] = []
        self._lock = asyncio.Lock()

    async def write(self, message: Message):
        """Store message in memory"""
        async with self._lock:
            self.messages.append(message)

    def get_all(self) -> list[Message]:
        """Get all collected messages"""
        return self.messages.copy()

    def clear(self):
        """Clear collected messages"""
        self.messages.clear()

    # Assertion helpers

    def assert_count(self, expected: int):
        """Assert exact message count"""
        assert len(self.messages) == expected, \
            f"Expected {expected} messages, got {len(self.messages)}"

    def assert_min_count(self, minimum: int):
        """Assert minimum message count"""
        assert len(self.messages) >= minimum, \
            f"Expected at least {minimum} messages, got {len(self.messages)}"

    def assert_values(self, expected: list):
        """Assert message values match expected"""
        actual = [m.value for m in self.messages]
        assert actual == expected, \
            f"Expected values {expected}, got {actual}"

    def assert_keys(self, expected: list[str]):
        """Assert message keys match expected"""
        actual = [m.key for m in self.messages]
        assert actual == expected, \
            f"Expected keys {expected}, got {actual}"

    def assert_contains_value(self, value):
        """Assert at least one message has this value"""
        values = [m.value for m in self.messages]
        assert value in values, \
            f"Expected to find value {value}, got {values}"
```

---

## Unit Testing

### Test Broker

```python
# tests/unit/test_broker.py

import pytest
from datetime import datetime, timezone
from cod3s_data import InMemoryBroker, Message

@pytest.fixture
def broker():
    """Create broker for testing"""
    broker = InMemoryBroker()
    yield broker

@pytest.fixture
def sample_message():
    """Create sample message"""
    return Message(
        key="test",
        timestamp=datetime.now(timezone.utc),
        value=42,
        tags={}
    )

@pytest.mark.unit
@pytest.mark.asyncio
async def test_broker_publish(broker, sample_message):
    """Test basic message publishing"""
    await broker.start()

    result = await broker.publish("test.channel", sample_message)

    assert result.success
    assert result.subscriber_count == 0  # No subscribers yet

@pytest.mark.unit
@pytest.mark.asyncio
async def test_broker_subscribe(broker, sample_message):
    """Test subscription and notification"""
    await broker.start()

    received_messages = []

    async def callback(msg: Message):
        received_messages.append(msg)

    # Subscribe
    handle = broker.subscribe("test.channel", callback)

    # Publish
    await broker.publish("test.channel", sample_message)

    # Wait briefly for async callback
    await asyncio.sleep(0.01)

    # Verify
    assert len(received_messages) == 1
    assert received_messages[0].key == "test"
    assert received_messages[0].value == 42

@pytest.mark.unit
@pytest.mark.asyncio
async def test_wildcard_subscription(broker, sample_message):
    """Test wildcard pattern matching"""
    await broker.start()

    received = []
    async def callback(msg): received.append(msg)

    # Subscribe with wildcard
    broker.subscribe("test.**", callback)

    # Publish to matching channels
    await broker.publish("test.channel", sample_message)
    await broker.publish("test.channel.sub", sample_message)
    await broker.publish("other.channel", sample_message)  # Should not match

    await asyncio.sleep(0.01)

    assert len(received) == 2  # Only test.* channels
```

### Test Transformations

```python
# tests/unit/test_transformations.py

@pytest.mark.unit
@pytest.mark.asyncio
async def test_threshold_alert():
    """Test threshold alert transformation"""
    broker = InMemoryBroker()
    await broker.start()

    # Setup transformation
    transform = ThresholdAlert(
        broker=broker,
        input_channel="input",
        output_channel="alerts",
        threshold=50.0
    )
    await transform.start()

    # Setup collector
    collector = CollectDestination(broker, "alerts")
    await collector.start()

    # Send messages
    for value in [30, 60, 45, 75]:  # Two above threshold
        msg = Message(
            key="value",
            timestamp=datetime.now(timezone.utc),
            value=value,
            tags={}
        )
        await broker.publish("input", msg)

    await asyncio.sleep(0.1)  # Wait for processing

    # Verify only high values triggered alerts
    collector.assert_count(2)
```

---

## Integration Testing

### Full Pipeline Test

```python
# tests/integration/test_pipeline.py

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline():
    """Test complete source → transform → destination pipeline"""
    framework = Framework()

    # Source: sequence 0-99
    framework.add_source(SequenceSource(
        broker=framework.broker,
        channel="input",
        start=0,
        end=100,
        rate=1000  # Fast for testing
    ))

    # Transform: filter > 50
    framework.add_transformation(FilterTransform(
        broker=framework.broker,
        input_channel="input",
        output_channel="filtered",
        predicate=lambda msg: msg.value > 50
    ))

    # Destination: collect results
    collector = CollectDestination(framework.broker, "filtered")
    framework.add_destination(collector)

    # Run framework briefly
    await framework.start()
    await asyncio.sleep(0.2)  # Let it run
    await framework.stop()

    # Verify: should have 49 messages (51-99)
    collector.assert_count(49)
    collector.assert_min_count(49)  # At least 49

    # Verify all values > 50
    for msg in collector.get_all():
        assert msg.value > 50
```

### CSV Source Integration Test

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_csv_source():
    """Test CSV file reading"""
    import tempfile
    import polars as pl

    # Create test CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write("key,timestamp,value\n")
        f.write("temp,2024-01-15T10:00:00Z,42.5\n")
        f.write("temp,2024-01-15T10:00:01Z,43.2\n")
        f.write("temp,2024-01-15T10:00:02Z,41.8\n")
        csv_path = f.name

    try:
        broker = InMemoryBroker()
        await broker.start()

        # Source
        source = CSVSource(
            broker=broker,
            channel="test",
            file_path=csv_path
        )

        # Collector
        collector = CollectDestination(broker, "test")
        await collector.start()

        # Run
        await source.start()
        await asyncio.sleep(0.1)

        # Verify
        collector.assert_count(3)
        collector.assert_values([42.5, 43.2, 41.8])

    finally:
        import os
        os.unlink(csv_path)
```

---

## Performance Testing

### Broker Throughput Benchmark

```python
# tests/performance/test_benchmarks.py

@pytest.mark.benchmark
def test_broker_publish_throughput(benchmark):
    """Benchmark broker publish throughput"""
    broker = InMemoryBroker()
    asyncio.run(broker.start())

    message = Message(
        key="test",
        timestamp=datetime.now(timezone.utc),
        value=42,
        tags={}
    )

    async def publish_batch():
        for _ in range(1000):
            await broker.publish("test.channel", message)

    # Benchmark
    result = benchmark(lambda: asyncio.run(publish_batch()))

    # Assert throughput
    # Should handle 1000 messages in <100ms
    assert result.stats.mean < 0.1
```

### Message Serialization Benchmark

```python
@pytest.mark.benchmark
def test_serialization_throughput(benchmark):
    """Benchmark message serialization"""
    message = Message(
        key="temperature",
        timestamp=datetime.now(timezone.utc),
        value=42.5,
        tags={"sensor": "TH001", "location": "warehouse_A"}
    )

    def serialize_batch():
        for _ in range(1000):
            json_str = message.to_json()

    # Benchmark
    result = benchmark(serialize_batch)

    # Assert performance
    # Should serialize 1000 messages in <10ms
    assert result.stats.mean < 0.01
```

### Coverage Target

```bash
# Run tests with coverage
pytest --cov=cod3s_data --cov-report=term-missing

# Coverage target: 80%+
# Name                              Stmts   Miss  Cover
# -----------------------------------------------------
# cod3s_data/__init__.py               10      0   100%
# cod3s_data/broker.py                120      5    96%
# cod3s_data/sources.py               150     15    90%
# cod3s_data/transformations.py       100     10    90%
# cod3s_data/destinations.py           80      8    90%
# -----------------------------------------------------
# TOTAL                               460     38    92%
```

---

## References

- **Functional Spec**: [12-TESTING](../FUNCTIONAL_SPECIFICATION/12-TESTING.md)
- **QA Decisions**: [Q10.1-Q10.2](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-04-SOURCES-API](TECH-04-SOURCES-API.md) - SequenceSource for testing
  - [TECH-06-DESTINATIONS-API](TECH-06-DESTINATIONS-API.md) - CollectDestination

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-09](TECH-09-SERIALIZATION.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-11 →](TECH-11-DEPLOYMENT.md) |
