"""
Custom Python Pipeline Example

This shows how to use the framework programmatically from Python
instead of YAML configuration. Use this when you need more control
or want to integrate with existing Python code.
"""

import asyncio

from cod3s_data.broker.in_memory import InMemoryBroker
from cod3s_data.destinations.core import ConsoleDestination, InMemoryDestination
from cod3s_data.sources.test_sources import RandomSource
from cod3s_data.transformations.builtin import AggregateTransform, FilterTransform


async def main():
    """Run a custom pipeline using Python API."""

    print("Starting Custom Python Pipeline")
    print("=" * 60)

    # 1. Create broker
    broker = InMemoryBroker(
        default_history_size=100,
        enable_metrics=True,
    )
    await broker.start()

    # 2. Create source - simulate temperature sensor
    temp_source = RandomSource(
        broker=broker,
        channel="sensors.temperature",
        rate=5.0,  # 5 readings per second
        min_value=18.0,
        max_value=28.0,
        max_messages=25,  # Run for 5 seconds
    )

    # 3. Create transformations
    # Filter: Alert on high temperature
    high_temp_filter = FilterTransform(
        broker=broker,
        input_channels="sensors.temperature",
        output_channel="alerts.high_temp",
        predicate=lambda msg: msg.value > 25.0,
    )

    # Aggregate: Calculate average every 5 readings
    avg_aggregator = AggregateTransform(
        broker=broker,
        input_channels="sensors.temperature",
        output_channel="stats.avg_temp",
        window_type="count",
        window_size=5,
        aggregation_fn=lambda msgs: round(
            sum(m.value for m in msgs) / len(msgs), 2
        ),
    )

    # 4. Create destinations
    # Console for raw readings
    console_dest = ConsoleDestination(
        broker=broker,
        channel_pattern="sensors.**",
    )

    # Console for alerts
    alert_dest = ConsoleDestination(
        broker=broker,
        channel_pattern="alerts.**",
    )

    # InMemory for statistics (so we can analyze them)
    stats_dest = InMemoryDestination(
        broker=broker,
        channel_pattern="stats.**",
    )

    # 5. Start everything (order matters!)
    print("\n📊 Starting pipeline components...")

    # Start destinations first (they need to subscribe)
    await console_dest.start()
    await alert_dest.start()
    await stats_dest.start()

    # Start transformations
    await high_temp_filter.start()
    await avg_aggregator.start()

    # Start source (this will block until done)
    print("🌡️  Generating temperature readings...\n")
    await temp_source.start()

    # 6. Wait a bit for final messages to process
    await asyncio.sleep(0.5)

    # 7. Analyze results
    print("\n" + "=" * 60)
    print("📈 PIPELINE RESULTS")
    print("=" * 60)

    stats_messages = stats_dest.get_all()
    print(f"\n✓ Captured {len(stats_messages)} average calculations:")
    for i, msg in enumerate(stats_messages, 1):
        print(f"  {i}. Average: {msg.value}°C")

    # Get broker metrics
    metrics = broker.get_metrics()
    print("\n📊 Broker Metrics:")
    print(f"  • Messages published: {metrics['publish_count']}")
    print(f"  • Callbacks executed: {metrics['notify_count']}")
    print(f"  • Active subscriptions: {metrics['subscription_count']}")
    print(f"  • Channels used: {metrics['channel_count']}")

    # 8. Cleanup
    await console_dest.stop()
    await alert_dest.stop()
    await stats_dest.stop()
    await high_temp_filter.stop()
    await avg_aggregator.stop()
    await temp_source.stop()
    await broker.stop()

    print("\n✓ Pipeline completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
