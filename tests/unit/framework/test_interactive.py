"""Unit tests for interactive pipeline mode."""

import asyncio

import pytest

from cod3s_data.config.models import (
    DestinationConfig,
    PipelineConfig,
    SourceConfig,
)
from cod3s_data.framework import Framework, PipelineState
from cod3s_data.observatory.config import ObservatoryConfig


class TestPipelineState:
    """Tests for PipelineState enum."""

    def test_pipeline_state_values(self):
        assert PipelineState.IDLE.value == "idle"
        assert PipelineState.RUNNING.value == "running"
        assert PipelineState.STOPPING.value == "stopping"
        assert PipelineState.STOPPED.value == "stopped"
        assert PipelineState.ERROR.value == "error"

    def test_pipeline_state_is_str(self):
        assert isinstance(PipelineState.IDLE, str)
        assert PipelineState.RUNNING == "running"


class TestInteractiveMode:
    """Tests for interactive pipeline mode."""

    @pytest.mark.asyncio
    async def test_interactive_mode_stays_idle_after_start(self):
        """In interactive mode, start() should not launch the pipeline."""
        config = PipelineConfig(
            name="test_interactive",
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
        obs_config = ObservatoryConfig(port=9990, interactive=True)
        framework = Framework(config, observatory=obs_config)

        assert framework._interactive is True
        assert framework._pipeline_state == PipelineState.IDLE

        await framework.start()

        # Pipeline should stay IDLE, components created but not running
        assert framework._pipeline_state == PipelineState.IDLE
        assert len(framework.sources) == 1
        assert len(framework.destinations) == 1
        assert len(framework._source_tasks) == 0

        await framework.stop()

    @pytest.mark.asyncio
    async def test_handle_start_command_from_idle(self):
        """handle_pipeline_command('start') from IDLE should start pipeline."""
        config = PipelineConfig(
            name="test_cmd_start",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="test.channel",
                    params={"start_value": 0, "end_value": 3, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        obs_config = ObservatoryConfig(port=9991, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()
        assert framework._pipeline_state == PipelineState.IDLE

        result = await framework.handle_pipeline_command("start")
        assert result["status"] == "ok"
        assert result["state"] == "running"
        assert framework._pipeline_state == PipelineState.RUNNING
        assert len(framework._source_tasks) > 0

        await framework.stop()

    @pytest.mark.asyncio
    async def test_handle_stop_command_from_running(self):
        """handle_pipeline_command('stop') from RUNNING should stop pipeline."""
        config = PipelineConfig(
            name="test_cmd_stop",
            sources=[
                SourceConfig(
                    type="random",
                    channel="test.channel",
                    params={"rate": 100.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        obs_config = ObservatoryConfig(port=9992, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()
        await framework.handle_pipeline_command("start")
        assert framework._pipeline_state == PipelineState.RUNNING

        # Let it run briefly
        await asyncio.sleep(0.2)

        result = await framework.handle_pipeline_command("stop")
        assert result["status"] == "ok"
        assert result["state"] == "stopped"
        assert framework._pipeline_state == PipelineState.STOPPED

        await framework.stop()

    @pytest.mark.asyncio
    async def test_handle_restart_command(self):
        """handle_pipeline_command('restart') should stop then start."""
        config = PipelineConfig(
            name="test_cmd_restart",
            sources=[
                SourceConfig(
                    type="random",
                    channel="test.channel",
                    params={"rate": 100.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        obs_config = ObservatoryConfig(port=9993, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()
        await framework.handle_pipeline_command("start")
        await asyncio.sleep(0.2)

        result = await framework.handle_pipeline_command("restart")
        assert result["status"] == "ok"
        assert result["state"] == "running"
        assert framework._pipeline_state == PipelineState.RUNNING

        await framework.stop()

    @pytest.mark.asyncio
    async def test_start_from_invalid_state_returns_error(self):
        """start command when already running should return error."""
        config = PipelineConfig(
            name="test_invalid_start",
            sources=[
                SourceConfig(
                    type="random",
                    channel="test.channel",
                    params={"rate": 100.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        obs_config = ObservatoryConfig(port=9994, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()
        await framework.handle_pipeline_command("start")

        result = await framework.handle_pipeline_command("start")
        assert result["status"] == "error"

        await framework.stop()

    @pytest.mark.asyncio
    async def test_stop_from_idle_returns_error(self):
        """stop command when idle should return error."""
        config = PipelineConfig(name="test_invalid_stop")
        obs_config = ObservatoryConfig(port=9995, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()
        assert framework._pipeline_state == PipelineState.IDLE

        result = await framework.handle_pipeline_command("stop")
        assert result["status"] == "error"

        await framework.stop()

    @pytest.mark.asyncio
    async def test_non_interactive_mode_starts_pipeline_immediately(self):
        """Default mode (non-interactive) should start pipeline as before."""
        config = PipelineConfig(
            name="test_non_interactive",
            sources=[
                SourceConfig(
                    type="sequence",
                    channel="test.channel",
                    params={"start_value": 0, "end_value": 3, "rate": 1000.0},
                )
            ],
            destinations=[
                DestinationConfig(type="inmemory", channel_pattern="test.channel", params={})
            ],
        )
        obs_config = ObservatoryConfig(port=9996, interactive=False)
        framework = Framework(config, observatory=obs_config)

        await framework.start()

        # Pipeline should be running immediately
        assert framework._pipeline_state == PipelineState.RUNNING
        assert len(framework._source_tasks) > 0

        await asyncio.wait_for(framework.run(), timeout=2.0)
        await framework.stop()

    @pytest.mark.asyncio
    async def test_interactive_run_loop(self):
        """In interactive mode, run() should loop until stop is called."""
        config = PipelineConfig(name="test_run_loop")
        obs_config = ObservatoryConfig(port=9989, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()

        # Start run() in background
        run_task = asyncio.create_task(framework.run())
        await asyncio.sleep(0.3)

        # run() should still be running (not completed)
        assert not run_task.done()

        # Stop should unblock run()
        await framework.stop()
        await asyncio.wait_for(run_task, timeout=2.0)


class TestBridgePipelineControl:
    """Tests for bridge pipeline control methods."""

    @pytest.mark.asyncio
    async def test_bridge_get_pipeline_state(self):
        """Bridge should report pipeline state from framework."""
        config = PipelineConfig(name="test_bridge_state")
        obs_config = ObservatoryConfig(port=9988, interactive=True)
        framework = Framework(config, observatory=obs_config)

        bridge = framework._bridge
        assert bridge is not None
        assert bridge.get_pipeline_state() == "idle"

        await framework.start()
        assert bridge.get_pipeline_state() == "idle"

        await framework.handle_pipeline_command("start")
        assert bridge.get_pipeline_state() == "running"

        await framework.stop()

    @pytest.mark.asyncio
    async def test_bridge_start_pipeline(self):
        """Bridge start_pipeline should delegate to framework."""
        config = PipelineConfig(name="test_bridge_start")
        obs_config = ObservatoryConfig(port=9987, interactive=True)
        framework = Framework(config, observatory=obs_config)

        await framework.start()

        bridge = framework._bridge
        result = await bridge.start_pipeline()
        assert result["status"] == "ok"
        assert framework._pipeline_state == PipelineState.RUNNING

        await framework.stop()

    @pytest.mark.asyncio
    async def test_bridge_no_framework_returns_error(self):
        """Bridge without framework reference should return error."""
        from cod3s_data.observatory.bridge import ObservatoryBridge
        from cod3s_data.observatory.buffer import EventBuffer
        from cod3s_data.observatory.sampler import MessageSampler
        from cod3s_data.observatory.websocket_manager import WebSocketManager

        bridge = ObservatoryBridge(
            event_buffer=EventBuffer(max_size=100, memory_limit_bytes=10 * 1024 * 1024),
            sampler=MessageSampler(),
            websocket_manager=WebSocketManager(),
        )
        # _framework is None by default
        result = await bridge.start_pipeline()
        assert result["status"] == "error"
        assert bridge.get_pipeline_state() == "unknown"
