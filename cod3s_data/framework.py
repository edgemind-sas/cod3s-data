"""Main framework coordinator for COD3S Data Framework."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

import structlog

from cod3s_data.broker.in_memory import InMemoryBroker
from cod3s_data.config.factory import ComponentFactory
from cod3s_data.config.models import PipelineConfig
from cod3s_data.destinations.base import Destination
from cod3s_data.plugins import load_plugins
from cod3s_data.sources.base import Source
from cod3s_data.transformations.base import Transformation

_logger = structlog.get_logger()


class PipelineState(str, Enum):
    """Pipeline lifecycle states."""

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class Framework:
    """Main framework coordinator for managing pipeline lifecycle."""

    def __init__(
        self,
        config: PipelineConfig,
        plugins: list[str] | None = None,
        observatory: bool | Any = False,
    ) -> None:
        """Initialize framework with configuration.

        Args:
            config: Pipeline configuration
            plugins: Extra plugin module paths to load (merged with config.plugins)
            observatory: Enable Observatory. Pass True for defaults,
                or an ObservatoryConfig instance for custom settings.
                Pass False (default) to disable.
        """
        self.config = config
        self._extra_plugins = plugins or []
        self.broker = InMemoryBroker(
            enable_metrics=config.broker.enable_metrics,
            default_history_size=config.broker.history_size,
        )
        self.factory = ComponentFactory(self.broker)

        self.sources: list[Source] = []
        self.transformations: list[Transformation] = []
        self.destinations: list[Destination] = []
        self._source_tasks: list[asyncio.Task[Any]] = []
        self._running = False

        # Pipeline state for interactive mode
        self._pipeline_state = PipelineState.IDLE
        self._interactive = False
        self._pipeline_monitor_task: asyncio.Task[Any] | None = None

        # Observatory bridge (None when disabled)
        self._bridge: Any = None
        self._init_observatory(observatory)

    def _init_observatory(self, observatory: bool | Any) -> None:
        """Initialize the Observatory bridge if requested."""
        # Resolve observatory setting: constructor param takes priority,
        # then fall back to config.observatory section
        if observatory is False and self.config.observatory is not None:
            obs_dict = self.config.observatory
            if obs_dict.get("enabled", False):
                observatory = True

        if not observatory:
            return

        try:
            from cod3s_data.observatory import create_observatory
            from cod3s_data.observatory.config import ObservatoryConfig

            if observatory is True:
                # Use config from YAML/dict if available, otherwise defaults
                if self.config.observatory is not None:
                    obs_config = ObservatoryConfig.model_validate(self.config.observatory)
                else:
                    obs_config = ObservatoryConfig()
            elif isinstance(observatory, ObservatoryConfig):
                obs_config = observatory
            else:
                obs_config = ObservatoryConfig()

            self._bridge = create_observatory(config=obs_config)
            self._bridge._framework = self
            self._interactive = obs_config.interactive
        except ImportError:
            raise ImportError(
                "Observatory requires extra dependencies. "
                "Install with: pip install cod3s-data[observatory]"
            )

    def _load_plugins(self) -> list[str]:
        """Load plugins from config and constructor argument.

        Returns:
            List of successfully loaded plugin module paths
        """
        all_plugins = list(self.config.plugins) + [
            p for p in self._extra_plugins if p not in self.config.plugins
        ]
        if not all_plugins:
            return []
        return load_plugins(all_plugins, self.factory)

    def _create_components(self) -> None:
        """Create pipeline components from configuration.

        Components are created but not started yet.
        """
        for i, source_config in enumerate(self.config.sources):
            source = self.factory.create_source(source_config)
            source._bridge = self._bridge
            source._component_id = f"src-{i}"
            source._label = source_config.label or ""
            source._description = source_config.description or ""
            self.sources.append(source)

        for i, transform_config in enumerate(self.config.transformations):
            transform = self.factory.create_transformation(transform_config)
            transform._bridge = self._bridge
            transform._component_id = f"tfm-{i}"
            transform._label = transform_config.label or ""
            transform._description = transform_config.description or ""
            self.transformations.append(transform)

        for i, dest_config in enumerate(self.config.destinations):
            destination = self.factory.create_destination(dest_config)
            destination._bridge = self._bridge
            destination._component_id = f"dst-{i}"
            destination._label = dest_config.label or ""
            destination._description = dest_config.description or ""
            self.destinations.append(destination)

    async def _start_pipeline(self) -> None:
        """Start the pipeline components (broker, destinations, transformations, sources).

        Can be called from start() or from handle_pipeline_command().
        """
        # Reset component state for restart
        for source in self.sources:
            source._running = False
            source._message_count = 0
        for transformation in self.transformations:
            transformation._running = False
            transformation._subscription_handles.clear()
        for destination in self.destinations:
            destination._running = False
            destination._subscription_handle = None
            destination._writer_task = None

        self._source_tasks.clear()

        # Start broker
        await self.broker.start()

        # Pass bridge reference to broker
        self.broker._bridge = self._bridge

        # Start destinations (subscribe first)
        for destination in self.destinations:
            await destination.start()

        # Start transformations
        for transformation in self.transformations:
            await transformation.start()

        # Start sources as tasks (they run asynchronously)
        for source in self.sources:
            task = asyncio.create_task(source.start())
            self._source_tasks.append(task)

        self._pipeline_state = PipelineState.RUNNING
        await self._broadcast_pipeline_state()

        # In interactive mode, monitor source tasks for natural completion (batch sources)
        if self._interactive:
            self._pipeline_monitor_task = asyncio.create_task(self._monitor_pipeline())

    async def _monitor_pipeline(self) -> None:
        """Monitor source tasks and transition to STOPPED when all complete naturally."""
        try:
            if self._source_tasks:
                await asyncio.gather(*self._source_tasks)
            # All sources finished naturally (batch mode)
            if self._pipeline_state == PipelineState.RUNNING:
                # Stop remaining components (transformations, destinations, broker)
                for transformation in self.transformations:
                    if transformation._running:
                        await transformation.stop()
                for destination in self.destinations:
                    if destination._running:
                        await destination.stop()
                await self.broker.stop()
                self._pipeline_state = PipelineState.STOPPED
                await self._broadcast_pipeline_state()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            _logger.debug("Pipeline monitor error", error=str(e))

    async def _stop_pipeline(self) -> None:
        """Stop pipeline components without touching the Observatory."""
        self._pipeline_state = PipelineState.STOPPING
        await self._broadcast_pipeline_state()

        # Cancel the monitor task first
        if self._pipeline_monitor_task and not self._pipeline_monitor_task.done():
            self._pipeline_monitor_task.cancel()
            try:
                await self._pipeline_monitor_task
            except asyncio.CancelledError:
                pass
            self._pipeline_monitor_task = None

        # Cancel source tasks
        for task in self._source_tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellations
        if self._source_tasks:
            await asyncio.gather(*self._source_tasks, return_exceptions=True)

        # Stop sources
        for source in self.sources:
            if source._running:
                await source.stop()

        # Stop transformations
        for transformation in self.transformations:
            if transformation._running:
                await transformation.stop()

        # Stop destinations (flush buffers)
        for destination in self.destinations:
            if destination._running:
                await destination.stop()

        # Stop broker
        await self.broker.stop()

        self._source_tasks.clear()
        self._pipeline_state = PipelineState.STOPPED
        await self._broadcast_pipeline_state()

    async def handle_pipeline_command(self, command: str) -> dict[str, str]:
        """Handle a pipeline control command (from Observatory WS).

        Args:
            command: One of "start", "stop", "restart"

        Returns:
            Dict with "status" and "state" keys
        """
        try:
            if command == "start":
                if self._pipeline_state in (PipelineState.IDLE, PipelineState.STOPPED):
                    await self._start_pipeline()
                    return {"status": "ok", "state": self._pipeline_state.value}
                return {
                    "status": "error",
                    "state": self._pipeline_state.value,
                    "message": f"Cannot start from state {self._pipeline_state.value}",
                }

            if command == "stop":
                if self._pipeline_state == PipelineState.RUNNING:
                    await self._stop_pipeline()
                    return {"status": "ok", "state": self._pipeline_state.value}
                return {
                    "status": "error",
                    "state": self._pipeline_state.value,
                    "message": f"Cannot stop from state {self._pipeline_state.value}",
                }

            if command == "restart":
                if self._pipeline_state == PipelineState.RUNNING:
                    await self._stop_pipeline()
                await self._start_pipeline()
                return {"status": "ok", "state": self._pipeline_state.value}

            return {"status": "error", "state": self._pipeline_state.value, "message": f"Unknown command: {command}"}
        except Exception as e:
            self._pipeline_state = PipelineState.ERROR
            await self._broadcast_pipeline_state()
            return {"status": "error", "state": self._pipeline_state.value, "message": str(e)}

    async def _broadcast_pipeline_state(self) -> None:
        """Broadcast pipeline state to all Observatory WS clients."""
        if self._bridge is not None:
            try:
                await self._bridge._ws.broadcast_event(
                    "pipeline.state", {"state": self._pipeline_state.value}
                )
            except Exception as e:
                _logger.debug("Failed to broadcast pipeline state", error=str(e))

    async def _broadcast_topology_snapshot(self) -> None:
        """Broadcast component topology to Observatory before pipeline starts."""
        if self._bridge is None:
            return

        for source in self.sources:
            try:
                await self._bridge.on_component_state_change(
                    source._component_id, "source", "none", "created"
                )
            except Exception:
                pass

        for transformation in self.transformations:
            try:
                await self._bridge.on_component_state_change(
                    transformation._component_id, "transformation", "none", "created"
                )
            except Exception:
                pass

        for destination in self.destinations:
            try:
                await self._bridge.on_component_state_change(
                    destination._component_id, "destination", "none", "created"
                )
            except Exception:
                pass

    async def start(self) -> None:
        """Start the pipeline."""
        if self._running:
            return

        self._running = True

        # Start Observatory server if bridge is active
        if self._bridge is not None:
            await self._bridge.start()

        # Load plugins before creating components
        self._load_plugins()

        # Create components from configuration
        self._create_components()

        # Broadcast topology so UI can see components before pipeline runs
        await self._broadcast_topology_snapshot()

        if self._interactive:
            # In interactive mode: stay IDLE, wait for WS command to start
            self._pipeline_state = PipelineState.IDLE
            await self._broadcast_pipeline_state()
            return

        # Normal mode: start pipeline immediately
        await self._start_pipeline()

    async def run(self) -> None:
        """Run the pipeline until completion or stopped.

        This method waits for all sources to complete.
        For REALTIME sources, this will run indefinitely until stop() is called.
        For BATCH sources, this will complete when all sources are done.
        """
        if not self._running:
            await self.start()

        if self._interactive:
            # In interactive mode, keep alive until cancelled
            # Pipeline is started/stopped via WS commands
            try:
                while self._running:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            return

        # Wait for all source tasks to complete
        try:
            await asyncio.gather(*self._source_tasks)
        except asyncio.CancelledError:
            # Graceful cancellation
            pass

    async def stop(self) -> None:
        """Stop the pipeline gracefully."""
        if not self._running:
            return

        self._running = False

        # Stop pipeline if it's running
        if self._pipeline_state == PipelineState.RUNNING:
            await self._stop_pipeline()
        else:
            # Cancel any remaining source tasks
            for task in self._source_tasks:
                if not task.done():
                    task.cancel()
            if self._source_tasks:
                await asyncio.gather(*self._source_tasks, return_exceptions=True)

        # Stop Observatory
        if self._bridge is not None:
            await self._bridge.stop()

    async def __aenter__(self) -> Framework:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

    @property
    def is_running(self) -> bool:
        """Check if framework is running."""
        return self._running
