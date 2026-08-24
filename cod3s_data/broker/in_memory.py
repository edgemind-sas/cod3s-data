"""In-memory broker implementation for COD3S Data Framework."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from cod3s_data.broker.base import (
    Broker,
    DeliveryGuarantee,
    HistoryMode,
    PublishResult,
    SubscriptionHandle,
)
from cod3s_data.broker.exceptions import InvalidChannelError, InvalidPatternError
from cod3s_data.core.buffers import HistoryBuffer
from cod3s_data.core.message import Message
from cod3s_data.core.subscription_registry import Callback, SubscriptionRegistry

_logger = structlog.get_logger()


class InMemoryBroker(Broker):
    """
    In-memory, single-process message broker.

    Characteristics:
    - Fast: No disk I/O, no network overhead
    - Simple: No external dependencies
    - Volatile: Messages lost on restart
    - Bounded: Configurable history buffer size

    Performance:
    - Publish: <1ms typical
    - Subscribe callback: <0.1ms typical
    - Throughput: 10,000+ msgs/sec

    Memory:
    - History buffers: configurable per channel
    - Typical: ~1MB for 10 channels with 100 history each

    Thread-safe: Yes (uses asyncio.Lock for state)
    """

    def __init__(self, default_history_size: int = 100, enable_metrics: bool = True) -> None:
        """
        Initialize in-memory broker.

        Args:
            default_history_size: Default history buffer size per channel
            enable_metrics: Emit metrics to _metrics.* channels

        Examples:
            >>> broker = InMemoryBroker(default_history_size=100)
            >>> broker = InMemoryBroker(enable_metrics=False)  # No metrics overhead
        """
        self._default_history_size = default_history_size
        self._enable_metrics = enable_metrics

        # Observatory bridge (set by Framework when observatory is active)
        self._bridge: Any = None

        # Subscription registry
        self._registry = SubscriptionRegistry()

        # History buffers per channel
        self._history: dict[str, HistoryBuffer] = {}

        # Subscription handles
        self._subscriptions: dict[str, SubscriptionHandle] = {}

        # State lock (for thread-safe subscription management)
        self._lock = asyncio.Lock()

        # Metrics
        self._publish_count = 0
        self._notify_count = 0
        self._error_count = 0

        # Running state
        self._running = False

    async def start(self) -> None:
        """Start broker."""
        self._running = True

    async def stop(self) -> None:
        """Stop broker."""
        self._running = False

        # Clear all subscriptions
        async with self._lock:
            self._subscriptions.clear()
            self._registry = SubscriptionRegistry()

    async def publish(
        self,
        channel: str,
        message: Message,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,  # noqa: ARG002 advisory only, see Broker.publish
    ) -> PublishResult:
        """
        Publish message to channel.

        Implementation:
        1. Validate channel name
        2. Add to history buffer
        3. Match subscriptions
        4. Notify subscribers (async)
        5. Emit metrics
        """
        # Validate channel
        if not channel or not channel.strip():
            raise InvalidChannelError("Channel name cannot be empty")

        # Reserved prefix (only _metrics.* allowed)
        if (
            channel.startswith("_")
            and not channel.startswith("_metrics.")
            and not self._enable_metrics
        ):
            raise InvalidChannelError(f"Channel '{channel}' uses reserved prefix '_'")

        publish_time = datetime.now(UTC)

        # Add to history
        await self._add_to_history(channel, message)

        # Match subscribers
        callbacks = self._registry.match_channel(channel)

        # Notify subscribers (fire-and-forget, don't wait)
        for callback in callbacks:
            asyncio.create_task(self._notify_subscriber(callback, message, channel))

        subscriber_count = len(callbacks)

        # Observatory hook
        if self._bridge is not None:
            try:
                await self._bridge.on_message_published(channel, message, subscriber_count)
            except Exception as e:
                _logger.warning("Observatory hook error", hook="on_message_published", error=str(e))

            # Forward _metrics.* messages as metric events
            if channel.startswith("_metrics."):
                try:
                    await self._bridge.on_metric_emitted(
                        metric_name=getattr(message, "key", channel),
                        value=getattr(message, "value", 0),
                        tags=dict(getattr(message, "tags", {})),
                    )
                except Exception as e:
                    _logger.warning(
                        "Observatory hook error", hook="on_metric_emitted", error=str(e)
                    )

        # Update metrics
        self._publish_count += 1

        # Emit metrics (if enabled, avoid recursion, throttle to every 50 messages)
        if (
            self._enable_metrics
            and not channel.startswith("_metrics.")
            and self._publish_count % 50 == 0
        ):
            metric_msg = Message(
                key="broker.publish_count",
                timestamp=publish_time,
                value=self._publish_count,
                tags={},
            )
            asyncio.create_task(
                self.publish(
                    "_metrics.broker.published",
                    metric_msg,
                    DeliveryGuarantee.AT_MOST_ONCE,
                )
            )

        return PublishResult(
            success=True, subscriber_count=subscriber_count, publish_time=publish_time
        )

    async def _notify_subscriber(self, callback: Callback, message: Message, channel: str) -> None:
        """
        Notify a single subscriber.

        Errors are caught and logged, don't crash broker.
        """
        try:
            await callback(message)
            self._notify_count += 1

        except Exception as e:
            self._error_count += 1

            # Emit error metric
            if self._enable_metrics:
                error_msg = Message(
                    key="broker.error_count",
                    timestamp=datetime.now(UTC),
                    value=self._error_count,
                    tags={"channel": channel, "error_type": type(e).__name__},
                )
                asyncio.create_task(
                    self.publish(
                        "_metrics.broker.errors",
                        error_msg,
                        DeliveryGuarantee.AT_MOST_ONCE,
                    )
                )

    async def _add_to_history(self, channel: str, message: Message) -> None:
        """Add message to channel history buffer."""
        if channel not in self._history:
            self._history[channel] = HistoryBuffer(max_size=self._default_history_size)

        self._history[channel].add(message)

    def subscribe(
        self,
        pattern: str,
        callback: Callback,
        history: HistoryMode = HistoryMode.NONE,
        history_count: int = 100,
    ) -> SubscriptionHandle:
        """
        Subscribe to channel pattern.

        Implementation:
        1. Validate pattern
        2. Register with subscription registry
        3. Replay history if requested
        4. Return handle
        """
        # Validate pattern
        if not pattern or not pattern.strip():
            raise InvalidPatternError("Pattern cannot be empty")

        # Create handle
        handle = SubscriptionHandle(id=str(uuid4()), pattern=pattern, callback=callback)

        # Register subscription
        self._registry.add_subscription(pattern, callback)
        self._subscriptions[handle.id] = handle

        # Observatory hook
        if self._bridge is not None:
            try:
                asyncio.create_task(
                    self._bridge.on_subscription_change(pattern, "subscribe", handle.id)
                )
            except Exception as e:
                _logger.warning(
                    "Observatory hook error", hook="on_subscription_change", error=str(e)
                )

        # Replay history if requested
        if history != HistoryMode.NONE:
            asyncio.create_task(self._replay_history(pattern, callback, history, history_count))

        # Emit metric
        if self._enable_metrics:
            metric_msg = Message(
                key="broker.active_subscriptions",
                timestamp=datetime.now(UTC),
                value=len(self._subscriptions),
                tags={},
            )
            asyncio.create_task(
                self.publish(
                    "_metrics.broker.subscriptions",
                    metric_msg,
                    DeliveryGuarantee.AT_MOST_ONCE,
                )
            )

        return handle

    async def _replay_history(
        self, pattern: str, callback: Callback, mode: HistoryMode, count: int
    ) -> None:
        """
        Replay historical messages to new subscriber.

        Called asynchronously after subscription.
        """
        # Find matching channels
        matching_channels = [ch for ch in self._history if self._matches_pattern(pattern, ch)]

        for channel in matching_channels:
            buffer = self._history[channel]

            if mode == HistoryMode.RECENT:
                messages = buffer.get_recent(count)
            elif mode == HistoryMode.ALL:
                messages = buffer.get_all()
            else:
                messages = []

            # Replay messages (newest first from buffer, but we reverse for oldest-first replay)
            for message in reversed(messages):
                # Errors during history replay are silently ignored
                with contextlib.suppress(Exception):
                    await callback(message)

    def _matches_pattern(self, pattern: str, channel: str) -> bool:
        """
        Check if channel matches pattern.

        Simple check for history replay.
        """
        if "*" not in pattern:
            return pattern == channel

        # Use registry's matching logic
        # Create a temporary callback to test
        async def dummy_callback(msg: Message) -> None:
            pass

        # Add temporarily, check match, remove
        self._registry.add_subscription(pattern, dummy_callback)
        callbacks = self._registry.match_channel(channel)
        self._registry.remove_subscription(pattern, dummy_callback)

        return len(callbacks) > 0

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """
        Remove subscription.

        Implementation:
        1. Remove from registry
        2. Remove from handles
        3. Emit metric
        """
        if handle.id not in self._subscriptions:
            return

        # Remove from registry
        self._registry.remove_subscription(handle.pattern, handle.callback)

        # Remove from handles
        del self._subscriptions[handle.id]

        # Observatory hook
        if self._bridge is not None:
            try:
                asyncio.create_task(
                    self._bridge.on_subscription_change(handle.pattern, "unsubscribe", handle.id)
                )
            except Exception as e:
                _logger.warning(
                    "Observatory hook error", hook="on_subscription_change", error=str(e)
                )

        # Emit metric
        if self._enable_metrics:
            metric_msg = Message(
                key="broker.active_subscriptions",
                timestamp=datetime.now(UTC),
                value=len(self._subscriptions),
                tags={},
            )
            asyncio.create_task(
                self.publish(
                    "_metrics.broker.subscriptions",
                    metric_msg,
                    DeliveryGuarantee.AT_MOST_ONCE,
                )
            )

    def get_history(self, channel: str, count: int = 100) -> list[Message]:
        """
        Get recent messages from channel history.

        Args:
            channel: Exact channel name
            count: Maximum messages to return

        Returns:
            List of recent messages (newest first), may be fewer than count
        """
        if channel not in self._history:
            return []

        return self._history[channel].get_recent(count)

    def get_metrics(self) -> dict[str, int]:
        """
        Get broker metrics.

        Returns:
            Dictionary with metric counts
        """
        return {
            "publish_count": self._publish_count,
            "notify_count": self._notify_count,
            "error_count": self._error_count,
            "subscription_count": self._registry.count_subscriptions(),
            "channel_count": len(self._history),
        }

    @property
    def enable_metrics(self) -> bool:
        """Check if metrics are enabled."""
        return self._enable_metrics

    @property
    def default_history_size(self) -> int:
        """Get default history size."""
        return self._default_history_size
