"""Integration tests for Observatory module."""

import asyncio

import pytest

from cod3s_data.config.models import (
    BrokerConfig,
    DestinationConfig,
    PipelineConfig,
    SourceConfig,
)
from cod3s_data.framework import Framework
from cod3s_data.observatory.config import ObservatoryConfig


class TestObservatoryIntegration:
    """Integration tests for Observatory with the framework."""

    @pytest.mark.asyncio
    async def test_framework_with_observatory_true(self):
        """Framework(config, observatory=True) should work."""
        config = PipelineConfig(name="test")
        framework = Framework(config, observatory=True)
        assert framework._bridge is not None
        assert framework._bridge._server is not None

    @pytest.mark.asyncio
    async def test_framework_with_observatory_false(self):
        """Framework(config, observatory=False) should have no bridge."""
        config = PipelineConfig(name="test")
        framework = Framework(config, observatory=False)
        assert framework._bridge is None

    @pytest.mark.asyncio
    async def test_framework_with_observatory_config(self):
        """Framework with ObservatoryConfig instance."""
        config = PipelineConfig(name="test")
        obs_config = ObservatoryConfig(port=9999, buffer_size=200)
        framework = Framework(config, observatory=obs_config)
        assert framework._bridge is not None
        assert framework._bridge._buffer.max_size == 200

    @pytest.mark.asyncio
    async def test_framework_observatory_from_pipeline_config(self):
        """Observatory enabled via PipelineConfig.observatory dict."""
        config = PipelineConfig(
            name="test",
            observatory={"enabled": True, "port": 9998},
        )
        framework = Framework(config)  # observatory param defaults to False
        assert framework._bridge is not None

    @pytest.mark.asyncio
    async def test_framework_observatory_disabled_in_pipeline_config(self):
        """Observatory disabled in PipelineConfig."""
        config = PipelineConfig(
            name="test",
            observatory={"enabled": False},
        )
        framework = Framework(config)
        assert framework._bridge is None

    @pytest.mark.asyncio
    async def test_bridge_receives_events_during_pipeline(self):
        """Bridge should capture events during a pipeline run."""
        config = PipelineConfig(
            name="test_obs",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="numbers",
                    params={"end_value": 5, "rate": 100.0},
                ),
            ],
            destinations=[
                DestinationConfig(type="console", channel_pattern="numbers"),
            ],
        )
        obs_config = ObservatoryConfig(port=9997)
        framework = Framework(config, observatory=obs_config)

        try:
            await framework.start()
            await asyncio.sleep(0.5)
        finally:
            await framework.stop()

        # The bridge should have captured events
        bridge = framework._bridge
        assert bridge is not None
        assert bridge._buffer.size > 0

    @pytest.mark.asyncio
    async def test_bridge_hooks_dont_crash_pipeline(self):
        """Even if bridge has issues, pipeline should not crash."""
        config = PipelineConfig(
            name="test_resilient",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="test",
                    params={"end_value": 3, "rate": 100.0},
                ),
            ],
            destinations=[
                DestinationConfig(type="console", channel_pattern="test"),
            ],
        )
        framework = Framework(config, observatory=True)

        # Deliberately break the bridge's WS manager to simulate an error
        framework._bridge._ws = None  # type: ignore

        try:
            # Pipeline should still complete without crashing
            await framework.start()
            await asyncio.sleep(0.5)
        finally:
            await framework.stop()


class TestObservatoryConfig:
    """Tests for Observatory config integration with PipelineConfig."""

    def test_pipeline_config_accepts_observatory(self):
        config = PipelineConfig(
            name="test",
            observatory={"enabled": True, "port": 9000},
        )
        assert config.observatory is not None
        assert config.observatory["port"] == 9000

    def test_pipeline_config_observatory_none(self):
        config = PipelineConfig(name="test")
        assert config.observatory is None
