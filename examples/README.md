# COD3S Data Framework - Examples

This directory contains example pipelines demonstrating the COD3S Data Framework capabilities.

## Running Examples

All examples can be run directly with Python:

```bash
uv run python examples/simple_pipeline.py
uv run python examples/sensor_monitoring.py
uv run python examples/data_transformation.py
```

## Examples

### 1. Simple Pipeline (`simple_pipeline.py`)

**Concepts demonstrated:**
- Basic pipeline creation
- Sequence source
- Console destination
- Async context manager usage

**What it does:**
Generates numbers 1-10 at 2 messages per second and prints them to the console.

**Run time:** ~5 seconds

### 2. Sensor Monitoring (`sensor_monitoring.py`)

**Concepts demonstrated:**
- Multiple sources
- Random data generation
- Wildcard channel patterns
- Filter transformations
- Aggregate transformations
- Multiple destinations
- Metrics collection

**What it does:**
Simulates real-time sensor monitoring for temperature and pressure:
- Generates random sensor readings at 10 Hz
- Alerts on high temperature (>28°C)
- Calculates rolling averages
- Collects and displays pipeline metrics

**Run time:** ~10 seconds

### 3. Data Transformation (`data_transformation.py`)

**Concepts demonstrated:**
- Chained transformations
- Filter transformation
- Map transformation
- Aggregate transformation
- Multiple destinations subscribing to different channels
- Result verification

**What it does:**
Processes numbers 1-100 through a transformation pipeline:
1. **Filter:** Keep only even numbers
2. **Map:** Square each number
3. **Aggregate:** Sum every 5 values

**Run time:** ~2 seconds

## Key Concepts

### Sources

- **SequenceSource:** Generates sequential numbers
- **RandomSource:** Generates random values within a range

### Transformations

- **FilterTransform:** Filter messages by predicate
- **MapTransform:** Transform message values
- **AggregateTransform:** Aggregate messages over windows

### Destinations

- **ConsoleDestination:** Print messages to stdout
- **InMemoryDestination:** Store messages in memory for analysis

### Configuration

All examples use programmatic configuration (`PipelineConfig`), but you can also use YAML configuration files. See the configuration documentation for details.

## Next Steps

- Explore the API documentation for more advanced features
- Try modifying the examples to experiment with different configurations
- Create your own custom sources, transformations, and destinations
- Check out the integration tests for more complex pipeline scenarios
