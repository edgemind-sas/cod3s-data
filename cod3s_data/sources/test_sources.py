"""Test data sources for COD3S Data Framework."""

import asyncio
import random
from datetime import datetime, timezone
from typing import AsyncIterator

from cod3s_data.broker.base import Broker, DeliveryGuarantee
from cod3s_data.core.message import Message
from cod3s_data.sources.base import BatchMode, Source


class RandomSource(Source):
    """
    Generate random values (REALTIME mode).

    Runs continuously until stopped.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        rate: float = 1.0,  # Messages per second
        min_value: float = 0.0,
        max_value: float = 100.0,
        key: str = "random_value",
        max_messages: int | None = None,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize random source.

        Args:
            broker: Message broker
            channel: Target channel
            rate: Messages per second
            min_value: Minimum random value
            max_value: Maximum random value
            key: Message key
            max_messages: Maximum messages to generate (None = unlimited)
            delivery_guarantee: Delivery guarantee
        """
        batch_mode = BatchMode.BATCH if max_messages is not None else BatchMode.REALTIME
        super().__init__(broker, channel, batch_mode, delivery_guarantee)
        self.rate = rate
        self.min_value = min_value
        self.max_value = max_value
        self.key = key
        self.max_messages = max_messages

    async def produce(self) -> AsyncIterator[Message]:
        """Generate random values at specified rate."""
        interval = 1.0 / self.rate if self.rate > 0 else 0
        count = 0

        while True:
            if self.max_messages is not None and count >= self.max_messages:
                break

            value = random.uniform(self.min_value, self.max_value)

            yield Message(
                key=self.key,
                timestamp=datetime.now(timezone.utc),
                value=value,
                tags={},
            )

            count += 1

            if interval > 0:
                await asyncio.sleep(interval)


class SequenceSource(Source):
    """
    Generate sequential numbers (BATCH or REALTIME mode).

    Useful for testing and debugging.
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        start_value: int = 0,
        end_value: int | None = None,
        step_value: int = 1,
        rate: float = 1.0,
        key: str = "sequence",
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        """
        Initialize sequence source.

        Args:
            broker: Message broker
            channel: Target channel
            start_value: Starting value
            end_value: Ending value (None = unlimited)
            step_value: Increment step
            rate: Messages per second
            key: Message key
            delivery_guarantee: Delivery guarantee
        """
        batch_mode = BatchMode.BATCH if end_value is not None else BatchMode.REALTIME
        super().__init__(broker, channel, batch_mode, delivery_guarantee)
        self.start_value = start_value
        self.end_value = end_value
        self.step_value = step_value
        self.rate = rate
        self.key = key

    async def produce(self) -> AsyncIterator[Message]:
        """Generate sequential values."""
        interval = 1.0 / self.rate if self.rate > 0 else 0
        value = self.start_value

        while True:
            if self.end_value is not None and value >= self.end_value:
                break

            yield Message(
                key=self.key,
                timestamp=datetime.now(timezone.utc),
                value=value,
                tags={"sequence_value": str(value)},
            )

            value += self.step_value

            if interval > 0:
                await asyncio.sleep(interval)
