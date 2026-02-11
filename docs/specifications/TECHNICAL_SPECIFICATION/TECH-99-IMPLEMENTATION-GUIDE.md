# Implementation Guide

**Document**: TECH-99-IMPLEMENTATION-GUIDE.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Purpose**: Developer guide for implementing and extending COD3S Data Framework

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-12](TECH-12-API-REFERENCE.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [APPENDIX-A →](TECH-APPENDIX-A-DECISIONS.md) |

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Code Style and Standards](#code-style-and-standards)
3. [Creating Custom Sources](#creating-custom-sources)
4. [Creating Custom Transformations](#creating-custom-transformations)
5. [Creating Custom Destinations](#creating-custom-destinations)
6. [Contribution Guidelines](#contribution-guidelines)

---

## Getting Started

### Development Environment Setup

```bash
# Prerequisites: Python 3.12+
python --version  # Should be 3.12+

# Clone repository
git clone https://github.com/cod3s/cod3s-data.git
cd cod3s-data

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install in development mode
pip install -e ".[dev]"

# Verify installation
pytest tests/
mypy cod3s_data/
ruff check .
```

### Project Structure Tour

```
cod3s_data/
├── core/           # Core components (Message, Broker, buffers)
├── sources/        # Source implementations
├── transformations/  # Transformation implementations
├── destinations/   # Destination implementations
├── config/         # Configuration loading (Pydantic)
├── observability/  # Logging and metrics
└── testing/        # Test utilities

tests/
├── unit/          # Fast, isolated tests
├── integration/   # Full pipeline tests
└── performance/   # Benchmarks
```

---

## Code Style and Standards

### Type Hints (Required)

Use Python 3.12+ syntax for all public APIs:

```python
# Good (Python 3.12+)
def process(items: list[str]) -> dict[str, int]:
    ...

def get_value(key: str) -> str | None:
    ...

# Bad (old syntax)
from typing import List, Dict, Optional
def process(items: List[str]) -> Dict[str, int]:
    ...
```

### Docstrings (Google Style)

All public classes and methods must have docstrings:

```python
def calculate_average(values: list[float]) -> float:
    """
    Calculate the average of a list of values.

    Args:
        values: List of numeric values (must not be empty)

    Returns:
        Average of all values

    Raises:
        ValueError: If values list is empty

    Examples:
        >>> calculate_average([1, 2, 3, 4, 5])
        3.0
    """
    if not values:
        raise ValueError("Cannot calculate average of empty list")
    return sum(values) / len(values)
```

### Async/Await

All I/O operations must be async:

```python
# Good
async def fetch_data() -> list[Message]:
    async with aiofiles.open('data.txt') as f:
        content = await f.read()
    return parse(content)

# Bad
def fetch_data() -> list[Message]:
    with open('data.txt') as f:  # Blocking I/O
        content = f.read()
    return parse(content)
```

### Immutability

Prefer immutable data structures:

```python
# Good (Pydantic frozen model)
class Message(BaseModel):
    model_config = {"frozen": True}

# Good (dataclass frozen)
@dataclass(frozen=True)
class Config:
    value: int

# Avoid mutable defaults
def process(items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []  # Create new list
    return items
```

### Error Handling

Fail-fast for configuration, resilient for runtime:

```python
# Configuration: fail-fast
def __init__(self, config: dict):
    # Validate immediately, raise clear errors
    if "channel" not in config:
        raise ValueError("Configuration must include 'channel'")

# Runtime: resilient
async def process_message(self, message: Message):
    try:
        await self.write(message)
    except Exception as e:
        # Log error, don't crash framework
        logger.error("write_failed", error=str(e))
        # Optionally send to DLQ
```

---

## Creating Custom Sources

### Step 1: Inherit from Source Base Class

```python
from cod3s_data.sources import Source
from cod3s_data.core import Message
from datetime import datetime, timezone
from typing import AsyncIterator

class MyCustomSource(Source):
    """
    Custom source that reads from [external system].

    Explain what this source does and how to use it.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        # Add your custom parameters
        api_url: str,
        poll_interval: float = 60.0,
        **kwargs
    ):
        """
        Initialize custom source.

        Args:
            broker: Message broker
            channel: Target channel
            api_url: API endpoint URL
            poll_interval: Seconds between polls
        """
        super().__init__(broker, channel, **kwargs)
        self.api_url = api_url
        self.poll_interval = poll_interval

    async def produce(self) -> AsyncIterator[Message]:
        """
        Generate messages from external system.

        This method is called by the framework.
        Yield Message instances.
        """
        import aiohttp

        async with aiohttp.ClientSession() as session:
            while True:  # Run indefinitely (REALTIME mode)
                try:
                    # Fetch data from external system
                    async with session.get(self.api_url) as response:
                        data = await response.json()

                        # Convert to Message
                        yield Message(
                            key="api_data",
                            timestamp=datetime.now(timezone.utc),
                            value=data,
                            tags={"source": "custom_api"}
                        )

                except Exception as e:
                    # Log error, continue
                    self.logger.error("fetch_failed", error=str(e))

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
```

### Step 2: Add Tests

```python
# tests/unit/test_custom_source.py

@pytest.mark.unit
@pytest.mark.asyncio
async def test_custom_source():
    """Test custom source produces messages"""
    broker = InMemoryBroker()
    await broker.start()

    source = MyCustomSource(
        broker=broker,
        channel="test",
        api_url="http://example.com/api"
    )

    # Collect messages
    collector = CollectDestination(broker, "test")
    await collector.start()

    # Run source briefly
    source_task = asyncio.create_task(source.start())
    await asyncio.sleep(0.1)
    await source.stop()
    source_task.cancel()

    # Verify
    collector.assert_min_count(1)
```

### Step 3: Register in Factory (Optional)

```python
# cod3s_data/config/factory.py

def create_source(broker: Broker, config: SourceConfig) -> Source:
    if config.type == "my_custom":
        return MyCustomSource(
            broker=broker,
            channel=config.channel,
            api_url=config.api_url,
            poll_interval=config.poll_interval or 60.0
        )
    # ... other sources
```

---

## Creating Custom Transformations

### Stateless Transformation Example

```python
from cod3s_data.transformations import StatelessTransform

class UnitConverter(StatelessTransform):
    """
    Convert measurement units.

    Example: Fahrenheit to Celsius, meters to feet, etc.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        conversion_fn: Callable[[float], float],
        new_key: str | None = None
    ):
        """
        Initialize unit converter.

        Args:
            broker: Message broker
            input_channel: Input channel pattern
            output_channel: Output channel
            conversion_fn: Function to convert value
            new_key: Optional new key for output message
        """
        super().__init__(broker, input_channel, output_channel)
        self.conversion_fn = conversion_fn
        self.new_key = new_key

    async def transform(self, message: Message) -> list[Message]:
        """
        Convert message value.

        Args:
            message: Input message

        Returns:
            List with single converted message
        """
        converted_value = self.conversion_fn(float(message.value))

        return [Message(
            key=self.new_key or message.key,
            timestamp=message.timestamp,
            value=converted_value,
            tags=message.tags
        )]

# Usage
fahrenheit_to_celsius = UnitConverter(
    broker=broker,
    input_channel="sensors.temp.f",
    output_channel="sensors.temp.c",
    conversion_fn=lambda f: (f - 32) * 5/9,
    new_key="temperature_celsius"
)
```

### Stateful Transformation Example

```python
from cod3s_data.transformations import StatefulTransform
from cod3s_data.core.buffers import TimeWindow

class MovingAverage(StatefulTransform):
    """
    Calculate moving average over time window.
    """

    def __init__(
        self,
        broker: Broker,
        input_channel: str,
        output_channel: str,
        window_duration: timedelta
    ):
        super().__init__(broker, [input_channel], output_channel)
        self.window = TimeWindow(window_duration)

    async def update_state(self, message: Message):
        """Add message to window"""
        self.window.add(message)

    async def transform(self) -> list[Message]:
        """Calculate average of window"""
        messages = self.window.all()

        if not messages:
            return []

        values = [float(m.value) for m in messages]
        average = sum(values) / len(values)

        return [Message(
            key="moving_average",
            timestamp=datetime.now(timezone.utc),
            value=average,
            tags={"window_size": str(len(messages))}
        )]
```

---

## Creating Custom Destinations

### Example: Custom Database Destination

```python
from cod3s_data.destinations import Destination

class PostgreSQLDestination(Destination):
    """
    Write messages to PostgreSQL database.
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        connection_string: str,
        table_name: str,
        **kwargs
    ):
        """
        Initialize PostgreSQL destination.

        Args:
            broker: Message broker
            channel_pattern: Channel pattern to subscribe
            connection_string: PostgreSQL connection string
            table_name: Target table name
        """
        super().__init__(broker, channel_pattern, **kwargs)
        self.connection_string = connection_string
        self.table_name = table_name
        self._pool = None

    async def start(self):
        """Create connection pool"""
        import asyncpg

        self._pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=10
        )

        await super().start()

    async def write(self, message: Message):
        """
        Insert message into database.

        Raises:
            Exception: On database error (triggers retry)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self.table_name}
                (id, key, timestamp, value, tags)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(message.id),
                message.key,
                message.timestamp,
                json.dumps(message.value),
                json.dumps(message.tags)
            )

    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
```

---

## Contribution Guidelines

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-new-source

# Make changes, commit
git add cod3s_data/sources/my_source.py
git commit -m "Add MyCustomSource for [purpose]"

# Run tests and checks
pytest tests/
mypy cod3s_data/
ruff check .

# Push and create pull request
git push origin feature/my-new-source
```

### Pull Request Checklist

- [ ] Tests added for new functionality
- [ ] All tests passing (`pytest`)
- [ ] Type checking passing (`mypy cod3s_data/`)
- [ ] Linting passing (`ruff check .`)
- [ ] Docstrings added (Google style)
- [ ] Example usage provided
- [ ] Performance considered (benchmarks if relevant)

### Testing Requirements

- **Unit tests**: Required for all new components
- **Integration tests**: Required for new sources/destinations
- **Coverage**: Aim for 80%+ coverage of new code

### Documentation

- Update relevant TECH-XX docs if API changes
- Add examples to `examples/` directory
- Update README.md if adding user-facing feature

---

## Best Practices

### Performance

```python
# Good: Use async for I/O
async with aiofiles.open(path) as f:
    data = await f.read()

# Good: Batch operations
messages = [...]
for msg in messages:
    await broker.publish(channel, msg)

# Better: Pre-compile regex patterns
class Source:
    def __init__(self):
        self.pattern = re.compile(r'...')  # Compile once
```

### Error Handling

```python
# Good: Specific exceptions
try:
    await self.write(message)
except ConnectionError as e:
    logger.error("connection_failed", error=str(e))
    raise  # Triggers retry
except ValueError as e:
    logger.error("invalid_data", error=str(e))
    # Don't retry for bad data

# Good: Clear error messages
raise ValueError(
    f"Invalid channel pattern '{pattern}'. "
    "Pattern must not start with '_' (reserved)"
)
```

### Logging

```python
# Good: Structured logging
logger.info("source_starting",
           source=self.__class__.__name__,
           channel=self.channel,
           batch_mode=self.batch_mode.value)

# Good: Bind context
self.logger = logger.bind(
    component="MySource",
    channel=self.channel
)
```

---

## References

- **Technical Specs**: See individual TECH-XX documents for detailed specifications
- **API Reference**: [TECH-12-API-REFERENCE](TECH-12-API-REFERENCE.md)
- **Examples**: `examples/` directory in repository

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-12](TECH-12-API-REFERENCE.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [APPENDIX-A →](TECH-APPENDIX-A-DECISIONS.md) |
