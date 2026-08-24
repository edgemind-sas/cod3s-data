"""Base classes for transformations in COD3S Data Framework."""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

from cod3s_data.broker.base import Broker, SubscriptionHandle
from cod3s_data.core.message import Message

if TYPE_CHECKING:
    from cod3s_data.transformations.param_store import ParameterStore

_logger = structlog.get_logger()


class Transformation(ABC):
    """Base class for all transformations."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
    ) -> None:
        self.broker = broker
        self.input_channels = (
            [input_channels] if isinstance(input_channels, str) else input_channels
        )
        self.output_channel = output_channel
        self._running = False
        self._subscription_handles: list[SubscriptionHandle] = []
        self._param_stores: list[ParameterStore] = []

        # Observatory bridge (set by Framework when observatory is active)
        self._bridge: Any = None
        self._component_id: str = ""
        self._label: str = ""
        self._description: str = ""

    async def start(self) -> None:
        """Start the transformation."""
        self._running = True
        # Hydrate dynamic parameters before subscribing to data inputs
        for store in self._param_stores:
            await store.start()
        for channel in self.input_channels:
            handle = self.broker.subscribe(channel, self._process_message)
            self._subscription_handles.append(handle)
        await self._notify_state_change("idle", "running")

    async def stop(self) -> None:
        """Stop the transformation."""
        self._running = False
        for handle in self._subscription_handles:
            self.broker.unsubscribe(handle)
        self._subscription_handles.clear()
        for store in self._param_stores:
            await store.stop()
        await self._notify_state_change("running", "stopped")

    async def _process_message(self, message: Message) -> None:
        """Process incoming message and publish results."""
        try:
            # Observatory: RECEIVED
            if self._bridge is not None:
                with contextlib.suppress(Exception):
                    await self._bridge.on_message_received(
                        self._component_id, "transformation", message
                    )

            results = await self.transform(message)

            # Observatory: PROCESSED (link outputs to input trace)
            if results and self._bridge is not None:
                try:
                    out_list = results if isinstance(results, list) else [results]
                    await self._bridge.on_message_processed(
                        self._component_id, "transformation", message, out_list, self.output_channel
                    )
                except Exception:
                    pass

            if results:
                for result in results if isinstance(results, list) else [results]:
                    await self.broker.publish(self.output_channel, result)
        except Exception:
            pass

    @abstractmethod
    async def transform(self, message: Message) -> Message | list[Message] | None:
        """Transform a message. Return message(s) or None to filter."""
        ...

    async def _notify_state_change(self, old_state: str, new_state: str) -> None:
        """Notify Observatory bridge of state change."""
        if self._bridge is not None:
            try:
                await self._bridge.on_component_state_change(
                    self._component_id, "transformation", old_state, new_state
                )
            except Exception as e:
                _logger.warning("Observatory hook error", error=str(e))

    @property
    def is_running(self) -> bool:
        return self._running


class StatelessTransform(Transformation):
    """Stateless transformation: 1:N message mapping."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        transform_fn: Callable[[Message], Message | list[Message] | None],
    ) -> None:
        super().__init__(broker, input_channels, output_channel)
        self.transform_fn = transform_fn

    async def transform(self, message: Message) -> Message | list[Message] | None:
        """Apply stateless transformation function."""
        return self.transform_fn(message)


class StatefulTransform(Transformation):
    """Stateful transformation: N:M multi-channel transformations."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
    ) -> None:
        super().__init__(broker, input_channels, output_channel)
        self.state: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def transform(self, message: Message) -> Message | list[Message] | None:
        """Transform with state. Override in subclasses."""
        async with self._lock:
            return await self.transform_with_state(message, self.state)

    @abstractmethod
    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Transform message using and updating state."""
        ...
