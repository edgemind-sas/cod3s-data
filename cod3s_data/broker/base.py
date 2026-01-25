"""Abstract broker interface for COD3S Data Framework."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from cod3s_data.core.message import Message
from cod3s_data.core.subscription_registry import Callback


class DeliveryGuarantee(Enum):
    """
    Message delivery guarantee level.

    Note: Delivery guarantees are enforced by sources, not broker.
    Broker is best-effort.
    """

    AT_MOST_ONCE = "at_most_once"  # Fire-and-forget
    AT_LEAST_ONCE = "at_least_once"  # May deliver duplicates


class HistoryMode(Enum):
    """
    History replay mode for new subscriptions.
    """

    NONE = "none"  # Only receive new messages
    RECENT = "recent"  # Replay last N messages
    ALL = "all"  # Replay all buffered messages


@dataclass
class PublishResult:
    """
    Result of publish operation.

    Attributes:
        success: Whether publish succeeded
        subscriber_count: Number of subscribers notified
        publish_time: When message was published
    """

    success: bool
    subscriber_count: int
    publish_time: datetime


@dataclass
class SubscriptionHandle:
    """
    Handle to manage a subscription.

    Use to unsubscribe later.
    """

    id: str
    pattern: str
    callback: Callback


class Broker(ABC):
    """
    Abstract broker interface.

    All broker implementations must support this interface.

    Thread-safe: Yes (all methods safe for concurrent access)
    """

    @abstractmethod
    async def publish(
        self,
        channel: str,
        message: Message,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> PublishResult:
        """
        Publish message to channel.

        Args:
            channel: Target channel (e.g., "sensors.temp")
            message: Message to publish
            delivery_guarantee: Delivery guarantee level (advisory only)

        Returns:
            PublishResult with success and subscriber count

        Raises:
            InvalidChannelError: If channel name is invalid
            PublishError: If publish fails

        Performance: O(1) exact match + O(n) wildcards, typically <1ms

        Examples:
            >>> result = await broker.publish("sensors.temp", message)
            >>> print(f"Notified {result.subscriber_count} subscribers")
        """
        ...

    @abstractmethod
    def subscribe(
        self,
        pattern: str,
        callback: Callback,
        history: HistoryMode = HistoryMode.NONE,
        history_count: int = 100,
    ) -> SubscriptionHandle:
        """
        Subscribe to channel pattern.

        Args:
            pattern: Channel pattern (exact or wildcard)
                - Exact: "sensors.temp"
                - Single-level wildcard: "sensors.*.temp"
                - Multi-level wildcard: "sensors.**"
            callback: Async function called for each matching message
            history: History replay mode
            history_count: Number of historical messages (if RECENT)

        Returns:
            SubscriptionHandle for managing this subscription

        Raises:
            InvalidPatternError: If pattern is malformed

        Performance: O(1) registration

        Examples:
            >>> async def handle_temp(msg: Message):
            ...     print(f"Temperature: {msg.value}")
            >>> handle = broker.subscribe("sensors.temp", handle_temp)
            >>> # Later: broker.unsubscribe(handle)
        """
        ...

    @abstractmethod
    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """
        Remove a subscription.

        Args:
            handle: Handle returned by subscribe()

        Examples:
            >>> broker.unsubscribe(handle)
        """
        ...

    @abstractmethod
    def get_history(self, channel: str, count: int = 100) -> list[Message]:
        """
        Get recent messages from channel history.

        Args:
            channel: Exact channel name
            count: Maximum messages to return

        Returns:
            List of recent messages (newest first), may be fewer than count

        Examples:
            >>> recent = broker.get_history("sensors.temp", count=10)
            >>> len(recent) <= 10
            True
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """
        Start broker (initialization, resource allocation).

        Called during framework startup.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop broker (cleanup, resource deallocation).

        Called during framework shutdown.
        """
        ...
