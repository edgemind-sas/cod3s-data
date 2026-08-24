"""Base class for data sources in COD3S Data Framework."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from cod3s_data.broker.base import Broker, DeliveryGuarantee
from cod3s_data.core.message import Message

if TYPE_CHECKING:
    from cod3s_data.transformations.param_store import ParameterStore

_logger = structlog.get_logger()


class BatchMode(Enum):
    """Source batch mode."""

    BATCH = "batch"  # Finite dataset, process once
    REALTIME = "realtime"  # Continuous operation
    TRANSPOSE = "transpose"  # Timestamp-based replay


class Source(ABC):
    """
    Base class for all data sources.

    Responsibilities:
    - Acquire data from external systems
    - Convert to COD3S messages
    - Publish to broker via channel
    - Handle lifecycle (start, stop)

    Subclasses implement produce() to generate messages.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        batch_mode: BatchMode = BatchMode.BATCH,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize source.

        Args:
            broker: Message broker for publishing
            channel: Target channel for messages
            batch_mode: Operating mode (BATCH, REALTIME, TRANSPOSE)
            delivery_guarantee: Message delivery guarantee
        """
        self.broker = broker
        self.channel = channel
        self.batch_mode = batch_mode
        self.delivery_guarantee = delivery_guarantee

        self._running = False
        self._paused = False
        self._message_count = 0
        self._param_stores: list[ParameterStore] = []

        # Observatory bridge (set by Framework when observatory is active)
        self._bridge: Any = None
        self._component_id: str = ""
        self._label: str = ""
        self._description: str = ""

    async def start(self) -> None:
        """
        Start producing messages.

        Calls produce() and publishes each message to broker.
        """
        self._running = True
        for store in self._param_stores:
            await store.start()
        await self._notify_state_change("idle", "running")

        try:
            async for message in self.produce():
                if not self._running:
                    break

                # Handle pause
                while self._paused and self._running:
                    await asyncio.sleep(0.1)

                if not self._running:
                    break

                # Publish message
                await self._publish_message(message)
                self._message_count += 1

        except Exception:
            raise

        finally:
            if self._running:
                self._running = False
                await self._notify_state_change("running", "completed")

    async def stop(self) -> None:
        """Stop producing messages."""
        self._running = False
        for store in self._param_stores:
            await store.stop()
        await self._notify_state_change("running", "stopped")
        await self._on_stop()

    async def pause(self) -> None:
        """Pause message production (REALTIME mode only)."""
        if self.batch_mode != BatchMode.REALTIME:
            return

        self._paused = True
        await self._notify_state_change("running", "paused")

    async def resume(self) -> None:
        """Resume message production."""
        self._paused = False
        await self._notify_state_change("paused", "running")

    async def _publish_message(self, message: Message) -> None:
        """
        Publish message to broker.

        Handles delivery guarantees.
        """
        await self.broker.publish(self.channel, message, self.delivery_guarantee)

        # Emit progress metric every 100 messages
        if self._message_count > 0 and self._message_count % 100 == 0:
            metric_msg = Message(
                key="source.messages_produced",
                timestamp=datetime.now(UTC),
                value=self._message_count,
                tags={"channel": self.channel, "source": self.__class__.__name__},
            )
            await self.broker.publish(
                f"_metrics.source.{self.__class__.__name__}.produced",
                metric_msg,
                DeliveryGuarantee.AT_MOST_ONCE,
            )

    @abstractmethod
    def produce(self) -> AsyncIterator[Message]:
        """
        Generate messages (implemented by subclass).

        Yields:
            Message instances to publish

        Examples:
            >>> async def produce(self):
            ...     for i in range(10):
            ...         yield Message(
            ...             key="value",
            ...             timestamp=datetime.now(timezone.utc),
            ...             value=i,
            ...             tags={}
            ...         )
        """
        ...

    async def _notify_state_change(self, old_state: str, new_state: str) -> None:
        """Notify Observatory bridge of state change."""
        if self._bridge is not None:
            try:
                await self._bridge.on_component_state_change(
                    self._component_id, "source", old_state, new_state
                )
            except Exception as e:
                _logger.warning("Observatory hook error", error=str(e))

    async def _on_stop(self) -> None:
        """Subclass-specific cleanup (optional)."""
        pass

    @property
    def is_running(self) -> bool:
        """Check if source is running."""
        return self._running

    @property
    def message_count(self) -> int:
        """Total messages produced."""
        return self._message_count
