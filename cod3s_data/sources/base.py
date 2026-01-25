"""Base class for data sources in COD3S Data Framework."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator

from cod3s_data.broker.base import Broker, DeliveryGuarantee
from cod3s_data.core.message import Message


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

    async def start(self) -> None:
        """
        Start producing messages.

        Calls produce() and publishes each message to broker.
        """
        self._running = True

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
            pass

    async def stop(self) -> None:
        """Stop producing messages."""
        self._running = False
        await self._on_stop()

    async def pause(self) -> None:
        """Pause message production (REALTIME mode only)."""
        if self.batch_mode != BatchMode.REALTIME:
            return

        self._paused = True

    async def resume(self) -> None:
        """Resume message production."""
        self._paused = False

    async def _publish_message(self, message: Message) -> None:
        """
        Publish message to broker.

        Handles delivery guarantees.
        """
        await self.broker.publish(self.channel, message, self.delivery_guarantee)

        # Emit progress metric every 1000 messages
        if self._message_count > 0 and self._message_count % 1000 == 0:
            metric_msg = Message(
                key="messages_produced",
                timestamp=datetime.now(timezone.utc),
                value=self._message_count,
                tags={"channel": self.channel, "source": self.__class__.__name__},
            )
            await self.broker.publish(
                f"_metrics.source.{self.__class__.__name__}.produced",
                metric_msg,
                DeliveryGuarantee.AT_MOST_ONCE,
            )

    @abstractmethod
    async def produce(self) -> AsyncIterator[Message]:
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
        yield  # Make this a generator for type checking

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
