"""Observatory Bridge - sole interface between COD3S framework and Observatory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from cod3s_data.core.subscription_registry import SubscriptionRegistry
from cod3s_data.observatory.buffer import EventBuffer, EventType, ObservatoryEvent
from cod3s_data.observatory.sampler import MessageSampler
from cod3s_data.observatory.websocket_manager import WebSocketManager

if TYPE_CHECKING:
    from cod3s_data.core.message import Message

logger = structlog.get_logger()


class ObservatoryBridge:
    """Sole point of contact between the COD3S framework and the Observatory.

    Implements observation hooks (framework -> observatory) and
    control commands (observatory -> framework).
    """

    def __init__(
        self,
        event_buffer: EventBuffer,
        sampler: MessageSampler,
        websocket_manager: WebSocketManager,
    ) -> None:
        self._buffer = event_buffer
        self._sampler = sampler
        self._ws = websocket_manager
        self._server: Any = None
        self._framework: Any = None

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the Observatory server."""
        if self._server is not None:
            await self._server.start()

    async def stop(self) -> None:
        """Stop the Observatory server."""
        # Close all WebSocket connections
        try:
            if self._ws is not None:
                for client_id in list(self._ws._clients.keys()):
                    try:
                        await self._ws._clients[client_id].close()
                    except Exception:
                        pass
                self._ws._clients.clear()
        except Exception:
            pass

        if self._server is not None:
            await self._server.stop()

    # --- Observation Hooks (Framework -> Bridge) ---
    # All hooks are error-isolated: they catch exceptions to
    # never crash the pipeline.

    async def on_message_published(
        self,
        channel: str,
        message: Message,
        subscriber_count: int,
    ) -> None:
        """Called by the broker after a message is published."""
        try:
            if not self._sampler.should_process(channel):
                return

            event = ObservatoryEvent(
                type=EventType.MESSAGE,
                data={
                    "channel": channel,
                    "key": getattr(message, "key", None),
                    "subscriber_count": subscriber_count,
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("message.published", event.data)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_message_published", error=str(e))

    async def on_component_state_change(
        self,
        component_id: str,
        component_type: str,
        old_state: str,
        new_state: str,
    ) -> None:
        """Called when a pipeline component changes state."""
        try:
            event = ObservatoryEvent(
                type=EventType.COMPONENT_STATE,
                data={
                    "component_id": component_id,
                    "component_type": component_type,
                    "old_state": old_state,
                    "new_state": new_state,
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("component.state", event.data)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_component_state_change", error=str(e))

    async def on_subscription_change(
        self,
        pattern: str,
        action: str,
        subscriber_id: str,
    ) -> None:
        """Called when a subscription is added or removed."""
        try:
            event = ObservatoryEvent(
                type=EventType.SUBSCRIPTION,
                data={
                    "pattern": pattern,
                    "action": action,
                    "subscriber_id": subscriber_id,
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("topology.update", event.data)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_subscription_change", error=str(e))

    async def on_metric_emitted(
        self,
        metric_name: str,
        value: float | dict,
        tags: dict[str, str],
    ) -> None:
        """Called when the framework emits a metric."""
        try:
            event = ObservatoryEvent(
                type=EventType.METRIC,
                data={
                    "metric_name": metric_name,
                    "value": value,
                    "tags": tags,
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("metric.update", event.data)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_metric_emitted", error=str(e))

    async def on_error(
        self,
        component_id: str,
        error: Exception,
        context: dict[str, str],
    ) -> None:
        """Called when a component encounters an error."""
        try:
            event = ObservatoryEvent(
                type=EventType.ERROR,
                data={
                    "component_id": component_id,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "context": context,
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("error.occurred", event.data)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_error", error=str(e))

    # --- Control Interface (Bridge -> Framework) ---
    # Stub methods. Will be wired in Phase 4 (Debug Controller).

    async def pause_pipeline(self) -> None:
        """Pause all sources at their next yield point."""

    async def resume_pipeline(self) -> None:
        """Resume all paused sources."""

    # --- Pipeline Control (Observatory -> Framework) ---

    async def start_pipeline(self) -> dict[str, str]:
        """Start the pipeline via framework."""
        if self._framework is None:
            return {"status": "error", "message": "No framework connected"}
        return await self._framework.handle_pipeline_command("start")

    async def stop_pipeline(self) -> dict[str, str]:
        """Stop the pipeline via framework."""
        if self._framework is None:
            return {"status": "error", "message": "No framework connected"}
        return await self._framework.handle_pipeline_command("stop")

    async def restart_pipeline(self) -> dict[str, str]:
        """Restart the pipeline via framework."""
        if self._framework is None:
            return {"status": "error", "message": "No framework connected"}
        return await self._framework.handle_pipeline_command("restart")

    def get_pipeline_state(self) -> str:
        """Get current pipeline state."""
        if self._framework is None:
            return "unknown"
        return self._framework._pipeline_state.value

    def get_components_snapshot(self) -> list[dict[str, str]]:
        """Get current list of pipeline components with their state."""
        if self._framework is None:
            return []
        components: list[dict[str, str]] = []
        for source in self._framework.sources:
            state = "running" if source._running else "created"
            components.append({
                "component_id": source._component_id,
                "component_type": "source",
                "state": state,
            })
        for tfm in self._framework.transformations:
            state = "running" if tfm._running else "created"
            components.append({
                "component_id": tfm._component_id,
                "component_type": "transformation",
                "state": state,
            })
        for dest in self._framework.destinations:
            state = "running" if dest._running else "created"
            components.append({
                "component_id": dest._component_id,
                "component_type": "destination",
                "state": state,
            })
        return components

    def get_topology_snapshot(self) -> dict[str, Any]:
        """Get enriched topology with nodes (including channels) and computed edges."""
        if self._framework is None:
            return {"nodes": [], "edges": []}

        nodes: list[dict[str, Any]] = []
        publishers: list[tuple[str, str]] = []  # (component_id, channel)
        subscribers: list[tuple[str, str]] = []  # (component_id, pattern)

        for source in self._framework.sources:
            state = "running" if source._running else "created"
            nodes.append({
                "component_id": source._component_id,
                "component_type": "source",
                "state": state,
                "channels": {
                    "publishes": [source.channel],
                    "subscribes": [],
                },
            })
            publishers.append((source._component_id, source.channel))

        for tfm in self._framework.transformations:
            state = "running" if tfm._running else "created"
            nodes.append({
                "component_id": tfm._component_id,
                "component_type": "transformation",
                "state": state,
                "channels": {
                    "publishes": [tfm.output_channel],
                    "subscribes": list(tfm.input_channels),
                },
            })
            publishers.append((tfm._component_id, tfm.output_channel))
            for ch in tfm.input_channels:
                subscribers.append((tfm._component_id, ch))

        for dest in self._framework.destinations:
            state = "running" if dest._running else "created"
            nodes.append({
                "component_id": dest._component_id,
                "component_type": "destination",
                "state": state,
                "channels": {
                    "publishes": [],
                    "subscribes": [dest.channel_pattern],
                },
            })
            subscribers.append((dest._component_id, dest.channel_pattern))

        # Compute edges
        edges: list[dict[str, str]] = []
        for pub_id, channel in publishers:
            for sub_id, pattern in subscribers:
                if pub_id == sub_id:
                    continue
                if SubscriptionRegistry.matches(pattern, channel):
                    edges.append({
                        "source_id": pub_id,
                        "target_id": sub_id,
                        "channel": channel,
                        "pattern": pattern,
                    })

        return {"nodes": nodes, "edges": edges}
