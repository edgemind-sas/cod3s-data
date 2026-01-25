"""Integration tests for full pipeline scenarios."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from cod3s_data.config import DestinationConfig, PipelineConfig, SourceConfig, TransformConfig
from cod3s_data.framework import Framework


class TestPipelineIntegration:
    @pytest.mark.asyncio
    async def test_simple_source_to_destination(self):
        """Test simple pipeline: source -> destination."""
        config = PipelineConfig(
            name="simple_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="numbers",
                    params={"start_value": 0, "end_value": 10, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="numbers",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        # Check results
        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 10
        assert [m.value for m in messages] == list(range(10))

        await framework.stop()

    @pytest.mark.asyncio
    async def test_pipeline_with_transformation(self):
        """Test pipeline: source -> transform -> destination."""
        config = PipelineConfig(
            name="transform_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="input",
                    params={"start_value": 1, "end_value": 5, "rate": 1000.0},
                )
            ],
            transformations=[
                TransformConfig(
                    type="map",
                    input_channels="input",
                    output_channel="output",
                    params={"map_fn_code": "lambda x: x ** 2"},
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="output",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 4
        assert [m.value for m in messages] == [1, 4, 9, 16]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_pipeline_with_filter(self):
        """Test pipeline with filter transformation."""
        config = PipelineConfig(
            name="filter_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="numbers",
                    params={"start_value": 0, "end_value": 10, "rate": 1000.0},
                )
            ],
            transformations=[
                TransformConfig(
                    type="filter",
                    input_channels="numbers",
                    output_channel="evens",
                    params={"predicate_code": "lambda msg: msg.value % 2 == 0"},
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="evens",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 5
        assert [m.value for m in messages] == [0, 2, 4, 6, 8]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_pipeline_with_aggregation(self):
        """Test pipeline with aggregation (count-based window)."""
        config = PipelineConfig(
            name="aggregate_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="data",
                    params={"start_value": 1, "end_value": 10, "rate": 1000.0},
                )
            ],
            transformations=[
                TransformConfig(
                    type="aggregate",
                    input_channels="data",
                    output_channel="sums",
                    params={
                        "window_type": "count",
                        "window_size": 3,
                        "aggregation_fn_code": "lambda msgs: sum(m.value for m in msgs)",
                    },
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="sums",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        # 9 messages: [1,2,3], [4,5,6], [7,8,9] -> sums: 6, 15, 24
        assert len(messages) == 3
        assert [m.value for m in messages] == [6, 15, 24]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_multiple_sources_same_channel(self):
        """Test multiple sources publishing to same channel."""
        config = PipelineConfig(
            name="multi_source_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="data",
                    params={"start_value": 0, "end_value": 3, "rate": 1000.0},
                ),
                SourceConfig(
                    type="sequence",
                    channel="data",
                    params={"start_value": 10, "end_value": 13, "rate": 1000.0},
                ),
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="data",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 6
        values = sorted([m.value for m in messages])
        assert values == [0, 1, 2, 10, 11, 12]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_multiple_destinations_wildcard(self):
        """Test multiple destinations with wildcard patterns."""
        config = PipelineConfig(
            name="multi_dest_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="sensors.temp",
                    params={"start_value": 20, "end_value": 23, "rate": 1000.0},
                ),
                SourceConfig(
                    type="sequence",
                    channel="sensors.pressure",
                    params={"start_value": 100, "end_value": 103, "rate": 1000.0},
                ),
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="sensors.temp",
                    params={},
                ),
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="sensors.**",
                    params={},
                ),
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        # First destination gets only temp
        dest1 = framework.destinations[0]
        messages1 = dest1.get_all()
        assert len(messages1) == 3
        assert all(m.value in [20, 21, 22] for m in messages1)

        # Second destination gets both temp and pressure
        dest2 = framework.destinations[1]
        messages2 = dest2.get_all()
        assert len(messages2) == 6
        values = sorted([m.value for m in messages2])
        assert values == [20, 21, 22, 100, 101, 102]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_chained_transformations(self):
        """Test pipeline with chained transformations."""
        config = PipelineConfig(
            name="chained_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="input",
                    params={"start_value": 1, "end_value": 10, "rate": 1000.0},
                )
            ],
            transformations=[
                # Filter: keep only even numbers
                TransformConfig(
                    type="filter",
                    input_channels="input",
                    output_channel="evens",
                    params={"predicate_code": "lambda msg: msg.value % 2 == 0"},
                ),
                # Map: square the even numbers
                TransformConfig(
                    type="map",
                    input_channels="evens",
                    output_channel="squared",
                    params={"map_fn_code": "lambda x: x ** 2"},
                ),
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="squared",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        # Even numbers: 2, 4, 6, 8
        # Squared: 4, 16, 36, 64
        assert len(messages) == 4
        assert [m.value for m in messages] == [4, 16, 36, 64]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_file_source_to_destination(self):
        """Test pipeline with file source."""
        # Create temporary file with test data
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"key": "test1", "value": 100}\n')
            f.write('{"key": "test2", "value": 200}\n')
            f.write('{"key": "test3", "value": 300}\n')
            temp_file = f.name

        try:
            config = PipelineConfig(
                name="file_pipeline",
                sources=[
                    SourceConfig(
                        type="file",
                        channel="file_data",
                        params={"file_path": temp_file},
                    )
                ],
                destinations=[
                    DestinationConfig(
                        type="inmemory",
                        channel_pattern="file_data",
                        params={},
                    )
                ],
            )

            framework = Framework(config)
            await framework.start()
            await asyncio.wait_for(framework.run(), timeout=3.0)

            dest = framework.destinations[0]
            messages = dest.get_all()
            assert len(messages) == 3
            assert [m.value for m in messages] == [100, 200, 300]
            assert [m.key for m in messages] == ["test1", "test2", "test3"]

            await framework.stop()

        finally:
            Path(temp_file).unlink()

    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test using framework as async context manager."""
        config = PipelineConfig(
            name="context_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="data",
                    params={"start_value": 0, "end_value": 5, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="data",
                    params={},
                )
            ],
        )

        async with Framework(config) as framework:
            assert framework.is_running
            await asyncio.wait_for(framework.run(), timeout=3.0)

        # Should be stopped after exiting context
        assert not framework.is_running

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self):
        """Test pipeline continues on transformation errors."""
        config = PipelineConfig(
            name="error_pipeline",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="numbers",
                    params={"start_value": -2, "end_value": 3, "rate": 1000.0},
                )
            ],
            transformations=[
                # This will error on negative numbers but should continue
                TransformConfig(
                    type="map",
                    input_channels="numbers",
                    output_channel="processed",
                    params={"map_fn_code": "lambda x: 10 / x"},  # Division by zero on x=0
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="processed",
                    params={},
                )
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        # Should get results for non-zero values: -2, -1, 1, 2
        # Results: -5.0, -10.0, 10.0, 5.0
        assert len(messages) == 4

        await framework.stop()

    @pytest.mark.asyncio
    async def test_metrics_channel_subscription(self):
        """Test subscribing to metrics channels."""
        config = PipelineConfig(
            name="metrics_pipeline",
            broker={"enable_metrics": True},
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="data",
                    params={"start_value": 0, "end_value": 3, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="data",
                    params={},
                ),
                # Subscribe to metrics
                DestinationConfig(
                    type="inmemory",
                    channel_pattern="_metrics.**",
                    params={},
                ),
            ],
        )

        framework = Framework(config)
        await framework.start()
        await asyncio.wait_for(framework.run(), timeout=3.0)

        # Data destination
        data_dest = framework.destinations[0]
        assert len(data_dest.get_all()) == 3

        # Metrics destination should have received metrics
        metrics_dest = framework.destinations[1]
        metrics = metrics_dest.get_all()
        assert len(metrics) > 0  # Should have some metrics

        await framework.stop()
