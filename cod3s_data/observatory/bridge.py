"""Observatory Bridge - sole interface between COD3S framework and Observatory."""

from __future__ import annotations

import contextlib
from collections import OrderedDict
from datetime import UTC
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


def _coerce_ints_to_floats(value: Any) -> Any:
    """Convert plain ints to floats, recursing into dicts/lists.

    Booleans are preserved (they're a subclass of int but represent a
    distinct domain). Used by ``update_param`` to keep numeric param
    values type-stable across publishes — see the docstring there.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, dict):
        return {k: _coerce_ints_to_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_ints_to_floats(v) for v in value]
    return value


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
        # Component lookups, built once per framework rather than scanned per
        # message: `_resolve_label` and `_resolve_publisher` sit on the publish
        # and receive hooks, and both used to walk every component every time.
        self._by_component_id: dict[str, Any] = {}
        self._publisher_of_channel: dict[str, tuple[str, str, str]] = {}
        self._indexed_framework: Any = None

    # --- Lifecycle ---

    async def start(self) -> None:
        """Start the Observatory server."""
        if self._server is not None:
            await self._server.start()

    async def stop(self) -> None:
        """Stop the Observatory server."""
        # Anything still queued goes out before the sockets close.
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.stop()

        # Close all WebSocket connections
        try:
            if self._ws is not None:
                for client_id in list(self._ws._clients.keys()):
                    with contextlib.suppress(Exception):
                        await self._ws._clients[client_id].close()
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

    def _observed_trace(self, message_id: str) -> str | None:
        """The trace of a message whose publication was recorded, else None.

        A message enters `_trace_ids` when its publication is observed, so the
        absence of an entry means the sampler skipped it. The reception and
        processing hooks used to record their steps regardless, which both cost
        work on messages nothing would ever show, and produced journeys holding
        receptions whose publication was missing — the Inspector then had to
        invent a parent for them.
        """
        return self._trace_ids.get(message_id)

    # --- Component resolution ---

    def _ensure_index(self) -> None:
        """Build the component lookups, once per framework.

        `_framework` is assigned as a plain attribute (framework.py and the
        tests both do it), so there is no setter to hook: the index is rebuilt
        whenever the attribute points at a different object.
        """
        framework = self._framework
        if framework is self._indexed_framework:
            return
        by_id: dict[str, Any] = {}
        publishers: dict[str, tuple[str, str, str]] = {}
        if framework is not None:
            for source in framework.sources:
                by_id[getattr(source, "_component_id", "")] = source
                publishers[source.channel] = (
                    source._component_id,
                    "source",
                    source._label,
                )
            for tfm in framework.transformations:
                by_id[getattr(tfm, "_component_id", "")] = tfm
                # A source already publishing this channel wins, as in the
                # sequential scan this replaces.
                publishers.setdefault(
                    tfm.output_channel,
                    (tfm._component_id, "transformation", tfm._label),
                )
            for dest in framework.destinations:
                by_id[getattr(dest, "_component_id", "")] = dest
        self._by_component_id = by_id
        self._publisher_of_channel = publishers
        self._indexed_framework = framework

    def _resolve_publisher(self, channel: str) -> tuple[str, str, str]:
        """Find which component publishes to a given channel.

        Returns (component_id, component_type, label).
        """
        if self._framework is None:
            return ("broker", "broker", "")
        self._ensure_index()
        return self._publisher_of_channel.get(channel, ("broker", "broker", ""))

    def _resolve_label(self, component_id: str) -> str:
        """Get the label for a component by its ID."""
        if self._framework is None:
            return ""
        self._ensure_index()
        component = self._by_component_id.get(component_id)
        if component is None:
            return ""
        return str(getattr(component, "_label", "") or "")

    def _get_component_sub_patterns(self, component_id: str) -> list[str]:
        """Get subscription patterns for a component."""
        if self._framework is None:
            return []
        self._ensure_index()
        component = self._by_component_id.get(component_id)
        if component is None:
            return []
        if hasattr(component, "input_channels"):
            return list(component.input_channels)
        if hasattr(component, "channel_pattern"):
            return [component.channel_pattern]
        return []

    def _find_receive_channel(self, component_id: str, trace_id: str, message_id: str) -> str:
        """Determine which published channel this component received from.

        Two facts identify it, and both are needed. The message carries the
        `message_id` of the PUBLISHED step that put it on the broker, and the
        channel it arrived on necessarily matches one of the component's
        subscription patterns. Scanning backwards takes the most recent
        publication satisfying both, which is the one just delivered.

        Matching on the pattern alone — what this did before — was wrong as soon
        as a trace published several channels a component subscribes to: it
        returned the first in journey order, so five of the six `sensors.egm.*`
        receptions of a six-sensor unpack were attributed to the first channel.
        Matching on the id alone is not enough either: a component may republish
        under the same id, and then only the pattern says which publication was
        this component's input.

        Falls back to the pattern alone when no PUBLISHED step carries the id —
        sampling drops publications but not receptions, and a long-running trace
        can be evicted while its messages are still in flight.
        """
        if self._journey_store is None:
            return ""
        steps = self._journey_store.get_steps(trace_id)
        if not steps:
            return ""
        patterns = self._get_component_sub_patterns(component_id)

        def subscribed(channel: str) -> bool:
            return not patterns or any(
                SubscriptionRegistry.matches(pattern, channel) for pattern in patterns
            )

        if message_id:
            for step in reversed(steps):
                if (
                    step.stage == "PUBLISHED"
                    and step.message_id == message_id
                    and subscribed(step.channel)
                ):
                    return step.channel

        if not patterns:
            return ""
        for step in reversed(steps):
            if step.stage == "PUBLISHED" and subscribed(step.channel):
                return step.channel
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
            # Queued, not awaited: this runs inside `broker.publish()`, and the
            # pipeline should not wait on a socket to keep moving.
            self._ws.queue_event("message.published", event.data)

            # Store complete message details
            if self._message_store is not None:
                with contextlib.suppress(Exception):
                    self._message_store.store(
                        msg_id,
                        channel,
                        {},
                        subscriber_count,
                        trace_id,
                        # The buffered event's own timestamp, so a row hydrated
                        # from the snapshot and its detail show the same instant.
                        observed_at=event.timestamp.isoformat(),
                        # Rendered only if the message is ever opened: the dump
                        # was being paid on every publication for the few that
                        # someone actually inspects.
                        message=message,
                    )

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
            trace_id = self._observed_trace(msg_id)
            if trace_id is None:
                return
            stage = "DELIVERED" if component_type == "destination" else "RECEIVED"
            label = self._resolve_label(component_id)
            channel = self._find_receive_channel(component_id, trace_id, msg_id)
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
            trace_id = self._observed_trace(input_id)
            if trace_id is None:
                return

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
            label = self._resolve_label(component_id)
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
        value: float | dict[str, Any],
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

    async def on_param_updated(
        self,
        component_id: str,
        param_name: str,
        old_value: Any,
        new_value: Any,
        *,
        channel: str = "",
    ) -> None:
        """Called when a ParameterStore rebinds a component attribute.

        Emitted as EventType.PARAM, not COMPONENT_STATE: this payload carries no
        component_type or new_state, and /api/topology keeps only the latest
        event per component id, so filing it under COMPONENT_STATE erased the
        node of every component holding a ParamRef.
        """
        try:
            event = ObservatoryEvent(
                type=EventType.PARAM,
                data={
                    "component_id": component_id,
                    "param_name": param_name,
                    "channel": channel,
                    "old_value": old_value,
                    "new_value": new_value,
                    "label": self._resolve_label(component_id),
                },
            )
            self._buffer.push(event)
            await self._ws.broadcast_event("param.updated", event.data)
        except Exception as e:
            logger.debug("Observatory hook error", hook="on_param_updated", error=str(e))

    async def update_param(
        self, channel: str, value: Any, key: str | None = None
    ) -> dict[str, Any]:
        """Publish a parameter update on the broker.

        Same effect as any external publisher pushing on ``channel``: the
        ``ParameterStore`` subscribed to that channel rebinds its component
        attribute. ``key``, when supplied, wraps ``value`` in a single-key
        dict so consumers using ``ParamRef.key`` can extract their slice.

        Plain ints in the payload are coerced to floats. Without this,
        downstream type-strict sinks (notably InfluxDB, which freezes the
        field type on the first write) silently reject updates when the
        initial YAML default was a float (``10.0``) and a later operator
        edit comes in as an int (``50``). All numeric setpoints/tolerances
        are floats by convention, so the coercion is harmless.
        """
        from datetime import datetime

        from cod3s_data.core.message import Message

        if self._framework is None:
            return {"status": "error", "message": "No framework connected"}

        broker = self._framework.broker
        payload = {key: value} if key else value
        payload = _coerce_ints_to_floats(payload)
        message = Message(
            key=channel,
            timestamp=datetime.now(UTC),
            value=payload,
            tags={},
        )
        try:
            result = await broker.publish(channel, message)
            return {
                "status": "ok",
                "channel": channel,
                "subscriber_count": result.subscriber_count,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_editable_params(self) -> list[dict[str, Any]]:
        """Snapshot of all parameters declared via ``ParamRef``.

        The factory attaches ``_param_stores`` to each component when it
        resolves a ``ParamRef``. We surface those so the Observatory UI can
        render an editor without inventing a new registration mechanism.
        """
        if self._framework is None:
            return []
        out: list[dict[str, Any]] = []
        for comp in (
            list(self._framework.sources)
            + list(self._framework.transformations)
            + list(self._framework.destinations)
        ):
            for store in getattr(comp, "_param_stores", []):
                out.append(
                    {
                        "component_id": getattr(comp, "_component_id", ""),
                        "component_label": getattr(comp, "_label", ""),
                        "param_name": store.param_name,
                        "channel": store.ref,
                        "key": store.dict_key,
                        "default": store.default,
                        "current": store.current,
                    }
                )
        return out

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

    def get_message_detail(self, message_id: str) -> dict[str, Any] | None:
        """Return complete message detail + journey for the WS handler."""
        if self._message_store is None:
            return None
        detail = self._message_store.get(message_id)
        if detail is None:
            return None
        trace_id = detail.get("trace_id", message_id)
        journey: list[dict[str, Any]] = []
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
        result: dict[str, str] = await self._framework.handle_pipeline_command("start")
        return result

    async def stop_pipeline(self) -> dict[str, str]:
        """Stop the pipeline via framework."""
        if self._framework is None:
            return {"status": "error", "message": "No framework connected"}
        result: dict[str, str] = await self._framework.handle_pipeline_command("stop")
        return result

    async def restart_pipeline(self) -> dict[str, str]:
        """Restart the pipeline via framework."""
        if self._framework is None:
            return {"status": "error", "message": "No framework connected"}
        result: dict[str, str] = await self._framework.handle_pipeline_command("restart")
        return result

    def get_pipeline_state(self) -> str:
        """Get current pipeline state."""
        if self._framework is None:
            return "unknown"
        state: str = self._framework._pipeline_state.value
        return state

    def get_pipeline_info(self) -> dict[str, str]:
        """Get pipeline display metadata for the Observatory UI."""
        if self._framework is None:
            return {"name": "", "display_name": "COD3S Observatory", "subtitle": ""}
        config = self._framework.config
        return {
            "name": config.name,
            "display_name": config.display_name or config.name,
            "subtitle": config.subtitle or "",
        }

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

    @staticmethod
    def _param_channels(component: Any) -> list[dict[str, str]]:
        """Parameter channels a component reads through its ``ParameterStore``s."""
        return [
            {"param": store.param_name, "channel": store.ref}
            for store in getattr(component, "_param_stores", [])
        ]

    def get_topology_snapshot(self) -> dict[str, Any]:
        """Get enriched topology with nodes (including channels) and computed edges.

        Edges come in two kinds. ``data`` edges pair a published channel with a
        subscribed pattern, the ordinary flow. ``parameter`` edges pair it with a
        ``ParamRef``: that consumer subscribes through its ``ParameterStore``,
        never through ``input_channels``, so without this second pass a channel
        that only feeds parameters would appear connected to nothing.
        """
        if self._framework is None:
            return {"nodes": [], "edges": []}

        nodes: list[dict[str, Any]] = []
        publishers: list[tuple[str, str]] = []  # (component_id, channel)
        subscribers: list[tuple[str, str]] = []  # (component_id, pattern)
        param_subscribers: list[tuple[str, str, str]] = []  # (component_id, ref, param)

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
                        "parameters": self._param_channels(source),
                    },
                }
            )
            publishers.append((source._component_id, source.channel))
            param_subscribers += [
                (source._component_id, ref["channel"], ref["param"])
                for ref in self._param_channels(source)
            ]

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
                        "parameters": self._param_channels(tfm),
                    },
                }
            )
            publishers.append((tfm._component_id, tfm.output_channel))
            for ch in tfm.input_channels:
                subscribers.append((tfm._component_id, ch))
            param_subscribers += [
                (tfm._component_id, ref["channel"], ref["param"])
                for ref in self._param_channels(tfm)
            ]

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
                        "parameters": self._param_channels(dest),
                    },
                }
            )
            subscribers.append((dest._component_id, dest.channel_pattern))
            param_subscribers += [
                (dest._component_id, ref["channel"], ref["param"])
                for ref in self._param_channels(dest)
            ]

        # Compute edges
        edges: list[dict[str, str]] = []
        for pub_id, channel in publishers:
            for sub_id, pattern in subscribers:
                if pub_id == sub_id:
                    continue
                if SubscriptionRegistry.matches(pattern, channel) or pattern.startswith(
                    channel + "."
                ):
                    edges.append(
                        {
                            "source_id": pub_id,
                            "target_id": sub_id,
                            "channel": channel,
                            "pattern": pattern,
                            "kind": "data",
                        }
                    )

        for pub_id, channel in publishers:
            for sub_id, ref, param in param_subscribers:
                if pub_id == sub_id:
                    continue
                if SubscriptionRegistry.matches(ref, channel) or ref.startswith(channel + "."):
                    edges.append(
                        {
                            "source_id": pub_id,
                            "target_id": sub_id,
                            "channel": channel,
                            "pattern": ref,
                            "kind": "parameter",
                            "param": param,
                        }
                    )

        return {"nodes": nodes, "edges": edges}
