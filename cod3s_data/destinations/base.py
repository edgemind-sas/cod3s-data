"""Base class for destinations in COD3S Data Framework."""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from cod3s_data.broker.base import Broker, SubscriptionHandle
from cod3s_data.core.buffers import DestinationBuffer, OverflowStrategy
from cod3s_data.core.message import Message

if TYPE_CHECKING:
    from cod3s_data.transformations.param_store import ParameterStore

_logger = structlog.get_logger()

# An exception message can be arbitrarily long — an InfluxDB rejection carries the
# whole offending line protocol. Tags travel with the message into whatever reads
# the dead-letter channel, so the detail is capped rather than passed through.
DLQ_DETAIL_MAX_LEN = 200


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
        self._param_stores: list[ParameterStore] = []

        # Observatory bridge (set by Framework when observatory is active)
        self._bridge: Any = None
        self._component_id: str = ""
        self._label: str = ""
        self._description: str = ""

    async def start(self) -> None:
        """Subscribe to the channel pattern and begin writing.

        Starts any attached parameter stores, subscribes to the broker, then
        launches the background writer loop that drains the buffer.
        """
        self._running = True
        for store in self._param_stores:
            await store.start()
        self._subscription_handle = self.broker.subscribe(
            self.channel_pattern, self._enqueue_message
        )
        self._writer_task = asyncio.create_task(self._writer_loop())
        await self._notify_state_change("idle", "running")

    async def stop(self) -> None:
        """Unsubscribe, drain what is buffered, and release resources.

        Waits for the writer loop to finish, flushes the remaining buffer and
        calls close(). Messages already accepted are written before this
        returns.
        """
        self._running = False
        if self._subscription_handle:
            self.broker.unsubscribe(self._subscription_handle)
        if self._writer_task:
            await self._writer_task
        await self._flush_buffer()
        await self.close()
        for store in self._param_stores:
            await store.stop()
        await self._notify_state_change("running", "stopped")

    async def _enqueue_message(self, message: Message) -> None:
        if self._bridge is not None:
            with contextlib.suppress(Exception):
                await self._bridge.on_message_received(self._component_id, "destination", message)
        await self.buffer.put(message)

    async def _writer_loop(self) -> None:
        batch: list[Message] = []
        while self._running or not self.buffer.is_empty():
            try:
                try:
                    message = await asyncio.wait_for(self.buffer.get(), timeout=0.1)
                    batch.append(message)
                except TimeoutError:
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
            except TimeoutError:
                break
        if batch:
            await self._write_batch_with_retry(batch)

    async def _write_batch_with_retry(self, batch: list[Message]) -> None:
        for message in batch:
            failure = await self._write_with_retry(message)
            if failure is not None:
                self._error_count += 1
                if self.dlq_channel:
                    with contextlib.suppress(Exception):
                        await self.broker.publish(
                            self.dlq_channel, self.to_dead_letter(message, failure)
                        )

    async def _write_with_retry(self, message: Message) -> Exception | None:
        """Write with retries, returning None on success or the last failure.

        The exception is returned rather than swallowed: it is the only thing
        that can say *why* a message ends up on the dead-letter channel, and by
        the time the caller has a bare False it is already gone.
        """
        # Reaching the end of the loop means every attempt failed, so this
        # placeholder only ever survives when no attempt was made at all.
        last_error: Exception = RuntimeError(
            f"No write attempted: retry_attempts is {self.retry_attempts}"
        )
        for attempt in range(self.retry_attempts):
            try:
                await self.write(message)
                self._message_count += 1
                return None
            except Exception as e:
                last_error = e
                if attempt >= self.retry_attempts - 1:
                    break
                backoff = self._calculate_backoff(attempt)
                await asyncio.sleep(backoff)
        return last_error

    def to_dead_letter(self, message: Message, error: Exception) -> Message:
        """Tag a message with why it is being routed to the dead-letter channel.

        Without this the message arrives byte-for-byte identical to the one that
        was published on the input channel — same key, same timestamp, same
        value — so nothing distinguishes a failure from ordinary traffic, and the
        reason has to be recovered by hand from the logs.

        Tags rather than an envelope around the value: a consumer reading the
        dead-letter channel as an ordinary stream keeps working. A private
        attribute on `Message` is not an option either — `model_dump_json()`
        omits private state, so the reason would never reach that consumer.

        Args:
            message: The message whose delivery was abandoned
            error: The failure from the last attempt

        Returns:
            A copy carrying the `dlq_*` tags; the original is left untouched.
        """
        detail = str(error).strip() or type(error).__name__
        if len(detail) > DLQ_DETAIL_MAX_LEN:
            detail = detail[: DLQ_DETAIL_MAX_LEN - 1] + "\u2026"

        tags = {
            "dlq_destination": type(self).__name__,
            # The pattern subscribed to, not the channel the message came in on:
            # the broker knows it but drops it before calling the subscriber.
            "dlq_channel_pattern": self.channel_pattern,
            "dlq_error_type": type(error).__name__,
            "dlq_error": detail,
            # A failure means every attempt was spent, so the count is the budget.
            "dlq_attempts": str(self.retry_attempts),
        }
        if self._component_id:
            tags["dlq_component_id"] = self._component_id
        return message.with_tags(**tags)

    def _calculate_backoff(self, attempt: int) -> float:
        if self.retry_strategy == RetryStrategy.EXPONENTIAL:
            return float(min(2**attempt, 60))
        else:
            return 1.0

    @abstractmethod
    async def write(self, message: Message) -> None:
        """Write one message to the sink.

        Raising is how a failure is signalled: the caller retries according to
        the retry strategy, and routes the message to the dead-letter channel
        if one is configured.

        Args:
            message: Message to write
        """

    async def _notify_state_change(self, old_state: str, new_state: str) -> None:
        """Notify Observatory bridge of state change."""
        if self._bridge is not None:
            try:
                await self._bridge.on_component_state_change(
                    self._component_id, "destination", old_state, new_state
                )
            except Exception as e:
                _logger.warning("Observatory hook error", error=str(e))

    async def close(self) -> None:
        """Release resources held by the sink.

        Called once by stop(), after the buffer has been flushed. The default
        does nothing; override it to close a file handle or a connection.
        """

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def error_count(self) -> int:
        return self._error_count
