"""Data transformation example - Chained transformations.

This example demonstrates:
- Chaining multiple transformations
- Filter -> Map -> Aggregate pipeline
- Different transformation types working together
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
    """Run data transformation pipeline."""
    config = PipelineConfig(
        name="data_transformation",
        sources=[
            # Generate sequence of numbers 1-100
            SourceConfig(
                type="sequence",
                label="Générateur 1-100",
                channel="raw.data",
                params={
                    "start_value": 1,
                    "end_value": 101,  # Generates 1-100
                    "rate": 50.0,  # 50 messages per second
                },
            )
        ],
        transformations=[
            # Step 1: Filter - Keep only even numbers
            TransformConfig(
                type="filter",
                label="Filtre pairs",
                input_channels="raw.data",
                output_channel="filtered.evens",
                params={
                    "predicate_code": "lambda msg: msg.value % 2 == 0",
                },
            ),
            # Step 2: Map - Square the even numbers
            TransformConfig(
                type="map",
                label="Carré",
                input_channels="filtered.evens",
                output_channel="mapped.squared",
                params={
                    "map_fn_code": "lambda x: x ** 2",
                },
            ),
            # Step 3: Aggregate - Sum every 5 squared values
            TransformConfig(
                type="aggregate",
                label="Somme par 5",
                input_channels="mapped.squared",
                output_channel="aggregated.sums",
                params={
                    "window_type": "count",
                    "window_size": 5,
                    "aggregation_fn_code": "lambda msgs: sum(m.value for m in msgs)",
                },
            ),
        ],
        destinations=[
            # Show raw data
            DestinationConfig(
                type="console",
                label="Log brut",
                channel_pattern="raw.data",
                params={},
            ),
            # Show filtered data
            DestinationConfig(
                type="console",
                label="Log filtrés",
                channel_pattern="filtered.evens",
                params={},
            ),
            # Show mapped data
            DestinationConfig(
                type="console",
                label="Log carrés",
                channel_pattern="mapped.squared",
                params={},
            ),
            # Show aggregated results
            DestinationConfig(
                type="console",
                label="Log agrégats",
                channel_pattern="aggregated.sums",
                params={},
            ),
            # Collect final results for verification
            DestinationConfig(
                type="inmemory",
                label="Collecteur résultats",
                channel_pattern="aggregated.sums",
                params={},
            ),
        ],
    )

    print("Starting data transformation pipeline...")
    print("\nPipeline stages:")
    print("  1. Generate: Numbers 1-100")
    print("  2. Filter:   Keep only even numbers (2, 4, 6, ...)")
    print("  3. Map:      Square each number (4, 16, 36, ...)")
    print("  4. Aggregate: Sum every 5 values")
    print()

    async with Framework(config) as framework:
        await framework.run()

    # Show final results
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    results_dest = framework.destinations[4]  # InMemoryDestination
    results = results_dest.get_all()

    print(f"\nGenerated {len(results)} aggregate values:")
    for i, msg in enumerate(results, 1):
        print(f"  Aggregate {i}: {msg.value}")

    # Verify the transformation pipeline worked correctly
    print("\nVerification:")
    print("  - Input: 1-100 (100 numbers)")
    print("  - After filter (evens): 50 numbers")
    print("  - After map (squared): 50 numbers")
    print(f"  - After aggregate (window=5): {len(results)} sums")

    print("\nPipeline completed!")


if __name__ == "__main__":
    asyncio.run(main())
