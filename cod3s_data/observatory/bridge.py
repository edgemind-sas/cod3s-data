"""Observatory Bridge - sole interface between COD3S framework and Observatory."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any

import structlog

from cod3s_data.core.subscription_registry import SubscriptionRegistry
from cod3s_data.observatory.buffer import EventBuffer, EventType, ObservatoryEvent
from cod3s_data.observatory.message_store import JourneyStep, JourneyStore, MessageDetailStore
from cod3s_data.observatory.sampler import MessageSampler
from cod3s_data.observatory.websocket_manager import WebSocketManager

if TYPE_CHECKING:
    from cod3s_data.core.message import Message

logger = structlog.get_logger()

_TRACE_ID_CACHE_SIZE = 2000


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
        message_store: MessageDetailStore | None = None,
        journey_store: JourneyStore | None = None,
    ) -> None:
        self._buffer = event_buffer
        self._sampler = sampler
        self._ws = websocket_manager
        self._message_store = message_store
        self._journey_store = journey_store
        self._server: Any = None
        self._framework: Any = None
        # Mapping message_id -> trace_id for correlating messages across transformations
        self._trace_ids: OrderedDict[str, str] = OrderedDict()
        # Mapping message_id -> parent_message_id for tree structure
        self._parent_ids: OrderedDict[str, str] = OrderedDict()

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

    # --- Trace ID management ---

    def _get_or_create_trace_id(self, message_id: str) -> str:
        """Get an existing trace_id for a message, or use message_id as new trace."""
        if message_id in self._trace_ids:
            self._trace_ids.move_to_end(message_id)
            return self._trace_ids[message_id]
        # New message: trace_id = message_id
        self._set_trace_id(message_id, message_id)
        return message_id

    def _set_trace_id(self, message_id: str, trace_id: str) -> None:
        """Associate a message_id with a trace_id, with LRU eviction."""
        if message_id in self._trace_ids:
            self._trace_ids.move_to_end(message_id)
        else:
            while len(self._trace_ids) >= _TRACE_ID_CACHE_SIZE:
                self._trace_ids.popitem(last=False)
        self._trace_ids[message_id] = trace_id

    def _set_parent_id(self, message_id: str, parent_message_id: str) -> None:
        """Record that message_id was produced from parent_message_id."""
        if message_id in self._parent_ids:
            self._parent_ids.move_to_end(message_id)
        else:
            while len(self._parent_ids) >= _TRACE_ID_CACHE_SIZE:
                self._parent_ids.popitem(last=False)
        self._parent_ids[message_id] = parent_message_id

    def _get_parent_id(self, message_id: str) -> str:
        """Get the parent message_id, or empty string if root."""
        return self._parent_ids.get(message_id, "")

    # --- Component resolution ---

    def _resolve_publisher(self, channel: str) -> tuple[str, str, str]:
        """Find which component publishes to a given channel.

        Returns (component_id, component_type, label).
        """
        if self._framework is None:
            return ("broker", "broker", "")
        for source in self._framework.sources:
            if source.channel == channel:
                return (source._component_id, "source", source._label)
        for tfm in self._framework.transformations:
            if tfm.output_channel == channel:
                return (tfm._component_id, "transformation", tfm._label)
        return ("broker", "broker", "")

    def _resolve_label(self, component_id: str) -> str:
        """Get the label for a component by its ID."""
        if self._framework is None:
            return ""
        for comp in (
            list(self._framework.sources)
            + list(self._framework.transformations)
            + list(self._framework.destinations)
        ):
            if getattr(comp, "_component_id", None) == component_id:
                return getattr(comp, "_label", "")
        return ""

    def _get_component_sub_patterns(self, component_id: str) -> list[str]:
        """Get subscription patterns for a component."""
        if self._framework is None:
            return []
        for tfm in self._framework.transformations:
            if tfm._component_id == component_id:
                return list(tfm.input_channels)
        for dest in self._framework.destinations:
            if dest._component_id == component_id:
                return [dest.channel_pattern]
        return []

    def _find_receive_channel(self, component_id: str, trace_id: str) -> str:
        """Determine which published channel this component received from.

        Uses topology (subscription patterns) to match against published
        channels in this journey.
        """
        patterns = self._get_component_sub_patterns(component_id)
        if not patterns or self._journey_store is None:
            return ""
        journey = self._journey_store.get_journey(trace_id)
        if not journey:
            return ""
        published_channels = [s["channel"] for s in journey if s["stage"] == "PUBLISHED"]
        for channel in published_channels:
            for pattern in patterns:
                if SubscriptionRegistry.matches(pattern, channel):
                    return channel
        return ""

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

            msg_id = str(getattr(message, "id", ""))
            trace_id = self._get_or_create_trace_id(msg_id)

            value = getattr(message, "value", None)
            value_preview = repr(value)
            if len(value_preview) > 120:
                value_preview = value_preview[:120] + "..."
            event = ObservatoryEvent(
                type=EventType.MESSAGE,
                data={
                    "channel": channel,
                    "key": getattr(message, "key", None),
                    "value_preview": value_preview,
                    "tags": dict(getattr(message, "tags", {})),
                    "subscriber_count": subscriber_count,
                    "message_id": msg_id,
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("message.published", event.data)

            # Store complete message details
            if self._message_store is not None:
                try:
                    msg_dict = message.to_dict() if hasattr(message, "to_dict") else {}
                    self._message_store.store(msg_id, channel, msg_dict, subscriber_count, trace_id)
                except Exception:
                    pass

            # Record PUBLISHED journey step with resolved publisher
            if self._journey_store is not None:
                try:
                    pub_id, pub_type, pub_label = self._resolve_publisher(channel)
                    parent_id = self._get_parent_id(msg_id)
                    self._journey_store.add_step(
                        trace_id,
                        JourneyStep(
                            stage="PUBLISHED",
                            component_id=pub_id,
                            component_type=pub_type,
                            channel=channel,
                            message_id=msg_id,
                            parent_message_id=parent_id,
                            label=pub_label,
                        ),
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.debug("Observatory hook error", hook="on_message_published", error=str(e))

    async def on_message_received(
        self,
        component_id: str,
        component_type: str,
        message: Message,
    ) -> None:
        """Called when a transformation/destination receives a message."""
        try:
            if self._journey_store is None:
                return
            msg_id = str(getattr(message, "id", ""))
            trace_id = self._trace_ids.get(msg_id, msg_id)
            stage = "DELIVERED" if component_type == "destination" else "RECEIVED"
            label = self._resolve_label(component_id)
            channel = self._find_receive_channel(component_id, trace_id)
            self._journey_store.add_step(
                trace_id,
                JourneyStep(
                    stage=stage,
                    component_id=component_id,
                    component_type=component_type,
                    channel=channel,
                    message_id=msg_id,
                    parent_message_id=self._get_parent_id(msg_id),
                    label=label,
                ),
            )
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_message_received", error=str(e))

    async def on_message_processed(
        self,
        component_id: str,
        component_type: str,
        input_message: Message,
        output_messages: list[Message],
        output_channel: str,
    ) -> None:
        """Called after a transformation has produced its outputs."""
        try:
            input_id = str(getattr(input_message, "id", ""))
            trace_id = self._trace_ids.get(input_id, input_id)

            if self._journey_store is not None:
                label = self._resolve_label(component_id)
                self._journey_store.add_step(
                    trace_id,
                    JourneyStep(
                        stage="PROCESSED",
                        component_id=component_id,
                        component_type=component_type,
                        channel=output_channel,
                        message_id=input_id,
                        parent_message_id=self._get_parent_id(input_id),
                        label=label,
                    ),
                )

            # Link output messages to the same trace_id + parent relationship
            for out_msg in output_messages:
                out_id = str(getattr(out_msg, "id", ""))
                if out_id and out_id != input_id:
                    self._set_trace_id(out_id, trace_id)
                    self._set_parent_id(out_id, input_id)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_message_processed", error=str(e))

    async def on_component_state_change(
        self,
        component_id: str,
        component_type: str,
        old_state: str,
        new_state: str,
    ) -> None:
        """Called when a pipeline component changes state."""
        try:
            label = ""
            if self._framework is not None:
                for comp in (
                    list(self._framework.sources)
                    + list(self._framework.transformations)
                    + list(self._framework.destinations)
                ):
                    if getattr(comp, "_component_id", None) == component_id:
                        label = getattr(comp, "_label", "")
                        break
            event = ObservatoryEvent(
                type=EventType.COMPONENT_STATE,
                data={
                    "component_id": component_id,
                    "component_type": component_type,
                    "old_state": old_state,
                    "new_state": new_state,
                    "label": label,
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

    # --- Message Inspector ---

    def get_message_detail(self, message_id: str) -> dict | None:
        """Return complete message detail + journey for the WS handler."""
        if self._message_store is None:
            return None
        detail = self._message_store.get(message_id)
        if detail is None:
            return None
        trace_id = detail.get("trace_id", message_id)
        journey: list[dict] = []
        if self._journey_store is not None:
            journey = self._journey_store.get_journey(trace_id) or []
        return {**detail, "journey": journey}

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
            components.append(
                {
                    "component_id": source._component_id,
                    "component_type": "source",
                    "state": state,
                    "label": source._label,
                    "description": getattr(source, "_description", ""),
                }
            )
        for tfm in self._framework.transformations:
            state = "running" if tfm._running else "created"
            components.append(
                {
                    "component_id": tfm._component_id,
                    "component_type": "transformation",
                    "state": state,
                    "label": tfm._label,
                    "description": getattr(tfm, "_description", ""),
                }
            )
        for dest in self._framework.destinations:
            state = "running" if dest._running else "created"
            components.append(
                {
                    "component_id": dest._component_id,
                    "component_type": "destination",
                    "state": state,
                    "label": dest._label,
                    "description": getattr(dest, "_description", ""),
                }
            )
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
            nodes.append(
                {
                    "component_id": source._component_id,
                    "component_type": "source",
                    "state": state,
                    "label": source._label,
                    "description": getattr(source, "_description", ""),
                    "channels": {
                        "publishes": [source.channel],
                        "subscribes": [],
                    },
                }
            )
            publishers.append((source._component_id, source.channel))

        for tfm in self._framework.transformations:
            state = "running" if tfm._running else "created"
            nodes.append(
                {
                    "component_id": tfm._component_id,
                    "component_type": "transformation",
                    "state": state,
                    "label": tfm._label,
                    "description": getattr(tfm, "_description", ""),
                    "channels": {
                        "publishes": [tfm.output_channel],
                        "subscribes": list(tfm.input_channels),
                    },
                }
            )
            publishers.append((tfm._component_id, tfm.output_channel))
            for ch in tfm.input_channels:
                subscribers.append((tfm._component_id, ch))

        for dest in self._framework.destinations:
            state = "running" if dest._running else "created"
            nodes.append(
                {
                    "component_id": dest._component_id,
                    "component_type": "destination",
                    "state": state,
                    "label": dest._label,
                    "description": getattr(dest, "_description", ""),
                    "channels": {
                        "publishes": [],
                        "subscribes": [dest.channel_pattern],
                    },
                }
            )
            subscribers.append((dest._component_id, dest.channel_pattern))

        # Compute edges
        edges: list[dict[str, str]] = []
        for pub_id, channel in publishers:
            for sub_id, pattern in subscribers:
                if pub_id == sub_id:
                    continue
                if SubscriptionRegistry.matches(pattern, channel) or pattern.startswith(channel + "."):
                    edges.append(
                        {
                            "source_id": pub_id,
                            "target_id": sub_id,
                            "channel": channel,
                            "pattern": pattern,
                        }
                    )

        return {"nodes": nodes, "edges": edges}
