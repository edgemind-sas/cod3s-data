"""Main framework coordinator for COD3S Data Framework."""

import asyncio
from typing import Any

from cod3s_data.broker.in_memory import InMemoryBroker
from cod3s_data.config.factory import ComponentFactory
from cod3s_data.config.models import PipelineConfig
from cod3s_data.destinations.base import Destination
from cod3s_data.plugins import load_plugins
from cod3s_data.sources.base import Source
from cod3s_data.transformations.base import Transformation


class Framework:
    """Main framework coordinator for managing pipeline lifecycle."""

    def __init__(self, config: PipelineConfig, plugins: list[str] | None = None) -> None:
        """Initialize framework with configuration.

        Args:
            config: Pipeline configuration
            plugins: Extra plugin module paths to load (merged with config.plugins)
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

    async def start(self) -> None:
        """Start the pipeline."""
        if self._running:
            return

        self._running = True

        # Load plugins before creating components
        self._load_plugins()

        # Start broker
        await self.broker.start()

        # Create components from configuration
        for source_config in self.config.sources:
            source = self.factory.create_source(source_config)
            self.sources.append(source)

        for transform_config in self.config.transformations:
            transform = self.factory.create_transformation(transform_config)
            self.transformations.append(transform)

        for dest_config in self.config.destinations:
            destination = self.factory.create_destination(dest_config)
            self.destinations.append(destination)

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

    async def run(self) -> None:
        """Run the pipeline until completion or stopped.

        This method waits for all sources to complete.
        For REALTIME sources, this will run indefinitely until stop() is called.
        For BATCH sources, this will complete when all sources are done.
        """
        if not self._running:
            await self.start()

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

        # Cancel source tasks
        for task in self._source_tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellations
        if self._source_tasks:
            await asyncio.gather(*self._source_tasks, return_exceptions=True)

        # Stop sources
        for source in self.sources:
            await source.stop()

        # Stop transformations
        for transformation in self.transformations:
            await transformation.stop()

        # Stop destinations (flush buffers)
        for destination in self.destinations:
            await destination.stop()

        # Stop broker
        await self.broker.stop()

    async def __aenter__(self) -> "Framework":
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
