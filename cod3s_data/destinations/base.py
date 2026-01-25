"""Base class for destinations in COD3S Data Framework."""

import asyncio
from abc import ABC, abstractmethod
from enum import Enum

from cod3s_data.broker.base import Broker, SubscriptionHandle
from cod3s_data.core.buffers import DestinationBuffer, OverflowStrategy
from cod3s_data.core.message import Message


class RetryStrategy(Enum):
    """Retry backoff strategy."""

    EXPONENTIAL = "exponential"
    FIXED = "fixed"


class Destination(ABC):
    """Base class for all destinations."""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        retry_attempts: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        dlq_channel: str | None = None,
        batch_size: int = 1,
    ) -> None:
        self.broker = broker
        self.channel_pattern = channel_pattern
        self.batch_size = batch_size
        self.retry_attempts = retry_attempts
        self.retry_strategy = retry_strategy
        self.dlq_channel = dlq_channel
        self.buffer = DestinationBuffer(buffer_size, overflow_strategy)
        self._running = False
        self._subscription_handle: SubscriptionHandle | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._message_count = 0
        self._error_count = 0

    async def start(self) -> None:
        self._running = True
        self._subscription_handle = self.broker.subscribe(
            self.channel_pattern, self._enqueue_message
        )
        self._writer_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> None:
        self._running = False
        if self._subscription_handle:
            self.broker.unsubscribe(self._subscription_handle)
        if self._writer_task:
            await self._writer_task
        await self._flush_buffer()
        await self.close()

    async def _enqueue_message(self, message: Message) -> None:
        await self.buffer.put(message)

    async def _writer_loop(self) -> None:
        batch: list[Message] = []
        while self._running or not self.buffer.is_empty():
            try:
                try:
                    message = await asyncio.wait_for(self.buffer.get(), timeout=0.1)
                    batch.append(message)
                except asyncio.TimeoutError:
                    if batch:
                        await self._write_batch_with_retry(batch)
                        batch = []
                    continue
                if len(batch) >= self.batch_size:
                    await self._write_batch_with_retry(batch)
                    batch = []
            except Exception:
                await asyncio.sleep(1)
        if batch:
            await self._write_batch_with_retry(batch)

    async def _flush_buffer(self) -> None:
        batch: list[Message] = []
        while not self.buffer.is_empty():
            try:
                message = await asyncio.wait_for(self.buffer.get(), timeout=0.1)
                batch.append(message)
                if len(batch) >= self.batch_size:
                    await self._write_batch_with_retry(batch)
                    batch = []
            except asyncio.TimeoutError:
                break
        if batch:
            await self._write_batch_with_retry(batch)

    async def _write_batch_with_retry(self, batch: list[Message]) -> None:
        for message in batch:
            success = await self._write_with_retry(message)
            if not success:
                self._error_count += 1
                if self.dlq_channel:
                    try:
                        await self.broker.publish(self.dlq_channel, message)
                    except Exception:
                        pass

    async def _write_with_retry(self, message: Message) -> bool:
        for attempt in range(self.retry_attempts):
            try:
                await self.write(message)
                self._message_count += 1
                return True
            except Exception:
                if attempt >= self.retry_attempts - 1:
                    return False
                backoff = self._calculate_backoff(attempt)
                await asyncio.sleep(backoff)
        return False

    def _calculate_backoff(self, attempt: int) -> float:
        if self.retry_strategy == RetryStrategy.EXPONENTIAL:
            return min(2**attempt, 60)
        else:
            return 1.0

    @abstractmethod
    async def write(self, message: Message) -> None:
        ...

    async def close(self) -> None:
        pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def error_count(self) -> int:
        return self._error_count
