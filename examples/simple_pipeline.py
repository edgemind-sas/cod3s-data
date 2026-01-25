"""Simple pipeline example - Generate numbers and print them.

This example demonstrates the basic concepts of the COD3S Data Framework:
- Creating a pipeline programmatically
- Using a sequence source to generate data
- Using a console destination to output data
"""

import asyncio

from cod3s_data.config import DestinationConfig, PipelineConfig, SourceConfig
from cod3s_data.framework import Framework


async def main():
    """Run simple pipeline."""
    # Create pipeline configuration
    config = PipelineConfig(
        name="simple_pipeline",
        sources=[
            SourceConfig(
                type="sequence",
                channel="numbers",
                params={
                    "start_value": 1,
                    "end_value": 11,  # Generates 1-10
                    "rate": 2.0,  # 2 messages per second
                },
            )
        ],
        destinations=[
            DestinationConfig(
                type="console",
                channel_pattern="numbers",
                params={},
            )
        ],
    )

    # Run the pipeline using async context manager
    print("Starting simple pipeline...")
    print("Generating numbers 1-10 at 2 msg/s\n")

    async with Framework(config) as framework:
        await framework.run()

    print("\nPipeline completed!")


if __name__ == "__main__":
    asyncio.run(main())
