# Build, Package, and Deployment

**Document**: TECH-11-DEPLOYMENT.md
**Version**: 1.0.0
**Date**: 2026-01-24
**Status**: Draft
**Implements**: [11-DEPLOYMENT](../FUNCTIONAL_SPECIFICATION/11-DEPLOYMENT.md)

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-10](TECH-10-TESTING.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-12 →](TECH-12-API-REFERENCE.md) |

---

## Table of Contents

1. [Package Structure](#package-structure)
2. [Dependencies](#dependencies)
3. [Installation](#installation)
4. [Deployment Modes](#deployment-modes)
5. [Docker Deployment](#docker-deployment)

---

## Package Structure

```
cod3s-data-python/
├── pyproject.toml           # Package metadata (PEP 518/621)
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt         # Pinned dependencies
├── requirements-dev.txt     # Development dependencies
│
├── cod3s_data/             # Main package
│   ├── __init__.py         # Public API exports
│   ├── __version__.py      # Version info
│   ├── framework.py        # Framework class
│   │
│   ├── core/               # Core components
│   │   ├── __init__.py
│   │   ├── message.py      # Message class
│   │   ├── broker.py       # Broker ABC, InMemoryBroker
│   │   └── buffers.py      # Buffers and registries
│   │
│   ├── sources/            # Sources
│   │   ├── __init__.py
│   │   ├── base.py         # Source ABC
│   │   ├── csv_source.py
│   │   ├── random_source.py
│   │   ├── sequence_source.py
│   │   └── file_source.py
│   │
│   ├── transformations/    # Transformations
│   │   ├── __init__.py
│   │   ├── base.py         # Transform ABCs
│   │   ├── filter.py
│   │   ├── threshold.py
│   │   └── aggregator.py
│   │
│   ├── destinations/       # Destinations
│   │   ├── __init__.py
│   │   ├── base.py         # Destination ABC
│   │   ├── console.py
│   │   ├── file.py
│   │   └── collect.py
│   │
│   ├── config/             # Configuration
│   │   ├── __init__.py
│   │   ├── models.py       # Pydantic models
│   │   └── loader.py       # YAML loading
│   │
│   ├── observability/      # Logging and metrics
│   │   ├── __init__.py
│   │   ├── logging.py
│   │   └── metrics.py
│   │
│   ├── testing/            # Test utilities
│   │   ├── __init__.py
│   │   └── collect.py      # CollectDestination
│   │
│   └── cli/                # CLI (V2.0)
│       ├── __init__.py
│       └── main.py
│
├── tests/                  # Test suite
│   ├── __init__.py
│   ├── conftest.py         # pytest fixtures
│   ├── unit/
│   ├── integration/
│   └── performance/
│
├── examples/               # Example pipelines
│   ├── quickstart.py
│   ├── 3d_printer.py
│   └── configs/
│       ├── simple.yaml
│       └── advanced.yaml
│
└── docs/                   # Documentation
    ├── conf.py             # Sphinx config
    └── index.rst
```

---

## Dependencies

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "cod3s-data"
version = "1.0.0"
description = "Lightweight data pipeline framework"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "MIT"}
authors = [
    {name = "COD3S Team", email = "team@cod3s.example"}
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]

dependencies = [
    # Core dependencies
    "pydantic>=2.9",           # Data validation, settings
    "pydantic-settings>=2.5",  # Environment variables
    "pyyaml>=6.0",             # YAML parsing
    "structlog>=24.0",         # Structured logging

    # Data handling
    "polars>=1.15",            # Fast CSV/dataframes
    "aiofiles>=24.0",          # Async file I/O

    # Optional performance
    "msgspec>=0.18",           # High-performance serialization
]

[project.optional-dependencies]
# Pandas as alternative to polars
pandas = [
    "pandas>=2.2",
]

# Development tools
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "pytest-benchmark>=5.0",
    "mypy>=1.13",
    "ruff>=0.8",
]

# Documentation
docs = [
    "mkdocs>=1.6",
    "mkdocs-material>=9.5",
]

[project.scripts]
cod3s = "cod3s_data.cli.main:main"

[project.urls]
Homepage = "https://github.com/cod3s/cod3s-data"
Documentation = "https://cod3s-data.readthedocs.io"
Repository = "https://github.com/cod3s/cod3s-data"

[tool.setuptools.packages.find]
where = ["."]
include = ["cod3s_data*"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[[tool.mypy.overrides]]
module = ["polars.*", "aiofiles.*"]
ignore_missing_imports = true
```

---

## Installation

### From PyPI (Future)

```bash
# Install from PyPI
pip install cod3s-data

# With pandas instead of polars
pip install cod3s-data[pandas]

# Development installation
pip install cod3s-data[dev]
```

### From Source

```bash
# Clone repository
git clone https://github.com/cod3s/cod3s-data.git
cd cod3s-data

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy cod3s_data/

# Linting
ruff check .
```

### Using uv (Recommended)

```bash
# Install uv (fast package installer)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create environment and install
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

---

## Deployment Modes

### Mode 1: Embedded Library

```python
# app.py
from cod3s_data import Framework
from cod3s_data.sources import CSVSource
from cod3s_data.destinations import ConsoleDestination

async def main():
    framework = Framework.from_yaml("pipeline.yaml")
    await framework.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Mode 2: CLI Tool (V2.0)

```bash
# Run pipeline from YAML
cod3s run pipeline.yaml

# Validate configuration
cod3s validate pipeline.yaml

# List available components
cod3s list sources
cod3s list destinations
cod3s list transformations
```

### Mode 3: Standalone Service (V2.0)

```bash
# Run as HTTP service
cod3s serve --config pipeline.yaml --port 8080

# With systemd
systemctl start cod3s-data
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

# Copy source code
COPY cod3s_data/ ./cod3s_data/

# Copy examples and configs
COPY examples/ ./examples/

# Non-root user
RUN useradd -m -u 1000 cod3s && \
    chown -R cod3s:cod3s /app
USER cod3s

# Default command (override with docker run)
CMD ["python", "-m", "cod3s_data", "run", "/config/pipeline.yaml"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  cod3s-data:
    build: .
    image: cod3s-data:1.0.0
    container_name: cod3s-pipeline

    environment:
      # Configuration overrides
      - COD3S_BROKER_HISTORY_SIZE=200
      - COD3S_OUTPUT_DIR=/output

    volumes:
      # Configuration
      - ./config:/config:ro
      # Data input
      - ./data:/data:ro
      # Output
      - ./output:/output

    restart: unless-stopped

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          cpus: '1'
          memory: 512M

    # Health check
    healthcheck:
      test: ["CMD", "python", "-c", "import cod3s_data; print('OK')"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Build and Run

```bash
# Build image
docker build -t cod3s-data:1.0.0 .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Multi-stage Build (Production)

```dockerfile
# Builder stage
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --user .

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy source
COPY cod3s_data/ ./cod3s_data/

# Make sure scripts are in PATH
ENV PATH=/root/.local/bin:$PATH

USER 1000

CMD ["python", "-m", "cod3s_data"]
```

---

## Systemd Service

### cod3s-data.service

```ini
[Unit]
Description=COD3S Data Framework
After=network.target

[Service]
Type=simple
User=cod3s
WorkingDirectory=/opt/cod3s-data
Environment="PATH=/opt/cod3s-data/.venv/bin:/usr/bin"
ExecStart=/opt/cod3s-data/.venv/bin/python -m cod3s_data run /etc/cod3s/pipeline.yaml
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cod3s-data

# Security
NoNewPrivileges=true
PrivateTmp=true
ReadOnlyPaths=/etc/cod3s

[Install]
WantedBy=multi-user.target
```

### Installation

```bash
# Copy service file
sudo cp cod3s-data.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable cod3s-data
sudo systemctl start cod3s-data

# Check status
sudo systemctl status cod3s-data

# View logs
sudo journalctl -u cod3s-data -f
```

---

## References

- **Functional Spec**: [11-DEPLOYMENT](../FUNCTIONAL_SPECIFICATION/11-DEPLOYMENT.md)
- **QA Decisions**: [Q9.1-Q9.2](../FUNCTIONAL_SPECIFICATION/QA_SPEC.md)
- **Related Tech Specs**:
  - [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) - Dependencies
  - [TECH-07-CONFIGURATION-API](TECH-07-CONFIGURATION-API.md) - Configuration loading

---

## Navigation
| Previous | Up | Next |
|----------|-----|------|
| [← TECH-10](TECH-10-TESTING.md) | [TECH-00-OVERVIEW](TECH-00-OVERVIEW.md) | [TECH-12 →](TECH-12-API-REFERENCE.md) |
