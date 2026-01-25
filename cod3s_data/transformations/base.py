"""Base classes for transformations in COD3S Data Framework."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable

from cod3s_data.broker.base import Broker, SubscriptionHandle
from cod3s_data.core.message import Message


class Transformation(ABC):
    """Base class for all transformations."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
    ) -> None:
        self.broker = broker
        self.input_channels = [input_channels] if isinstance(input_channels, str) else input_channels
        self.output_channel = output_channel
        self._running = False
        self._subscription_handles: list[SubscriptionHandle] = []

    async def start(self) -> None:
        """Start the transformation."""
        self._running = True
        for channel in self.input_channels:
            handle = self.broker.subscribe(channel, self._process_message)
            self._subscription_handles.append(handle)

    async def stop(self) -> None:
        """Stop the transformation."""
        self._running = False
        for handle in self._subscription_handles:
            self.broker.unsubscribe(handle)
        self._subscription_handles.clear()

    async def _process_message(self, message: Message) -> None:
        """Process incoming message and publish results."""
        try:
            results = await self.transform(message)
            if results:
                for result in results if isinstance(results, list) else [results]:
                    await self.broker.publish(self.output_channel, result)
        except Exception:
            pass

    @abstractmethod
    async def transform(self, message: Message) -> Message | list[Message] | None:
        """Transform a message. Return message(s) or None to filter."""
        ...

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
