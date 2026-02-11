# Technical Specification Overview

**Document**: TECH-00-OVERVIEW.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Purpose**: Technical specification index, navigation, and technology stack summary

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← Functional Spec](../FUNCTIONAL_SPECIFICATION/00-OVERVIEW.md) | Technical Specification | [TECH-01 →](TECH-01-ARCHITECTURE.md) |

---

## Table of Contents

1. [Introduction](#introduction)
2. [Document Map](#document-map)
3. [Technology Stack](#technology-stack)
4. [Core Dependencies](#core-dependencies)
5. [Traceability Matrix](#traceability-matrix)
6. [Development Environment](#development-environment)
7. [Reading Guide](#reading-guide)

---

## Introduction

### Purpose

This technical specification suite provides **implementation-ready guidance** for building the COD3S Data Framework V1.0. It bridges the gap between functional requirements and actual code, specifying:

- Internal architecture and design patterns
- Data structures and algorithms
- API signatures with type hints
- Component implementations
- Testing strategies
- Deployment procedures

### Target Audience

- **Framework Implementers**: Developers building the COD3S Data Framework
- **Integration Engineers**: Developers integrating COD3S into applications
- **Component Authors**: Developers creating custom sources, transformations, destinations
- **Technical Reviewers**: Architects validating design decisions

### Relationship to Functional Specification

The [Functional Specification](../FUNCTIONAL_SPECIFICATION/00-OVERVIEW.md) defines **what** the framework must do. This technical specification defines **how** to implement it.

**Coverage**: 100% of V1.0 functional requirements, with V2.0 extension points identified.

---

## Document Map

### Foundation Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | Index, navigation, tech stack (this document) | Draft |
| [TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md) | Internal architecture, concurrency model, lifecycle | Draft |
| [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) | Core data structures (Message, buffers, registries) | Draft |
| [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md) | Technical design decisions log | Draft |

**Read these first** to understand the architectural foundation.

### Component API Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [TECH-03-BROKER-API](TECH-03-BROKER-API.md) | Broker implementation and API | Draft |
| [TECH-04-SOURCES-API](TECH-04-SOURCES-API.md) | Sources implementation and API | Draft |
| [TECH-05-TRANSFORMATIONS-API](TECH-05-TRANSFORMATIONS-API.md) | Transformations implementation and API | Draft |
| [TECH-06-DESTINATIONS-API](TECH-06-DESTINATIONS-API.md) | Destinations implementation and API | Draft |
| [TECH-07-CONFIGURATION-API](TECH-07-CONFIGURATION-API.md) | Configuration system implementation | Draft |
| [TECH-08-OBSERVABILITY-API](TECH-08-OBSERVABILITY-API.md) | Observability implementation | Draft |

**Read these** to understand component-specific implementations.

### Infrastructure Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [TECH-09-SERIALIZATION](TECH-09-SERIALIZATION.md) | Serialization formats and protocols | Draft |
| [TECH-10-TESTING](TECH-10-TESTING.md) | Testing infrastructure and patterns | Draft |
| [TECH-11-DEPLOYMENT](TECH-11-DEPLOYMENT.md) | Build, package, deployment | Draft |

**Read these** for cross-cutting concerns.

### Reference Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [TECH-12-API-REFERENCE](TECH-12-API-REFERENCE.md) | Complete API reference | Draft |
| [TECH-99-IMPLEMENTATION-GUIDE](TECH-99-IMPLEMENTATION-GUIDE.md) | Developer implementation guide | Draft |

**Use these** as ongoing references during development.

### Recommended Reading Order

**For Framework Implementers**:
1. TECH-00-OVERVIEW (this document)
2. TECH-APPENDIX-A-DECISIONS (understand key choices)
3. TECH-01-ARCHITECTURE (understand overall design)
4. TECH-02-DATA-STRUCTURES (core data types)
5. Component APIs in dependency order:
   - TECH-03-BROKER-API
   - TECH-04-SOURCES-API
   - TECH-06-DESTINATIONS-API
   - TECH-05-TRANSFORMATIONS-API
   - TECH-07-CONFIGURATION-API
   - TECH-08-OBSERVABILITY-API
6. Infrastructure: TECH-09, TECH-10, TECH-11
7. TECH-99-IMPLEMENTATION-GUIDE (development workflow)

**For Component Authors** (custom sources/transforms/destinations):
1. TECH-00-OVERVIEW (this document)
2. TECH-02-DATA-STRUCTURES (Message class)
3. Specific component API (TECH-04, TECH-05, or TECH-06)
4. TECH-99-IMPLEMENTATION-GUIDE (extension guide)

**For Integration Engineers**:
1. TECH-00-OVERVIEW (this document)
2. TECH-07-CONFIGURATION-API (how to configure)
3. TECH-11-DEPLOYMENT (how to deploy)
4. TECH-12-API-REFERENCE (API usage)

---

## Technology Stack

### Language and Runtime

**Python 3.12+**
- **Why**: 10-30% faster than 3.9, modern type hints, better error messages
- **Rationale**: See [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-1-python-312-as-minimum-version)

### Concurrency Model

**AsyncIO**
- **Purpose**: Non-blocking I/O for sources and destinations
- **Why**: Efficient for I/O-bound operations, mature in Python 3.12
- **Details**: See [TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md#concurrency-model)

### Core Philosophy

**Leverage proven libraries, don't reinvent the wheel**
- Use battle-tested implementations (Pydantic, polars, structlog)
- Prefer performance (Rust-based libraries when available)
- Keep dependencies reasonable (10-15 core deps)
- All dependencies pip-installable with wheels (no compilation)

---

## Core Dependencies

### Data Validation and Models

**Pydantic v2.x** ([docs](https://docs.pydantic.dev))
- **Purpose**: Data validation, settings management, serialization
- **Why**: Rust-based core (17x faster than v1), automatic validation, excellent DX
- **Usage**: All data models (Message, configuration, etc.)
- **Rationale**: [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-2-pydantic-v2-for-data-models)

**pydantic-settings v2.x** ([docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/))
- **Purpose**: Environment variable configuration with validation
- **Why**: Type-safe configuration loading, automatic parsing
- **Usage**: Configuration system (TECH-07)

### Data Processing

**polars v1.15+** ([docs](https://docs.pola.rs))
- **Purpose**: CSV/dataframe operations
- **Why**: 5-10x faster than pandas, better memory efficiency, modern API
- **Usage**: CSVSource, data manipulation
- **Fallback**: pandas v2.2+ as optional dependency for ecosystem compatibility
- **Rationale**: [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-3-polars-primary-with-pandas-fallback)

### Serialization

**msgspec v0.18+** ([docs](https://jcristharif.com/msgspec/))
- **Purpose**: High-performance JSON serialization (10x faster than stdlib)
- **Why**: Zero-copy deserialization, still human-readable
- **Usage**: Optional high-performance serialization
- **Default**: Pydantic's built-in JSON (good performance, zero extra deps)
- **Rationale**: [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-4-pydantic-json-default-msgspec-optional)

### Logging

**structlog v24.0+** ([docs](https://www.structlog.org))
- **Purpose**: Structured, machine-parsable logging
- **Why**: Context binding, clean API, production-ready
- **Usage**: All logging throughout framework
- **Rationale**: [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md#decision-5-structlog-for-structured-logging)

### File I/O

**aiofiles v24.0+** ([docs](https://github.com/Tinche/aiofiles))
- **Purpose**: Async file operations (non-blocking reads/writes)
- **Why**: AsyncIO-compatible file I/O
- **Usage**: FileSource, FileDestination

### Configuration

**PyYAML v6.0+** ([docs](https://pyyaml.org))
- **Purpose**: YAML parsing for configuration files
- **Why**: Standard, stable, widely-used
- **Usage**: Configuration loading (TECH-07)

### Development Tools

**ruff v0.8+** ([docs](https://docs.astral.sh/ruff/))
- **Purpose**: Fast linter and formatter (replaces black, flake8, isort)
- **Why**: 10-100x faster than alternatives, written in Rust
- **Usage**: Code quality enforcement

**mypy v1.13+** ([docs](https://mypy-lang.org))
- **Purpose**: Static type checking (strict mode)
- **Why**: Catch type errors before runtime
- **Usage**: Type safety validation

**pytest v8.0+** ([docs](https://docs.pytest.org))
- **Purpose**: Testing framework
- **Why**: Industry standard, excellent async support (pytest-asyncio)
- **Usage**: Unit, integration, and performance tests

### Dependency Summary

```toml
# pyproject.toml (simplified)
[project]
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.9",
    "pydantic-settings>=2.5",
    "polars>=1.15",
    "structlog>=24.0",
    "aiofiles>=24.0",
    "pyyaml>=6.0",
    "msgspec>=0.18",  # Optional but recommended
]

[project.optional-dependencies]
pandas = ["pandas>=2.2"]  # Alternative to polars
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-benchmark>=5.0",
    "pytest-cov>=6.0",
    "mypy>=1.13",
    "ruff>=0.8",
]
```

**Total Core Dependencies**: 7 (very reasonable)
**All provide wheels**: Fast, no compilation required

---

## Traceability Matrix

This section maps functional requirements to technical specifications.

### Functional → Technical Mapping

| Functional Spec | Technical Spec | Coverage |
|-----------------|----------------|----------|
| [02-ARCHITECTURE](../FUNCTIONAL_SPECIFICATION/02-ARCHITECTURE.md) | [TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md) | AsyncIO concurrency, lifecycle |
| [03-MESSAGES](../FUNCTIONAL_SPECIFICATION/03-MESSAGES.md) | [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) | Message class (Pydantic) |
| [04-SOURCES](../FUNCTIONAL_SPECIFICATION/04-SOURCES.md) | [TECH-04-SOURCES-API](TECH-04-SOURCES-API.md) | Source ABC, batch modes |
| [05-TRANSFORMATIONS](../FUNCTIONAL_SPECIFICATION/05-TRANSFORMATIONS.md) | [TECH-05-TRANSFORMATIONS-API](TECH-05-TRANSFORMATIONS-API.md) | Stateless/stateful base classes |
| [06-DESTINATIONS](../FUNCTIONAL_SPECIFICATION/06-DESTINATIONS.md) | [TECH-06-DESTINATIONS-API](TECH-06-DESTINATIONS-API.md) | Destination ABC, retry logic |
| [07-CHANNELS-ROUTING](../FUNCTIONAL_SPECIFICATION/07-CHANNELS-ROUTING.md) | [TECH-03-BROKER-API](TECH-03-BROKER-API.md) | Subscription registry, wildcards |
| [08-BROKER](../FUNCTIONAL_SPECIFICATION/08-BROKER.md) | [TECH-03-BROKER-API](TECH-03-BROKER-API.md) | Broker implementation |
| [09-CONFIGURATION](../FUNCTIONAL_SPECIFICATION/09-CONFIGURATION.md) | [TECH-07-CONFIGURATION-API](TECH-07-CONFIGURATION-API.md) | YAML + Python + env vars |
| [10-OBSERVABILITY](../FUNCTIONAL_SPECIFICATION/10-OBSERVABILITY.md) | [TECH-08-OBSERVABILITY-API](TECH-08-OBSERVABILITY-API.md) | Metrics, logging, tracing |
| [11-DEPLOYMENT](../FUNCTIONAL_SPECIFICATION/11-DEPLOYMENT.md) | [TECH-11-DEPLOYMENT](TECH-11-DEPLOYMENT.md) | Package, Docker, systemd |
| [12-TESTING](../FUNCTIONAL_SPECIFICATION/12-TESTING.md) | [TECH-10-TESTING](TECH-10-TESTING.md) | pytest, test utilities |

### QA_SPEC Decision Coverage

All 33 decisions in [QA_SPEC.md](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md) are addressed:

| QA Decision | Technical Spec | Implementation |
|-------------|----------------|----------------|
| Q1.1 (Concurrency) | TECH-01-ARCHITECTURE | AsyncIO event loop |
| Q1.2 (Language) | TECH-APPENDIX-A | Python 3.12+ |
| Q1.3 (Error handling) | TECH-APPENDIX-A | Fail-fast config, resilient runtime |
| Q2.1-2.6 (Messages) | TECH-02-DATA-STRUCTURES | Pydantic Message model |
| Q3.1-3.5 (Sources) | TECH-04-SOURCES-API | Source ABC, batch modes |
| Q4.1-4.3 (Transformations) | TECH-05-TRANSFORMATIONS-API | Stateless/stateful classes |
| Q5.1-5.4 (Destinations) | TECH-06-DESTINATIONS-API | Destination ABC, buffers |
| Q6.1-6.4 (Broker) | TECH-03-BROKER-API | Subscription registry |
| Q7.1-7.3 (Configuration) | TECH-07-CONFIGURATION-API | Pydantic Settings |
| Q8.1-8.2 (Observability) | TECH-08-OBSERVABILITY-API | structlog, metrics-as-messages |
| Q9.1-9.2 (Deployment) | TECH-11-DEPLOYMENT | pip package, Docker |
| Q10.1-10.2 (Testing) | TECH-10-TESTING | pytest, CollectDestination |

**Coverage**: 100% of V1.0 decisions

---

## Development Environment

### Prerequisites

- **Python 3.12+**: [Download](https://www.python.org/downloads/)
- **pip**: Included with Python 3.12
- **Git**: For version control

### Recommended Setup

**Option 1: uv (recommended, fastest)**
```bash
# Install uv (Rust-based, very fast)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Activate
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e ".[dev]"
```

**Option 2: poetry (alternative)**
```bash
# Install poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install --with dev
```

**Option 3: pip + venv (traditional)**
```bash
# Create virtual environment
python3.12 -m venv .venv

# Activate
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
# Check Python version
python --version  # Should be 3.12+

# Run type checking
mypy cod3s_data/

# Run linting
ruff check .

# Run tests
pytest tests/
```

### IDE Setup

**VS Code** (recommended):
```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

**PyCharm**:
- Set Project SDK to Python 3.12
- Enable mypy plugin
- Configure Ruff as external tool

---

## Reading Guide

### For Different Audiences

#### Framework Implementers

**Goal**: Build the COD3S Data Framework from scratch

**Start here**:
1. This document (TECH-00) - understand stack and structure
2. [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md) - understand key decisions
3. [TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md) - understand overall design

**Then read in order**:
- TECH-02 (data structures)
- TECH-03 through TECH-08 (component APIs)
- TECH-09 through TECH-11 (infrastructure)
- TECH-99 (implementation guide)

**Reference as needed**:
- TECH-12 (API reference)
- Functional specs for requirements
- QA_SPEC for decision rationale

#### Component Authors

**Goal**: Create custom sources, transformations, or destinations

**Start here**:
1. This document (TECH-00) - understand stack
2. [TECH-02-DATA-STRUCTURES](TECH-02-DATA-STRUCTURES.md) - Message class
3. Specific component API:
   - [TECH-04-SOURCES-API](TECH-04-SOURCES-API.md) for custom sources
   - [TECH-05-TRANSFORMATIONS-API](TECH-05-TRANSFORMATIONS-API.md) for custom transformations
   - [TECH-06-DESTINATIONS-API](TECH-06-DESTINATIONS-API.md) for custom destinations

**Then**:
- [TECH-99-IMPLEMENTATION-GUIDE](TECH-99-IMPLEMENTATION-GUIDE.md) - extension guide
- [TECH-10-TESTING](TECH-10-TESTING.md) - testing patterns

**Reference**:
- [TECH-12-API-REFERENCE](TECH-12-API-REFERENCE.md) - base class APIs

#### Integration Engineers

**Goal**: Integrate COD3S into an application

**Start here**:
1. This document (TECH-00) - understand stack
2. [TECH-07-CONFIGURATION-API](TECH-07-CONFIGURATION-API.md) - how to configure
3. [TECH-11-DEPLOYMENT](TECH-11-DEPLOYMENT.md) - how to deploy

**Then**:
- [TECH-12-API-REFERENCE](TECH-12-API-REFERENCE.md) - programmatic API
- Specific component docs as needed

**Reference**:
- Functional specs for feature descriptions
- [TECH-10-TESTING](TECH-10-TESTING.md) - testing your integration

#### Technical Reviewers

**Goal**: Validate design decisions and architecture

**Start here**:
1. This document (TECH-00) - overview
2. [TECH-APPENDIX-A-DECISIONS](TECH-APPENDIX-A-DECISIONS.md) - design rationale
3. [TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md) - architectural patterns

**Review**:
- Traceability matrix (above) - requirement coverage
- Component APIs (TECH-03 through TECH-08) - interface design
- Infrastructure docs (TECH-09 through TECH-11) - deployment strategy

**Validate against**:
- Functional specifications (requirements)
- QA_SPEC (design decisions)
- Industry best practices

### Code Example Conventions

All code examples in this technical specification follow these conventions:

**Type Hints**: Always included (Python 3.12+ syntax)
```python
# Modern syntax (Python 3.12+)
def process(items: list[str]) -> dict[str, int]:
    ...

# NOT the old syntax
from typing import List, Dict
def process(items: List[str]) -> Dict[str, int]:
    ...
```

**Optional Types**: Use `|` syntax
```python
def get_value(key: str) -> str | None:
    ...

# NOT Optional[]
from typing import Optional
def get_value(key: str) -> Optional[str]:
    ...
```

**Async/Await**: Always async for I/O
```python
async def fetch_data() -> list[Message]:
    async with aiofiles.open('data.txt') as f:
        content = await f.read()
    return parse(content)
```

**Pydantic Models**: Frozen (immutable) by default
```python
from pydantic import BaseModel

class Message(BaseModel):
    key: str
    value: int

    model_config = {
        "frozen": True,  # Immutable
    }
```

**Docstrings**: Google style
```python
def calculate(x: int, y: int) -> int:
    """
    Calculate the sum of two numbers.

    Args:
        x: First number
        y: Second number

    Returns:
        Sum of x and y

    Raises:
        ValueError: If inputs are negative
    """
    if x < 0 or y < 0:
        raise ValueError("Inputs must be non-negative")
    return x + y
```

### Version Tags

Throughout the technical specification, features are tagged by version:

- **V1.0**: Implementation-ready, required for first release
- **V2.0**: Extension point identified, outline provided (not fully specified)
- **V3.0+**: Future research, not specified in detail

Example:
```python
# V1.0: InMemoryBroker
class InMemoryBroker(Broker):
    """In-process pub/sub (V1.0)"""
    ...

# V2.0: RedisBroker (extension point)
class RedisBroker(Broker):
    """Redis-based distributed pub/sub (V2.0)"""
    # To be specified in V2.0 technical spec
    ...
```

---

## Document Standards

### Standard Header

Every technical specification document includes:

```markdown
# [Document Title]

**Document**: TECH-XX-NAME.md
**Version**: 1.0.0
**Date**: 2026-01-XX
**Status**: Draft | Review | Approved
**Implements**: [Functional Spec Section]

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-XX](TECH-XX.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-XX →](TECH-XX.md) |
```

### Cross-References

- **Functional Spec**: `[02-ARCHITECTURE](../FUNCTIONAL_SPECIFICATION/02-ARCHITECTURE.md)`
- **Other Tech Spec**: `[TECH-01-ARCHITECTURE](TECH-01-ARCHITECTURE.md)`
- **QA Decision**: `[QA_SPEC Q1.1](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md#q11-concurrency-model)`
- **Code Location**: `src/broker/registry.py:123`

---

## Success Criteria

### Completeness

- ✅ All V1.0 functional requirements have technical specifications
- ✅ All 33 QA_SPEC decisions are implemented
- ✅ All public APIs have type signatures
- ✅ All code examples are runnable
- ✅ All extension points (V2.0) are identified

### Quality

- ✅ Type hints on all public APIs (mypy strict mode compliant)
- ✅ Docstrings on all classes and methods (Google style)
- ✅ Code examples demonstrate actual usage
- ✅ Performance characteristics documented
- ✅ Error cases specified

### Developer Readiness

- ✅ Implementers can build framework from specifications alone
- ✅ No ambiguous requirements
- ✅ Clear rationale for all major decisions
- ✅ Testing strategy enables validation
- ✅ Deployment procedures complete

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-24 | 1.0.0 | Initial technical specification overview |

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← Functional Spec](../FUNCTIONAL_SPECIFICATION/00-OVERVIEW.md) | Technical Specification | [TECH-01 →](TECH-01-ARCHITECTURE.md) |
