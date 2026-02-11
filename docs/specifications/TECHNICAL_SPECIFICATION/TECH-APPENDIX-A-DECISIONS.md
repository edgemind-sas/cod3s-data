# Technical Design Decisions Log

**Document**: TECH-APPENDIX-A-DECISIONS.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Purpose**: Record of all major technical design decisions for COD3S Data Framework

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-99](TECH-99-IMPLEMENTATION-GUIDE.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-00 →](TECH-00-OVERVIEW.md) |

---

## Table of Contents

1. [Language and Runtime](#decision-1-python-312-as-minimum-version)
2. [Data Validation and Models](#decision-2-pydantic-v2-for-data-models)
3. [Data Processing](#decision-3-polars-primary-with-pandas-fallback)
4. [Serialization](#decision-4-pydantic-json-default-msgspec-optional)
5. [Logging](#decision-5-structlog-for-structured-logging)
6. [Concurrency Model](#decision-6-asyncio-for-concurrency)
7. [Dependency Philosophy](#decision-7-leverage-proven-libraries)
8. [Subscription Matching](#decision-8-hybrid-subscription-registry)
9. [Message Immutability](#decision-9-immutable-messages)
10. [Error Handling Strategy](#decision-10-fail-fast-vs-resilient)

---

## Decision 1: Python 3.12+ as Minimum Version

### Question
What minimum Python version should we target? Should we support older versions (3.9, 3.10, 3.11) or require the latest stable?

### Decision
Require **Python 3.12+** as the minimum supported version.

### Rationale

1. **Performance Improvements**: Python 3.12 is 10-30% faster than 3.9 in many workloads
   - Improved bytecode compiler
   - Faster asyncio implementation
   - Better memory allocation

2. **Modern Type Hints**:
   - PEP 695: Type parameter syntax (`class Stack[T]:`)
   - PEP 692: TypedDict with `Unpack`
   - Better generic support without `from typing import`
   - Simpler syntax: `list[str]` instead of `List[str]`, `str | None` instead of `Optional[str]`

3. **Better Error Messages**:
   - Enhanced traceback formatting
   - More helpful exception messages
   - Improved debugging experience

4. **Industry Standard**:
   - Python 3.12 released October 2023 (stable for 2+ years by 2026)
   - Most data engineering projects targeting 3.11+
   - Docker base images readily available

5. **No Legacy Baggage**:
   - Don't need to maintain compatibility shims
   - Can use modern idioms throughout
   - Cleaner, more maintainable codebase

### Alternatives Considered

1. **Python 3.9+** (broader compatibility)
   - **Why rejected**: Older performance characteristics, missing modern type hint features
   - Would require `from typing import List, Optional` everywhere
   - Slower asyncio implementation
   - Limited upside for 2026 deployment

2. **Python 3.11+** (balance)
   - **Why rejected**: 3.12 offers significant improvements with minimal adoption barrier
   - 3.12 is stable and widely available by 2026
   - Small version bump for better developer experience

3. **Python 3.13+** (bleeding edge)
   - **Why rejected**: Too new (October 2024 release), less stable
   - Fewer production deployments
   - Docker images less mature
   - No compelling features for this use case

### Trade-offs

**Advantages**:
- Best performance and developer experience
- Modern, clean codebase
- Future-proof for next 3-5 years
- No legacy compatibility code

**Disadvantages**:
- May exclude users on older systems
- Requires 3.12 in deployment environments
- Smaller ecosystem compared to 3.9-3.11 (mitigated: most libraries support 3.12 by 2026)

**Mitigation**: Provide clear installation docs and Docker images for easy deployment.

### References
- **Functional Spec**: N/A (implementation decision)
- **QA_SPEC**: Implicit in V1.0 scope

---

## Decision 2: Pydantic v2 for Data Models

### Question
How should we handle data validation, settings management, and serialization? Roll our own validators or use a library?

### Decision
Use **Pydantic v2.x** as the foundation for all data models, configuration, and validation.

### Rationale

1. **Performance**: Pydantic v2 core is written in Rust (pydantic-core)
   - **17x faster** than Pydantic v1
   - Competitive with hand-written validators
   - Zero runtime overhead for type hints

2. **Automatic Validation**:
   - Validates data at construction time
   - Clear, actionable error messages
   - Handles complex validation rules declaratively

3. **Built-in Serialization**:
   - JSON serialization out of the box
   - Schema generation (JSON Schema)
   - Proper datetime/UUID handling

4. **Settings Management**:
   - `pydantic-settings` for environment variables
   - Type-safe configuration loading
   - Automatic parsing and validation

5. **Developer Experience**:
   - IDE autocomplete and type checking
   - Self-documenting models
   - No boilerplate validation code

6. **Industry Standard**:
   - Used by FastAPI, SQLModel, LangChain, and many others
   - Active development and community
   - Excellent documentation

### Alternatives Considered

1. **dataclasses + manual validation**
   - **Why rejected**: Requires writing custom validators for every field
   - No automatic JSON serialization
   - No settings management
   - More boilerplate code
   - Error messages less clear

2. **attrs + cattrs**
   - **Why rejected**: Less performant than Pydantic v2
   - Smaller ecosystem and community
   - More complex API for serialization
   - No settings management out of the box

3. **msgspec.Struct**
   - **Why rejected**: While very fast, lacks settings management
   - Less flexible validation
   - Smaller ecosystem
   - Better as serialization layer (see Decision 4)

### Trade-offs

**Advantages**:
- Excellent performance (Rust core)
- Zero boilerplate for validation
- Type safety with IDE support
- Industry-proven

**Disadvantages**:
- Adds dependency (mitigated: widely used, stable)
- Learning curve for contributors (mitigated: excellent docs)

### References
- **Functional Spec**: 03-MESSAGES.md (message validation requirements)
- **QA_SPEC**: Q2.1, Q2.2 (message structure, validation)

---

## Decision 3: Polars (Primary) with Pandas Fallback

### Question
Which dataframe library should we use for CSV reading and data manipulation? Pandas (ubiquitous) or Polars (modern, fast)?

### Decision
Use **polars** as the primary library for CSV/dataframe operations, with **pandas** as an optional fallback for ecosystem compatibility.

### Rationale

1. **Performance**: Polars is **5-10x faster** than pandas for CSV reading/writing
   - Rust-based engine
   - Better memory efficiency
   - Parallel processing by default

2. **Modern API Design**:
   - Cleaner, more consistent API
   - Explicit vs implicit operations
   - Better error messages

3. **Lazy Evaluation**:
   - Query optimization before execution
   - Reduced memory usage
   - Better for large files

4. **Future-Proof**:
   - Growing adoption in data engineering
   - Active development
   - Modern codebase (no 10+ year legacy)

5. **Pandas Fallback**:
   - Keep pandas as optional dependency
   - Larger ecosystem (sklearn, statsmodels, etc.)
   - More integrations available
   - Users can choose based on needs

### Alternatives Considered

1. **Pandas only**
   - **Why rejected**: Slower performance, larger memory footprint
   - Legacy API with inconsistencies
   - But: Keep as optional for ecosystem compatibility

2. **CSV stdlib only**
   - **Why rejected**: Too slow for large files
   - No automatic type inference
   - Requires manual parsing logic

3. **Dask or Vaex** (distributed dataframes)
   - **Why rejected**: Overkill for V1.0 single-machine use case
   - More complex dependency
   - V2.0 could add distributed sources

### Trade-offs

**Advantages**:
- Best-in-class CSV performance
- Lower memory usage
- Modern, clean API
- Pandas still available for compatibility

**Disadvantages**:
- Smaller ecosystem than pandas (mitigated: growing rapidly)
- Two libraries to maintain (mitigated: similar APIs, thin wrapper)

**Implementation**: Provide CSVSource with configurable backend (`engine="polars"` or `engine="pandas"`).

### References
- **Functional Spec**: 04-SOURCES.md (CSVSource requirements)
- **QA_SPEC**: Q3.3 (CSV batch modes)

---

## Decision 4: Pydantic JSON (Default), msgspec (Optional)

### Question
What serialization format and library should we use for messages? Standard library JSON, Pydantic, or specialized library?

### Decision
Use **Pydantic's built-in JSON serialization** as the default, with **msgspec** as an optional high-performance alternative.

### Rationale

1. **Pydantic JSON (Default)**:
   - **Zero extra dependencies** (already using Pydantic)
   - Leverages pydantic-core (Rust-based) for good performance (~200k msgs/sec)
   - Handles datetime, UUID, and custom types automatically
   - ~4x faster than stdlib json
   - Human-readable JSON format

2. **msgspec (Optional)**:
   - **10x faster** than stdlib json (~500k msgs/sec)
   - Zero-copy deserialization
   - Still JSON format (human-readable, debuggable)
   - Simple API
   - Pure Rust implementation

3. **Pluggable Design**:
   - Define `Serializer` ABC
   - Implementations: `PydanticJsonSerializer`, `MsgspecJsonSerializer`
   - Users choose based on performance needs

4. **JSON Format**:
   - Human-readable and debuggable
   - Universal tool support
   - Easy integration with external systems
   - Standard web format

### Alternatives Considered

1. **stdlib json only**
   - **Why rejected**: Too slow (~50k msgs/sec)
   - Manual datetime/UUID handling
   - Pydantic already provides better alternative

2. **MessagePack** (binary)
   - **Why rejected**: Not human-readable
   - Harder to debug
   - Less universal
   - Could add in V2.0 for network transport

3. **Protocol Buffers** or **Avro**
   - **Why rejected**: Requires schema files
   - More complex setup
   - Overkill for in-process messaging
   - V2.0 could add for cross-language support

4. **Pickle**
   - **Why rejected**: Python-specific, not portable
   - Security concerns (arbitrary code execution)
   - Not suitable for data exchange

### Performance Comparison

```
Serialization Performance (messages/second):
- stdlib json:        ~50,000
- Pydantic (v2):     ~200,000 (4x faster)
- msgspec:           ~500,000 (10x faster)
```

### Trade-offs

**Advantages**:
- Good default performance (Pydantic)
- Optional high performance (msgspec)
- Human-readable format
- Pluggable design

**Disadvantages**:
- JSON is text-based (larger than binary)
- Not the absolute fastest (Pydantic is "good enough", msgspec is "very fast")

**Recommendation**: Use Pydantic for most cases, msgspec for high-throughput scenarios.

### References
- **Functional Spec**: 03-MESSAGES.md (serialization requirements)
- **QA_SPEC**: Q2.3 (timestamp precision), Q2.4 (tag types)

---

## Decision 5: structlog for Structured Logging

### Question
What logging approach should we use? Standard library logging, print statements, or structured logging library?

### Decision
Use **structlog** for all logging throughout the framework.

### Rationale

1. **Structured Output**:
   - Machine-parsable logs (JSON format)
   - Easy filtering and searching
   - Better for log aggregation systems (ELK, Datadog, etc.)

2. **Context Binding**:
   - Attach trace IDs, component names, etc. to logger
   - Context propagates through call chain
   - No need to pass trace_id everywhere

3. **Developer Experience**:
   - Clean API: `logger.info("message_published", channel=channel, count=5)`
   - Better than string formatting: `logger.info(f"Published to {channel} count={count}")`
   - Type-safe field names

4. **Performance**:
   - Lazy evaluation (string formatting only if log level enabled)
   - Minimal overhead

5. **Industry Standard**:
   - Used by many Python data/infra projects
   - Good documentation and community

### Alternatives Considered

1. **stdlib logging**
   - **Why rejected**: String-based messages, harder to parse
   - Less structured
   - More verbose configuration
   - But: Could use as backend for structlog

2. **loguru**
   - **Why rejected**: Less structured than structlog
   - More focused on developer convenience than machine parsing
   - Smaller ecosystem

3. **Print statements**
   - **Why rejected**: Not production-ready
   - No log levels, no filtering
   - Can't disable or redirect

### Trade-offs

**Advantages**:
- Structured, parsable logs
- Context binding
- Clean API
- Production-ready

**Disadvantages**:
- Adds dependency (mitigated: small, stable library)
- Different from stdlib logging (mitigated: can interoperate)

### References
- **Functional Spec**: 10-OBSERVABILITY.md (logging requirements)
- **QA_SPEC**: Q8.1 (metrics format)

---

## Decision 6: AsyncIO for Concurrency

### Question
What concurrency model should we use? Threading, multiprocessing, asyncio, or combination?

### Decision
Use **asyncio** as the primary concurrency model for I/O-bound operations, with optional ProcessPoolExecutor for CPU-bound transformations.

### Rationale

1. **Non-blocking I/O**:
   - Sources and destinations are I/O-bound (file, network)
   - AsyncIO allows many concurrent operations without threads
   - No GIL contention for I/O

2. **Efficient Resource Usage**:
   - Single event loop can handle thousands of async operations
   - Lower memory overhead than threads
   - Better CPU utilization

3. **Mature in Python 3.12**:
   - Performance improvements in 3.12
   - Stable, well-tested
   - Good library ecosystem (aiofiles, aiohttp, etc.)

4. **Natural Fit for Pub/Sub**:
   - Callbacks are async functions
   - Event-driven architecture
   - Easy to coordinate multiple components

5. **Optional CPU-bound Processing**:
   - Use ProcessPoolExecutor for heavy transformations
   - AsyncIO can orchestrate parallel processes
   - Best of both worlds

### Alternatives Considered

1. **Threading**
   - **Why rejected**: GIL limits CPU parallelism
   - Higher memory overhead
   - Race conditions harder to debug
   - But: Could use for blocking I/O if needed

2. **Multiprocessing**
   - **Why rejected**: Higher overhead (process spawn)
   - More complex IPC
   - Overkill for I/O-bound work
   - But: Use ProcessPoolExecutor for CPU transforms

3. **Synchronous (no concurrency)**
   - **Why rejected**: Poor performance for concurrent sources/destinations
   - Sequential processing limits throughput
   - Not suitable for real-time use cases

4. **Trio** or **anyio** (alternative async libraries)
   - **Why rejected**: AsyncIO is standard library
   - Broader ecosystem
   - More documentation and examples

### Trade-offs

**Advantages**:
- Efficient for I/O-bound work
- Lower overhead than threads
- Good ecosystem
- Standard library (no dependency)

**Disadvantages**:
- Async/await syntax required throughout
- Harder to debug than synchronous (mitigated: better tools in 3.12)
- CPU-bound work still needs threads/processes

**Implementation**: Main event loop coordinates sources, broker, and destinations. CPU-heavy transforms use ProcessPoolExecutor.

### References
- **Functional Spec**: 02-ARCHITECTURE.md (concurrency requirements)
- **QA_SPEC**: Q1.1 (concurrency model)

---

## Decision 7: Leverage Proven Libraries

### Question
Should we implement core functionality from scratch or leverage existing libraries?

### Decision
**Prefer solid, proven libraries** over custom implementations. Don't reinvent the wheel.

### Philosophy

1. **Use Battle-Tested Code**:
   - Established libraries have found and fixed edge cases
   - More thoroughly tested than custom code
   - Often more performant (e.g., Rust-based implementations)

2. **Focus on Core Value**:
   - Our value is in the framework architecture, not CSV parsing
   - Spend time on pub/sub logic, not validation boilerplate
   - Differentiate where it matters

3. **Prefer Performance**:
   - When multiple options exist, prefer faster implementations
   - polars over pandas (5-10x faster)
   - msgspec over stdlib json (10x faster)
   - Pydantic v2 over v1 (17x faster)

4. **Keep Dependencies Reasonable**:
   - 10-15 core dependencies is acceptable
   - All must be pip-installable (no complex C compilation)
   - Prefer actively maintained projects

5. **No Compilation Required**:
   - All dependencies provide wheels (pre-compiled binaries)
   - Easy `pip install`, works on all platforms
   - Fast installation

### Core Dependencies Chosen

| Library | Purpose | Why This One |
|---------|---------|--------------|
| **pydantic** | Validation, settings | Rust-based v2 (17x faster), industry standard |
| **polars** | CSV/dataframes | 5-10x faster than pandas, modern API |
| **structlog** | Logging | Structured, machine-parsable, context binding |
| **msgspec** | Serialization | 10x faster than json, zero-copy |
| **aiofiles** | Async file I/O | Standard for async file operations |
| **pyyaml** | YAML parsing | Ubiquitous, stable |

**Total Core Dependencies**: ~6-8 (very reasonable)

### Alternatives Considered

1. **Custom implementations for everything**
   - **Why rejected**: Reinventing wheel
   - More bugs, less performance
   - More code to maintain

2. **Minimal dependencies (stdlib only)**
   - **Why rejected**: Much slower (stdlib json vs msgspec)
   - More boilerplate (no Pydantic validation)
   - Worse developer experience

3. **Every possible library (kitchen sink)**
   - **Why rejected**: Dependency bloat
   - Harder to install/maintain
   - Conflicting versions

### Trade-offs

**Advantages**:
- Better performance (leverage Rust implementations)
- Less code to maintain
- Proven, tested implementations
- Better developer experience

**Disadvantages**:
- External dependencies (mitigated: all stable, widely-used)
- Version compatibility (mitigated: use modern versions, clear requirements)

### References
- **Functional Spec**: All components benefit from this decision
- **QA_SPEC**: Implicit in performance requirements

---

## Decision 8: Hybrid Subscription Registry

### Question
How should we implement channel pattern matching? Hash map, regex, trie, or hybrid?

### Decision
Use a **hybrid approach**: O(1) exact matches, compiled regex for wildcards.

### Rationale

1. **Performance Optimization**:
   - Most subscriptions are exact matches → O(1) lookup
   - Wildcards use pre-compiled regex → faster than runtime matching
   - Common case (exact) is optimized, rare case (wildcard) is acceptable

2. **Simplicity**:
   - No complex trie structure
   - Easy to understand and debug
   - Minimal code

3. **Sufficient Performance**:
   - O(1) for exact: `sensors.temp` → instant
   - O(n) for wildcards: n = number of wildcard patterns (typically small, <100)
   - Total matching time: <1ms for typical workloads

### Implementation Strategy

```python
class SubscriptionRegistry:
    def __init__(self):
        self._exact_matches: dict[str, list[Callback]] = {}
        self._single_wildcards: dict[Pattern, list[Callback]] = {}
        self._multi_wildcards: list[tuple[Pattern, Callback]] = []
```

**Matching Algorithm**:
1. Check exact match first (fast path)
2. If no exact match, iterate wildcards
3. Return combined results

### Alternatives Considered

1. **Regex for all patterns**
   - **Why rejected**: Slower for common exact matches
   - O(n) for everything instead of O(1) for exact

2. **Trie (prefix tree)**
   - **Why rejected**: More complex implementation
   - Memory overhead
   - Overkill for typical use cases (100s of patterns, not millions)

3. **Compile all patterns to single mega-regex**
   - **Why rejected**: Harder to maintain
   - Difficult to add/remove subscriptions
   - Less clear error messages

### Trade-offs

**Advantages**:
- Fast common case (exact match)
- Simple, maintainable code
- Good enough performance for wildcards

**Disadvantages**:
- O(n) for wildcard matching (acceptable: n is small)
- Not optimal for thousands of wildcard patterns (not a V1.0 requirement)

**Optimization Path**: If users report slow wildcard matching with many patterns, V2.0 could add trie-based optimization.

### References
- **Functional Spec**: 07-CHANNELS-ROUTING.md (wildcard patterns)
- **QA_SPEC**: Q6.2 (pattern matching)

---

## Decision 9: Immutable Messages

### Question
Should messages be mutable or immutable after creation?

### Decision
Messages are **immutable** (frozen Pydantic models).

### Rationale

1. **Thread Safety**:
   - Immutable objects are inherently thread-safe
   - No race conditions when passing messages between components
   - Simpler concurrency model

2. **Predictability**:
   - Message can't be modified after publish
   - Transformations create new messages (functional style)
   - Easier to reason about data flow

3. **Debugging**:
   - Message state can't change unexpectedly
   - Clear data lineage (each transformation creates new message)

4. **Performance**:
   - Pydantic frozen models are fast
   - No defensive copying needed
   - Can share references safely

### Implementation

```python
class Message(BaseModel):
    model_config = {
        "frozen": True,  # Immutable
    }
```

### Alternatives Considered

1. **Mutable messages**
   - **Why rejected**: Thread-safety concerns
   - Need defensive copying
   - Harder to track changes

2. **Copy-on-write**
   - **Why rejected**: More complex implementation
   - Pydantic frozen is simpler and sufficient

### Trade-offs

**Advantages**:
- Thread-safe by default
- Predictable behavior
- Easier debugging

**Disadvantages**:
- Must create new message for modifications (acceptable: transformations should create new messages anyway)

### References
- **Functional Spec**: 03-MESSAGES.md (message structure)
- **QA_SPEC**: Q2.1 (message attributes)

---

## Decision 10: Fail-Fast vs Resilient

### Question
How should we handle errors? Crash on any error or try to continue?

### Decision
**Fail-fast for configuration errors, resilient for runtime errors.**

### Rationale

1. **Configuration Errors** (fail-fast):
   - Invalid configuration should be caught at startup
   - Better to crash immediately than behave incorrectly
   - Pydantic validation provides clear error messages
   - Forces users to fix configuration before running

2. **Runtime Errors** (resilient):
   - Sources/destinations may have transient failures
   - Log error and continue processing
   - Don't crash entire framework for one bad message
   - Per-component error isolation

3. **Clear Error Messages**:
   - Pydantic: "Field 'channel' is required"
   - structlog: Structured error logging with context

### Strategy

**Startup (fail-fast)**:
```python
try:
    config = PipelineConfig(**config_dict)
except ValidationError as e:
    # Print clear error and exit
    sys.exit(1)
```

**Runtime (resilient)**:
```python
try:
    await destination.write(message)
except Exception as e:
    logger.error("write_failed", destination=dest_id, error=str(e))
    # Continue processing, optionally send to DLQ
```

### Alternatives Considered

1. **Always fail-fast**
   - **Why rejected**: Too brittle for production
   - Single bad message crashes framework

2. **Always resilient**
   - **Why rejected**: Silent failures at startup
   - Configuration errors only discovered at runtime

### Trade-offs

**Advantages**:
- Configuration errors caught early
- Production resilience for transient failures
- Clear error messages

**Disadvantages**:
- Need to check logs for runtime errors
- Some errors may be ignored (mitigated: observability)

### References
- **Functional Spec**: 02-ARCHITECTURE.md (error handling)
- **QA_SPEC**: Q1.3 (error handling philosophy)

---

## Summary of Decisions

| Decision | Choice | Primary Reason |
|----------|--------|----------------|
| Language | Python 3.12+ | Performance, modern features |
| Data Models | Pydantic v2 | Rust-based performance, validation |
| Dataframes | polars (pandas fallback) | 5-10x faster CSV processing |
| Serialization | Pydantic JSON (msgspec optional) | Good default, optional high-perf |
| Logging | structlog | Structured, machine-parsable |
| Concurrency | AsyncIO | Efficient for I/O-bound work |
| Dependencies | Leverage proven libraries | Performance, reliability |
| Subscriptions | Hybrid (exact + regex) | Fast common case, simple |
| Messages | Immutable | Thread-safe, predictable |
| Error Handling | Fail-fast config, resilient runtime | Safety + robustness |

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-24 | 1.0.0 | Initial version with 10 core decisions |

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-99](TECH-99-IMPLEMENTATION-GUIDE.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-00 →](TECH-00-OVERVIEW.md) |
