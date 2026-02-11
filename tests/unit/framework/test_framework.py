"""Unit tests for framework."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from cod3s_data.config import DestinationConfig, PipelineConfig, SourceConfig, TransformConfig
from cod3s_data.core.component import ComponentState
from cod3s_data.framework import Framework
from cod3s_data.plugins import PluginError


class TestFramework:
    @pytest.mark.asyncio
    async def test_framework_start_stop(self):
        config = PipelineConfig(
            name="test_pipeline",
            sources=[],
            transformations=[],
            destinations=[],
        )
        framework = Framework(config)

        assert not framework.is_running

        await framework.start()
        assert framework.is_running

        await framework.stop()
        assert not framework.is_running

    @pytest.mark.asyncio
    async def test_framework_with_source_and_destination(self):
        config = PipelineConfig(
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="test.channel",
                    params={"start_value": 0, "end_value": 5, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        framework = Framework(config)

        await framework.start()
        assert len(framework.sources) == 1
        assert len(framework.destinations) == 1

        # Run and wait for completion
        await asyncio.wait_for(framework.run(), timeout=2.0)

        # Check messages were delivered
        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 5
        assert [m.value for m in messages] == [0, 1, 2, 3, 4]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_framework_with_transformation(self):
        config = PipelineConfig(
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="input.channel",
                    params={"start_value": 0, "end_value": 3, "rate": 1000.0},
                )
            ],
            transformations=[
                TransformConfig(
                    type="map",
                    input_channels="input.channel",
                    output_channel="output.channel",
                    params={"map_fn_code": "lambda x: x * 2"},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="output.channel", params={})
            ],
        )
        framework = Framework(config)

        await framework.start()
        assert len(framework.sources) == 1
        assert len(framework.transformations) == 1
        assert len(framework.destinations) == 1

        await asyncio.wait_for(framework.run(), timeout=2.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 3
        assert [m.value for m in messages] == [0, 2, 4]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_framework_context_manager(self):
        config = PipelineConfig(
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="test.channel",
                    params={"start_value": 0, "end_value": 2, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )

        async with Framework(config) as framework:
            assert framework.is_running
            await asyncio.wait_for(framework.run(), timeout=2.0)

        assert not framework.is_running

    @pytest.mark.asyncio
    async def test_framework_multiple_sources(self):
        config = PipelineConfig(
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="channel1",
                    params={"start_value": 0, "end_value": 2, "rate": 1000.0},
                ),
                SourceConfig(
                    type="sequence",
                    channel="channel2",
                    params={"start_value": 10, "end_value": 12, "rate": 1000.0},
                ),
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="channel*", params={})
            ],
        )
        framework = Framework(config)

        await framework.start()
        assert len(framework.sources) == 2

        await asyncio.wait_for(framework.run(), timeout=2.0)

        dest = framework.destinations[0]
        messages = dest.get_all()
        assert len(messages) == 4  # 2 messages from each source
        values = sorted([m.value for m in messages])
        assert values == [0, 1, 10, 11]

        await framework.stop()

    @pytest.mark.asyncio
    async def test_framework_graceful_shutdown(self):
        config = PipelineConfig(
            sources=[
                SourceConfig(
                    type="random",
                    channel="test.channel",
                    params={"rate": 100.0},  # REALTIME mode
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        framework = Framework(config)

        await framework.start()

        # Start running in background
        run_task = asyncio.create_task(framework.run())

        # Let it run for a bit
        await asyncio.sleep(0.2)

        # Graceful shutdown
        await framework.stop()

        # Ensure run task completes
        await asyncio.wait_for(run_task, timeout=1.0)

        assert not framework.is_running

    @pytest.mark.asyncio
    async def test_framework_broker_config(self):
        config = PipelineConfig(
            broker={"enable_metrics": False, "history_size": 50},
            sources=[],
            destinations=[],
        )
        framework = Framework(config)

        assert framework.broker.enable_metrics is False
        assert framework.broker.default_history_size == 50


class TestFrameworkPlugins:
    @pytest.mark.asyncio
    async def test_framework_loads_config_plugins(self):
        """Framework loads plugins listed in config.plugins on start()."""
        register_fn = MagicMock()

        config = PipelineConfig(
            plugins=["my.plugin"],
            sources=[],
            destinations=[],
        )
        framework = Framework(config)

        with patch("cod3s_data.framework.load_plugins", return_value=["my.plugin"]) as mock_load:
            await framework.start()
            mock_load.assert_called_once_with(["my.plugin"], framework.factory)

        await framework.stop()

    @pytest.mark.asyncio
    async def test_framework_loads_constructor_plugins(self):
        """Framework loads plugins passed via constructor arg."""
        config = PipelineConfig(sources=[], destinations=[])
        framework = Framework(config, plugins=["extra.plugin"])

        with patch("cod3s_data.framework.load_plugins", return_value=["extra.plugin"]) as mock_load:
            await framework.start()
            mock_load.assert_called_once_with(["extra.plugin"], framework.factory)

        await framework.stop()

    @pytest.mark.asyncio
    async def test_framework_merges_config_and_constructor_plugins(self):
        """Framework merges config.plugins and constructor plugins without duplication."""
        config = PipelineConfig(
            plugins=["plugin.a"],
            sources=[],
            destinations=[],
        )
        framework = Framework(config, plugins=["plugin.b", "plugin.a"])

        with patch("cod3s_data.framework.load_plugins", return_value=["plugin.a", "plugin.b"]) as mock_load:
            await framework.start()
            # plugin.a from config, plugin.b from extra (plugin.a not duplicated)
            mock_load.assert_called_once_with(["plugin.a", "plugin.b"], framework.factory)

        await framework.stop()

    @pytest.mark.asyncio
    async def test_framework_invalid_plugin_raises_on_start(self):
        """Framework with invalid plugin raises PluginError at start()."""
        config = PipelineConfig(
            plugins=["nonexistent.plugin"],
            sources=[],
            destinations=[],
        )
        framework = Framework(config)

        with pytest.raises(PluginError):
            await framework.start()


class TestComponentState:
    def test_component_state_enum(self):
        assert ComponentState.CREATED.value == "created"
        assert ComponentState.STARTING.value == "starting"
        assert ComponentState.RUNNING.value == "running"
        assert ComponentState.STOPPING.value == "stopping"
        assert ComponentState.STOPPED.value == "stopped"
