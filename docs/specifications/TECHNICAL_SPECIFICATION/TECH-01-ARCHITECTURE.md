# Internal Architecture

**Document**: TECH-01-ARCHITECTURE.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [02-ARCHITECTURE](../FUNCTIONAL_SPECIFICATION/02-ARCHITECTURE.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-00](TECH-00-OVERVIEW.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-02 →](TECH-02-DATA-STRUCTURES.md) |

---

## Table of Contents

1. [Concurrency Model](#concurrency-model)
2. [Component Lifecycle](#component-lifecycle)
3. [Event Loop Coordination](#event-loop-coordination)
4. [Error Handling Architecture](#error-handling-architecture)
5. [Memory Management](#memory-management)
6. [Performance Optimization](#performance-optimization)
7. [Threading Model](#threading-model)
8. [Synchronization](#synchronization)

---

## Concurrency Model

### AsyncIO Foundation

**Design Decision**: Use Python's `asyncio` as the primary concurrency model for all I/O-bound operations.

**Rationale**: See [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-6-asyncio-for-concurrency)

### Event Loop Architecture

```python
import asyncio
from typing import AsyncIterator

class Framework:
    """
    Main framework coordinator using AsyncIO.

    Architecture:
    - Single event loop coordinates all components
    - Sources, broker, and destinations run as concurrent tasks
    - Non-blocking message passing
    """

    def __init__(self):
        self.broker: Broker = InMemoryBroker()
        self.sources: list[Source] = []
        self.transformations: list[Transformation] = []
        self.destinations: list[Destination] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def run(self):
        """
        Main entry point - coordinates all components.

        Lifecycle:
        1. Startup phase (validate, initialize)
        2. Running phase (concurrent execution)
        3. Shutdown phase (graceful cleanup)
        """
        try:
            # Phase 1: Startup
            await self._startup()

            # Phase 2: Run all components concurrently
            await self._run_components()

        except KeyboardInterrupt:
            logger.info("shutdown_requested", reason="keyboard_interrupt")
        except Exception as e:
            logger.error("framework_error", error=str(e), exc_info=True)
            raise
        finally:
            # Phase 3: Shutdown
            await self._shutdown()

    async def _startup(self):
        """
        Startup phase: validate configuration, initialize components.

        Fail-fast: Any error here terminates the framework.
        """
        logger.info("framework_starting")

        # Validate configuration (Pydantic will raise ValidationError if invalid)
        # This is intentionally synchronous - fail fast on config errors

        # Initialize broker
        await self.broker.start()
        logger.info("broker_started")

        # Subscribe transformations to their input channels
        for transform in self.transformations:
            await transform.start()
            logger.info("transformation_started", transform=transform.__class__.__name__)

        # Subscribe destinations to their channels
        for dest in self.destinations:
            await dest.start()
            logger.info("destination_started", destination=dest.__class__.__name__)

        logger.info("framework_ready",
                   source_count=len(self.sources),
                   transform_count=len(self.transformations),
                   dest_count=len(self.destinations))

    async def _run_components(self):
        """
        Running phase: execute all sources concurrently.

        Each source runs as an independent async task.
        Transformations and destinations react to messages via subscriptions.
        """
        self._running = True

        # Start all sources concurrently
        source_tasks = [
            asyncio.create_task(self._run_source(source))
            for source in self.sources
        ]

        # Wait for all sources to complete or shutdown signal
        await asyncio.gather(
            *source_tasks,
            self._shutdown_event.wait(),
            return_exceptions=True  # Don't crash on individual source failure
        )

    async def _run_source(self, source: Source):
        """
        Run a single source.

        Errors are caught and logged, don't crash framework.
        """
        try:
            logger.info("source_starting", source=source.__class__.__name__)
            await source.start()
            logger.info("source_completed", source=source.__class__.__name__)
        except Exception as e:
            logger.error("source_failed",
                        source=source.__class__.__name__,
                        error=str(e),
                        exc_info=True)
            # Don't re-raise: other sources should continue

    async def _shutdown(self):
        """
        Shutdown phase: graceful cleanup of all components.

        Order:
        1. Stop sources (no new messages)
        2. Drain broker (process pending messages)
        3. Close destinations (flush buffers)
        """
        logger.info("framework_shutting_down")

        # 1. Stop all sources
        for source in self.sources:
            try:
                await source.stop()
            except Exception as e:
                logger.warning("source_stop_failed",
                              source=source.__class__.__name__,
                              error=str(e))

        # 2. Allow broker to drain pending messages
        # Wait a short time for in-flight messages to complete
        await asyncio.sleep(0.1)

        # 3. Close all destinations (flush buffers)
        for dest in self.destinations:
            try:
                await dest.close()
            except Exception as e:
                logger.warning("destination_close_failed",
                              destination=dest.__class__.__name__,
                              error=str(e))

        logger.info("framework_stopped")

    async def stop(self):
        """
        Request graceful shutdown.

        Can be called from signal handlers or external control.
        """
        logger.info("shutdown_requested")
        self._shutdown_event.set()
```

### Concurrency Characteristics

| Operation | Concurrency Model | Rationale |
|-----------|------------------|-----------|
| **Source execution** | Concurrent async tasks | Each source runs independently |
| **Message publishing** | Non-blocking (async) | Don't wait for subscribers |
| **Subscription callbacks** | Concurrent async tasks | Parallel processing of messages |
| **Destination writes** | Buffered + async | Batch writes, don't block publishers |
| **Transformations** | Async callbacks | React to messages without blocking |

### Performance Implications

**Throughput**: Single event loop can handle 10,000+ async operations concurrently
- **Bottleneck**: CPU-bound transformations (solution: ProcessPoolExecutor)
- **Not bottleneck**: I/O operations (disk, network)

**Latency**: Message publish to subscriber callback < 1ms (typical)
- **Fast path**: Direct callback invocation (no queue)
- **Slow path**: Buffered destinations (configurable buffer size)

---

## Component Lifecycle

### Lifecycle States

Each component progresses through these states:

```
CREATED → STARTING → RUNNING → STOPPING → STOPPED
```

### State Definitions

| State | Description | Operations Allowed |
|-------|-------------|-------------------|
| **CREATED** | Component instantiated | Configuration only |
| **STARTING** | Initialization in progress | Resource allocation |
| **RUNNING** | Normal operation | Message processing |
| **STOPPING** | Graceful shutdown initiated | Finish pending, reject new |
| **STOPPED** | Fully terminated | None (cleanup complete) |

### Lifecycle Implementation

```python
from enum import Enum
from abc import ABC, abstractmethod

class ComponentState(Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"

class Component(ABC):
    """
    Base class for all framework components.

    Enforces lifecycle state management.
    """

    def __init__(self):
        self._state = ComponentState.CREATED
        self._state_lock = asyncio.Lock()

    @property
    def state(self) -> ComponentState:
        return self._state

    async def start(self):
        """
        Transition: CREATED → STARTING → RUNNING

        Subclasses implement _on_start() for custom initialization.
        """
        async with self._state_lock:
            if self._state != ComponentState.CREATED:
                raise RuntimeError(f"Cannot start from state {self._state}")

            self._state = ComponentState.STARTING
            logger.info("component_starting", component=self.__class__.__name__)

        try:
            await self._on_start()

            async with self._state_lock:
                self._state = ComponentState.RUNNING
                logger.info("component_running", component=self.__class__.__name__)

        except Exception as e:
            async with self._state_lock:
                self._state = ComponentState.STOPPED
            logger.error("component_start_failed",
                        component=self.__class__.__name__,
                        error=str(e))
            raise

    async def stop(self):
        """
        Transition: RUNNING → STOPPING → STOPPED

        Subclasses implement _on_stop() for custom cleanup.
        """
        async with self._state_lock:
            if self._state not in (ComponentState.RUNNING, ComponentState.STARTING):
                logger.warning("stop_called_in_invalid_state",
                              component=self.__class__.__name__,
                              state=self._state.value)
                return

            self._state = ComponentState.STOPPING
            logger.info("component_stopping", component=self.__class__.__name__)

        try:
            await self._on_stop()

            async with self._state_lock:
                self._state = ComponentState.STOPPED
                logger.info("component_stopped", component=self.__class__.__name__)

        except Exception as e:
            logger.error("component_stop_failed",
                        component=self.__class__.__name__,
                        error=str(e))
            # Still transition to STOPPED even on error
            async with self._state_lock:
                self._state = ComponentState.STOPPED

    @abstractmethod
    async def _on_start(self):
        """Subclass-specific startup logic"""
        pass

    @abstractmethod
    async def _on_stop(self):
        """Subclass-specific cleanup logic"""
        pass
```

### Async Context Manager Pattern

**Recommended usage**:

```python
async def main():
    framework = Framework.from_yaml("pipeline.yaml")

    async with framework:
        # Framework runs until KeyboardInterrupt or completion
        await asyncio.Future()  # Run forever

# Context manager handles startup/shutdown
class Framework:
    async def __aenter__(self):
        await self._startup()
        # Start components in background
        self._run_task = asyncio.create_task(self._run_components())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._shutdown()
        if self._run_task:
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
```

---

## Event Loop Coordination

### Single Event Loop Design

**Architecture**: All components share a single `asyncio` event loop.

```python
# Main event loop
asyncio.run(framework.run())

# All async operations use the same loop
loop = asyncio.get_running_loop()
```

**Benefits**:
- Simpler coordination (no IPC needed)
- Lower overhead (no thread/process switching)
- Easier debugging (single thread)

**Trade-offs**:
- CPU-bound work blocks loop → Use ProcessPoolExecutor

### Task Management

```python
class Framework:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def _create_task(self, coro) -> asyncio.Task:
        """
        Create and track an async task.

        Prevents tasks from being garbage collected.
        """
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _wait_all_tasks(self, timeout: float = 5.0):
        """
        Wait for all tracked tasks to complete.

        Used during shutdown to ensure clean completion.
        """
        if not self._tasks:
            return

        done, pending = await asyncio.wait(
            self._tasks,
            timeout=timeout,
            return_when=asyncio.ALL_COMPLETED
        )

        if pending:
            logger.warning("tasks_still_pending",
                          count=len(pending),
                          tasks=[t.get_name() for t in pending])

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # Wait for cancellation
            await asyncio.wait(pending, timeout=1.0)
```

### CPU-Bound Processing

For CPU-intensive transformations, use `ProcessPoolExecutor`:

```python
import concurrent.futures
from functools import partial

class CPUBoundTransform(StatelessTransform):
    """
    Transformation that offloads CPU work to separate process.

    Use for: complex calculations, ML inference, heavy data processing.
    """

    def __init__(self, broker, input_channel, output_channel, workers: int = 4):
        super().__init__(broker, input_channel, output_channel)
        self._executor = concurrent.futures.ProcessPoolExecutor(max_workers=workers)

    async def transform(self, message: Message) -> list[Message]:
        """
        Offload heavy computation to separate process.

        Event loop continues processing other messages.
        """
        loop = asyncio.get_running_loop()

        # Run in process pool (doesn't block event loop)
        result = await loop.run_in_executor(
            self._executor,
            self._cpu_heavy_work,
            message.value
        )

        return [Message(
            key=message.key,
            timestamp=message.timestamp,
            value=result,
            tags=message.tags
        )]

    @staticmethod
    def _cpu_heavy_work(value: any) -> any:
        """
        CPU-intensive function (runs in separate process).

        Must be static or top-level function (for pickle serialization).
        """
        # Heavy computation here
        import time
        time.sleep(0.1)  # Simulate work
        return value * 2

    async def _on_stop(self):
        """Cleanup: shutdown process pool"""
        self._executor.shutdown(wait=True)
        await super()._on_stop()
```

---

## Error Handling Architecture

### Error Handling Strategy

**Philosophy**: Fail-fast for configuration, resilient for runtime.

See [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-10-fail-fast-vs-resilient)

### Configuration Errors (Fail-Fast)

```python
from pydantic import ValidationError

def main():
    try:
        # Load configuration
        config = PipelineConfig.from_yaml("pipeline.yaml")
        framework = Framework(config)

    except ValidationError as e:
        # Pydantic provides clear, actionable errors
        print(f"Configuration error:\n{e}")
        sys.exit(1)

    except FileNotFoundError as e:
        print(f"Configuration file not found: {e}")
        sys.exit(1)

    # If we get here, configuration is valid
    asyncio.run(framework.run())
```

**Pydantic Error Example**:
```
Configuration error:
2 validation errors for PipelineConfig
sources.0.channel
  field required (type=value_error.missing)
sources.1.file_path
  File does not exist: '/nonexistent/file.csv' (type=value_error)
```

### Runtime Errors (Resilient)

```python
class Destination(Component):
    async def _handle_message(self, message: Message):
        """
        Process message with error isolation.

        Errors don't crash the framework or affect other messages.
        """
        try:
            await self.write(message)

            # Emit success metric
            await self.broker.publish(
                f"_metrics.destination.{self.name}.success",
                MetricMessage(key="write_success", value=1, ...)
            )

        except Exception as e:
            # Log error with context
            logger.error("destination_write_failed",
                        destination=self.name,
                        channel=message.key,
                        message_id=str(message.id),
                        error=str(e),
                        exc_info=True)

            # Emit failure metric
            await self.broker.publish(
                f"_metrics.destination.{self.name}.failure",
                MetricMessage(key="write_failure", value=1, ...)
            )

            # Send to DLQ if configured
            if self.dlq_channel:
                try:
                    await self.broker.publish(self.dlq_channel, message)
                except Exception as dlq_error:
                    logger.error("dlq_publish_failed", error=str(dlq_error))

            # Increment retry counter
            message._retry_count += 1

            # Retry if under limit
            if message._retry_count <= self.max_retries:
                backoff = self._calculate_backoff(message._retry_count)
                await asyncio.sleep(backoff)
                await self._handle_message(message)  # Retry
```

### Error Isolation

**Design Principle**: Component failures don't cascade.

```
Source 1 crashes  →  Sources 2, 3 continue
Dest 1 fails      →  Dest 2, 3 continue
Transform errors  →  Message goes to DLQ, processing continues
```

**Implementation**:
- Each source runs in separate task (exceptions caught)
- Subscription callbacks wrapped in try/except
- Destinations buffer messages (failure doesn't block publisher)

---

## Memory Management

### Memory Allocation Strategy

**Goal**: Bounded memory usage, predictable behavior under load.

### Bounded Buffers

```python
class HistoryBuffer:
    """
    Fixed-size ring buffer for channel history.

    Memory: O(max_size * message_size)
    Automatically evicts oldest when full.
    """

    def __init__(self, max_size: int = 100):
        self._buffer: deque[Message] = deque(maxlen=max_size)
        # deque with maxlen automatically discards oldest

    def add(self, message: Message):
        """O(1) append, auto-evicts if full"""
        self._buffer.append(message)

class DestinationBuffer:
    """
    Bounded queue for destination messages.

    Memory: O(max_size * message_size)
    Configurable overflow strategy.
    """

    def __init__(self, max_size: int, overflow: OverflowStrategy):
        self._queue = asyncio.Queue(maxsize=max_size)
        self._overflow = overflow

    async def put(self, message: Message):
        """Handle overflow according to strategy"""
        # See TECH-02-DATA-STRUCTURES for implementation
        ...
```

### Memory Limits

| Component | Memory Bound | Configuration |
|-----------|--------------|---------------|
| **History buffer** | `max_size * ~1KB` per channel | `history_size=100` (default) |
| **Destination buffer** | `buffer_size * ~1KB` | `buffer_size=1000` (default) |
| **Subscriptions** | `O(num_patterns)` | Unlimited (typically <1000) |
| **In-flight messages** | `O(num_subscribers)` | Unbounded (relies on async) |

**Total memory estimate** (typical):
```
10 channels * 100 history * 1KB     = 1 MB
5 destinations * 1000 buffer * 1KB  = 5 MB
Subscriptions + overhead            = 1 MB
--------------------------------
Total framework overhead:           ≈ 7 MB
```

### Garbage Collection

**Immutable messages** → No circular references → Efficient GC

```python
class Message(BaseModel):
    model_config = {"frozen": True}  # Immutable

# Messages are GC'd when no longer referenced
# No manual cleanup needed
```

---

## Performance Optimization

### Optimization Strategies

#### 1. Fast Path for Exact Channel Matches

```python
class SubscriptionRegistry:
    def match_channel(self, channel: str) -> list[Callback]:
        """
        O(1) for exact matches (common case).
        O(n) for wildcards (rare case).
        """
        callbacks = []

        # Fast path: exact match (O(1))
        if channel in self._exact_matches:
            callbacks.extend(self._exact_matches[channel])
            return callbacks  # Skip wildcard checks if exact match found

        # Slow path: wildcard matching (O(n))
        for pattern, cbs in self._wildcards.items():
            if pattern.match(channel):
                callbacks.extend(cbs)

        return callbacks
```

#### 2. Pre-compiled Regex Patterns

```python
def add_subscription(self, pattern: str, callback: Callback):
    """Compile regex once at subscription time"""
    if '*' in pattern:
        regex = self._compile_pattern(pattern)  # Compile once
        self._wildcards[regex] = callback
    else:
        self._exact_matches[pattern] = callback
```

#### 3. Message Passing (No Copy)

```python
# Messages are immutable → safe to share references
await broker.publish(channel, message)  # No copy

# Subscribers receive same object
async def callback(message: Message):
    # Same message object, no deep copy
    ...
```

#### 4. Async Batching for Destinations

```python
class FileDestination(Destination):
    async def _writer_loop(self):
        """Batch writes to reduce I/O overhead"""
        batch = []

        while self._running:
            try:
                # Wait up to 100ms for messages
                message = await asyncio.wait_for(
                    self.buffer.get(),
                    timeout=0.1
                )
                batch.append(message)

                # Flush when batch full or timeout
                if len(batch) >= self.batch_size:
                    await self._flush_batch(batch)
                    batch = []

            except asyncio.TimeoutError:
                # Timeout: flush partial batch
                if batch:
                    await self._flush_batch(batch)
                    batch = []

    async def _flush_batch(self, batch: list[Message]):
        """Write entire batch in one I/O operation"""
        lines = [msg.model_dump_json() for msg in batch]
        async with aiofiles.open(self.file_path, 'a') as f:
            await f.write('\n'.join(lines) + '\n')
```

### Performance Targets

| Operation | Target | Typical |
|-----------|--------|---------|
| **Publish** (exact match) | < 0.1 ms | 0.05 ms |
| **Publish** (wildcard) | < 1 ms | 0.5 ms |
| **Subscription callback** | < 0.1 ms | 0.02 ms |
| **Message throughput** | > 10,000 msgs/sec | 50,000 msgs/sec |
| **Memory overhead** | < 10 MB | 7 MB |

---

## Threading Model

### Single-Threaded Async

**Default**: All components run in a single thread using `asyncio`.

```python
# All this runs in one thread
asyncio.run(framework.run())
```

**No threading needed for**:
- I/O-bound sources (file, network)
- Broker (in-memory pub/sub)
- I/O-bound destinations

### When to Use Threads

**Rare cases** where threading is appropriate:

1. **Blocking I/O libraries** (no async support)
2. **Legacy integrations** (thread-based APIs)

**Use `run_in_executor`**:

```python
import concurrent.futures

class BlockingSource(Source):
    """Source using blocking I/O library"""

    def __init__(self, broker, channel):
        super().__init__(broker, channel)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    async def produce(self) -> AsyncIterator[Message]:
        loop = asyncio.get_running_loop()

        while self._running:
            # Run blocking call in thread pool
            data = await loop.run_in_executor(
                self._executor,
                self._blocking_read  # Blocking function
            )

            yield Message(
                key="data",
                timestamp=datetime.now(timezone.utc),
                value=data,
                tags={}
            )

    def _blocking_read(self):
        """Blocking I/O (runs in separate thread)"""
        import time
        time.sleep(1)  # Simulate blocking I/O
        return {"value": 42}
```

---

## Synchronization

### No Locks Needed (Mostly)

**AsyncIO advantage**: Cooperative multitasking → no race conditions in single task.

```python
# No lock needed - single task execution
async def handle_message(message: Message):
    self.counter += 1  # Safe: no concurrent access
    await self.process(message)
```

### When Locks Are Needed

**Rare cases**:

1. **Shared state across tasks**
2. **Component lifecycle state**

```python
class Component:
    def __init__(self):
        self._state_lock = asyncio.Lock()  # Protect state transitions

    async def start(self):
        async with self._state_lock:
            if self._state != ComponentState.CREATED:
                raise RuntimeError(f"Invalid state: {self._state}")
            self._state = ComponentState.STARTING
        # Lock released, state transition complete
```

### Lock-Free Patterns

**Prefer immutability and message passing**:

```python
# Good: Immutable message, no lock needed
message = Message(key="temp", value=42, timestamp=now(), tags={})
await broker.publish("sensors.temp", message)

# Good: Actor-like pattern (message passing)
class Aggregator:
    async def handle_message(self, message: Message):
        # Process message, no shared state with other messages
        self.state[message.key] = message.value
        # Each message processed sequentially in this callback
```

---

## References

- **Functional Spec**: [02-ARCHITECTURE](../FUNCTIONAL_SPECIFICATION/02-ARCHITECTURE.md)
- **QA Decisions**: [QA_SPEC Q1.1](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md) (Concurrency)
- **Related Tech Specs**:
  - [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) (Message, buffers)
  - [TECH-03-BROKER-API](TECH-03-BROKER-API.md) (Pub/sub implementation)

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-00](TECH-00-OVERVIEW.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-02 →](TECH-02-DATA-STRUCTURES.md) |
