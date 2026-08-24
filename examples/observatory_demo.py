"""Observatory demo - Pipeline with real-time Observatory monitoring.

This example demonstrates:
- Running a pipeline with Observatory enabled
- Accessing the Observatory web UI at http://127.0.0.1:8765
- Viewing captured events in the buffer
- Querying the REST API for topology and health

Usage:
    uv run python examples/observatory_demo.py

Then open http://127.0.0.1:8765 in your browser while it runs.
You can also query:
    curl http://127.0.0.1:8765/api/health
    curl http://127.0.0.1:8765/api/topology
"""

import asyncio

from cod3s_data.config import DestinationConfig, PipelineConfig, SourceConfig
from cod3s_data.framework import Framework
from cod3s_data.observatory.config import ObservatoryConfig


async def main():
    config = PipelineConfig(
        name="observatory_demo",
        broker={"enable_metrics": True, "history_size": 100},
        sources=[
            SourceConfig(
                type="random",
                label="Capteur Température",
                channel="sensors.temperature",
                params={
                    "rate": 5.0,
                    "max_messages": 50,
                    "min_value": 18.0,
                    "max_value": 30.0,
                },
            ),
            SourceConfig(
                type="sequence",
                label="Compteur séquentiel",
                channel="counters.seq",
                params={
                    "start_value": 1,
                    "end_value": 21,
                    "rate": 2.0,
                },
            ),
        ],
        destinations=[
            DestinationConfig(type="console", label="Log Capteurs", channel_pattern="sensors.**"),
            DestinationConfig(type="console", label="Log Compteurs", channel_pattern="counters.**"),
        ],
    )

    obs_config = ObservatoryConfig(port=8765, buffer_size=500)
    framework = Framework(config, observatory=obs_config)

    print("=== COD3S Observatory Demo ===")
    print()
    print("Observatory will start on http://127.0.0.1:8765")
    print()
    print("Endpoints to test:")
    print("  - Web UI:    http://127.0.0.1:8765")
    print("  - Health:    http://127.0.0.1:8765/api/health")
    print("  - Topology:  http://127.0.0.1:8765/api/topology")
    print("  - Debug:     http://127.0.0.1:8765/api/debug/state")
    print("  - WebSocket: ws://127.0.0.1:8765/ws")
    print()

    try:
        await framework.start()
        print("Pipeline started! Running sources...\n")
        await framework.run()
    finally:
        # Show what the Observatory captured
        bridge = framework._bridge
        buffer = bridge._buffer

        print(f"\n{'=' * 60}")
        print(f"Observatory captured {buffer.size} events")
        print(f"Estimated memory: {buffer.estimated_memory_mb:.2f} MB")
        print(f"{'=' * 60}")

        # Show event type breakdown
        from collections import Counter

        events = buffer.get_recent(limit=buffer.size)
        type_counts = Counter(e["type"] for e in events)
        print("\nEvent breakdown:")
        for etype, count in type_counts.most_common():
            print(f"  {etype:20s} : {count}")

        # Show recent messages
        print("\nLast 5 message events:")
        msg_events = [e for e in events if e["type"] == "message"]
        for e in msg_events[-5:]:
            d = e["data"]
            print(f"  [{d['channel']}] key={d.get('key', '?')} subs={d.get('subscriber_count', 0)}")

        # Show component state changes
        print("\nComponent state changes:")
        state_events = [e for e in events if e["type"] == "component_state"]
        for e in state_events:
            d = e["data"]
            print(
                f"  {d['component_id']:8s} ({d['component_type']:13s}) {d['old_state']} -> {d['new_state']}"
            )

        await framework.stop()

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
