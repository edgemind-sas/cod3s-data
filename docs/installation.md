# Installation Guide

## Requirements

- Python 3.12 or higher
- pip or uv package manager

## Installation Methods

### Using pip

```bash
pip install cod3s-data
```

### Using uv (Recommended)

```bash
uv pip install cod3s-data
```

### From Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/yourusername/cod3s-data.git
cd cod3s-data
uv pip install -e ".[dev]"
```

## Verify Installation

Check that the CLI is installed correctly:

```bash
cod3s-data --version
```

You should see:
```
COD3S Data Framework v1.0.0
```

## Optional Dependencies

### Observatory (Web UI)

```bash
uv pip install "cod3s-data[observatory]"
```

Adds FastAPI, uvicorn and websockets, and enables the Observatory UI served at
<http://localhost:8765>.

### InfluxDB Destination

```bash
uv pip install "cod3s-data[influxdb]"
```

Adds `influxdb-client[async]`, required by the `influxdb` destination. A local
server for development:

```bash
docker compose -f docker-compose.influxdb.yml up -d
```

### Development Tools

For development, install with dev dependencies:

```bash
uv pip install "cod3s-data[dev]"
```

This includes:
- pytest (testing framework)
- pytest-asyncio (async test support)
- pytest-cov (code coverage)
- mypy (type checking)
- ruff (linting and formatting)

## Docker Installation

### Pull Pre-built Image

```bash
docker pull cod3s/cod3s-data:latest
```

### Build from Source

```bash
cd cod3s-data
docker build -t cod3s-data .
```

### Run with Docker

```bash
docker run -v $(pwd)/examples:/app/examples cod3s-data run examples/simple_pipeline.yaml
```

## Troubleshooting

### Python Version Issues

If you get a "requires Python >=3.12" error, make sure you have Python 3.12+ installed:

```bash
python --version
```

### Permission Errors

On Linux/macOS, you may need to use `pip install --user` or use a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install cod3s-data
```

### Import Errors

If you get import errors, ensure your virtual environment is activated and the package is installed:

```bash
pip list | grep cod3s-data
```

## Next Steps

- Read the [Quick Start Guide](quickstart.md)
- Explore [Example Pipelines](../examples/)
- Review the [API Reference](api-reference.md)
