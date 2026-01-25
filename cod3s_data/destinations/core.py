"""Core destination implementations."""

import asyncio
import sys
from pathlib import Path
from typing import TextIO

from cod3s_data.broker.base import Broker
from cod3s_data.core.buffers import OverflowStrategy
from cod3s_data.core.message import Message
from cod3s_data.destinations.base import Destination, RetryStrategy


class ConsoleDestination(Destination):
    """Print messages to stdout or stderr."""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        stream: str = "stdout",
        format: str = "json",
        buffer_size: int = 100,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
    ) -> None:
        super().__init__(broker, channel_pattern, buffer_size, overflow_strategy, retry_attempts=1)
        self.stream_name = stream
        self.format = format
        self._stream: TextIO = sys.stdout if stream == "stdout" else sys.stderr

    async def write(self, message: Message) -> None:
        if self.format == "json":
            output = message.to_json()
        else:
            output = f"{message.timestamp.isoformat()} [{message.key}] {message.value}"
        print(output, file=self._stream)


class FileDestination(Destination):
    """Write messages to JSON/JSONL files."""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        file_path: str | Path,
        format: str = "jsonl",
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        retry_attempts: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        dlq_channel: str | None = None,
        batch_size: int = 10,
        append: bool = True,
    ) -> None:
        super().__init__(
            broker, channel_pattern, buffer_size, overflow_strategy,
            retry_attempts, retry_strategy, dlq_channel, batch_size
        )
        self.file_path = Path(file_path)
        self.format = format
        self.append = append
        self._file_handle: TextIO | None = None
        self._lock = asyncio.Lock()

    async def write(self, message: Message) -> None:
        async with self._lock:
            if self._file_handle is None:
                mode = "a" if self.append else "w"
                self._file_handle = self.file_path.open(mode, encoding="utf-8")
            self._file_handle.write(message.to_json() + "\n")
            self._file_handle.flush()

    async def close(self) -> None:
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None


class InMemoryDestination(Destination):
    """Store messages in memory."""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        retry_attempts: int = 1,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        dlq_channel: str | None = None,
    ) -> None:
        super().__init__(
            broker, channel_pattern, buffer_size, overflow_strategy,
            retry_attempts, retry_strategy, dlq_channel
        )
        self.messages: list[Message] = []
        self._lock = asyncio.Lock()

    async def write(self, message: Message) -> None:
        async with self._lock:
            self.messages.append(message)

    def get_all(self) -> list[Message]:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages.clear()
