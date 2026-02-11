"""Sensor monitoring example - Real-time sensor data processing.

This example demonstrates:
- Multiple sensor sources (temperature, pressure)
- Wildcard channel patterns for routing
- Filtering out-of-range values
- Aggregating sensor readings over time windows
- Multiple destinations for different data streams
"""

import asyncio

from cod3s_data.config import (
    DestinationConfig,
    PipelineConfig,
    SourceConfig,
    TransformConfig,
)
from cod3s_data.framework import Framework


async def main():
    """Run sensor monitoring pipeline."""
    config = PipelineConfig(
        name="sensor_monitoring",
        broker={"enable_metrics": True, "history_size": 1000},
        sources=[
            # Temperature sensor - generates random values around 25°C
            SourceConfig(
                type="random",
                channel="sensors.temperature.room1",
                params={
                    "rate": 10.0,  # 10 Hz
                    "max_messages": 100,  # Run for 10 seconds
                    "min_value": 20.0,
                    "max_value": 30.0,
                },
            ),
            # Pressure sensor - generates random values around 1013 hPa
            SourceConfig(
                type="random",
                channel="sensors.pressure.room1",
                params={
                    "rate": 10.0,  # 10 Hz
                    "max_messages": 100,
                    "min_value": 1000.0,
                    "max_value": 1030.0,
                },
            ),
        ],
        transformations=[
            # Filter: Alert on high temperature (>28°C)
            TransformConfig(
                type="filter",
                input_channels="sensors.temperature.**",
                output_channel="alerts.high_temp",
                params={
                    "predicate_code": "lambda msg: msg.value > 28.0",
                },
            ),
            # Aggregate: Calculate average temperature every 10 readings
            TransformConfig(
                type="aggregate",
                input_channels="sensors.temperature.**",
                output_channel="stats.temperature.avg",
                params={
                    "window_type": "count",
                    "window_size": 10,
                    "aggregation_fn_code": "lambda msgs: sum(m.value for m in msgs) / len(msgs)",
                },
            ),
            # Aggregate: Calculate average pressure every 10 readings
            TransformConfig(
                type="aggregate",
                input_channels="sensors.pressure.**",
                output_channel="stats.pressure.avg",
                params={
                    "window_type": "count",
                    "window_size": 10,
                    "aggregation_fn_code": "lambda msgs: sum(m.value for m in msgs) / len(msgs)",
                },
            ),
        ],
        destinations=[
            # Log all raw sensor data
            DestinationConfig(
                type="console",
                channel_pattern="sensors.**",
                params={},
            ),
            # Log temperature alerts
            DestinationConfig(
                type="console",
                channel_pattern="alerts.**",
                params={},
            ),
            # Log statistics
            DestinationConfig(
                type="console",
                channel_pattern="stats.**",
                params={},
            ),
            # Store metrics in memory for analysis
            DestinationConfig(
                type="inmemory",
                channel_pattern="_metrics.**",
                params={},
            ),
        ],
    )

    print("Starting sensor monitoring pipeline...")
    print("Monitoring temperature and pressure sensors")
    print("  - Temperature range: 20-30°C (alerts if >28°C)")
    print("  - Pressure range: 1000-1030 hPa")
    print("  - Sample rate: 10 Hz for 10 seconds")
    print("\nPress Ctrl+C to stop\n")

    async with Framework(config) as framework:
        try:
            await framework.run()
        except KeyboardInterrupt:
            print("\n\nStopping pipeline...")

    # Print metrics
    print("\n" + "=" * 60)
    print("PIPELINE METRICS")
    print("=" * 60)

    metrics_dest = framework.destinations[3]
    metrics = metrics_dest.get_all()

    if metrics:
        print(f"Total metrics collected: {len(metrics)}")
        print("\nMetric summary:")
        for metric in metrics[:10]:  # Show first 10 metrics
            print(f"  {metric.key}: {metric.value} (tags: {metric.tags})")

    print("\nPipeline completed!")


if __name__ == "__main__":
    asyncio.run(main())
