"""CollectDestination for testing."""

import asyncio

from cod3s_data.broker.base import Broker
from cod3s_data.core.buffers import OverflowStrategy
from cod3s_data.core.message import Message
from cod3s_data.destinations.base import Destination


class CollectDestination(Destination):
    """Collect messages with assertions for testing."""

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
    ) -> None:
        super().__init__(broker, channel_pattern, buffer_size, overflow_strategy, retry_attempts=1)
        self.messages: list[Message] = []
        self._lock = asyncio.Lock()
        self._wait_event = asyncio.Event()

    async def write(self, message: Message) -> None:
        async with self._lock:
            self.messages.append(message)
            self._wait_event.set()
            self._wait_event.clear()

    def get_all(self) -> list[Message]:
        return self.messages.copy()

    def clear(self) -> None:
        self.messages.clear()

    def assert_count(self, expected: int) -> None:
        assert len(self.messages) == expected, (
            f"Expected {expected} messages, got {len(self.messages)}"
        )

    def assert_min_count(self, minimum: int) -> None:
        assert len(self.messages) >= minimum, (
            f"Expected at least {minimum} messages, got {len(self.messages)}"
        )

    def filter_by(self, key: str | None = None, **tags: str) -> list[Message]:
        results = self.messages
        if key:
            results = [m for m in results if m.key == key]
        for tag_key, tag_value in tags.items():
            results = [m for m in results if m.tags.get(tag_key) == tag_value]
        return results

    async def wait_for_messages(self, count: int, timeout: float = 5.0) -> None:
        start = asyncio.get_event_loop().time()
        while len(self.messages) < count:
            if asyncio.get_event_loop().time() - start > timeout:
                raise TimeoutError(
                    f"Timeout waiting for {count} messages, got {len(self.messages)}"
                )
            await asyncio.sleep(0.01)
