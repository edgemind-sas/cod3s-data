"""Built-in transformations for COD3S Data Framework."""

import asyncio
import contextlib
import re
import statistics
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cod3s_data.broker.base import Broker
from cod3s_data.core.message import Message
from cod3s_data.transformations.base import StatefulTransform, StatelessTransform, Transformation


class FilterTransform(StatelessTransform):
    """Filter messages by predicate."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        predicate: Callable[[Message], bool],
    ) -> None:
        def filter_fn(msg: Message) -> Message | None:
            return msg if predicate(msg) else None

        super().__init__(broker, input_channels, output_channel, filter_fn)


class MapTransform(StatelessTransform):
    """Transform message values."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        map_fn: Callable[[Any], Any],
    ) -> None:
        def transform_fn(msg: Message) -> Message:
            new_value = map_fn(msg.value)
            return msg.with_value(new_value)

        super().__init__(broker, input_channels, output_channel, transform_fn)


def _default_aggregation(msgs: list[Message]) -> Any:
    """Default aggregation: average of message values."""
    return sum(msg.value for msg in msgs) / len(msgs)


class AggregateTransform(StatefulTransform):
    """Aggregate messages over time or count windows."""

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        window_type: str = "count",
        window_size: int | None = None,
        window_duration: float | None = None,
        aggregation_fn: Callable[[list[Message]], Any] = _default_aggregation,
    ) -> None:
        super().__init__(broker, input_channels, output_channel)
        self.window_type = window_type
        self.window_size = window_size
        self.window_duration = window_duration
        self.aggregation_fn = aggregation_fn

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Aggregate messages in windows."""
        if "window" not in state:
            state["window"] = []
            state["window_start"] = datetime.now(UTC)

        result = None

        # Time-based window - check before adding message
        if self.window_type == "time" and self.window_duration and state["window"]:
            elapsed = (datetime.now(UTC) - state["window_start"]).total_seconds()
            if elapsed >= self.window_duration:
                result = self._create_aggregate(state["window"], message.key)
                state["window"] = []
                state["window_start"] = datetime.now(UTC)

        # Add message to window
        state["window"].append(message)

        # Count-based window - check after adding
        if (
            self.window_type == "count"
            and self.window_size
            and len(state["window"]) >= self.window_size
        ):
            result = self._create_aggregate(state["window"], message.key)
            state["window"] = []
            state["window_start"] = datetime.now(UTC)

        return result

    def _create_aggregate(self, messages: list[Message], key: str) -> Message:
        """Create aggregated message."""
        aggregated_value = self.aggregation_fn(messages)
        return Message(
            key=f"{key}_agg",
            timestamp=datetime.now(UTC),
            value=aggregated_value,
            tags={},
        )


class AlarmTransform(StatefulTransform):
    """Alarm transformation that emits on state change (OK/ALARM).

    Monitors a stream of numeric messages and emits an alarm message when
    a value crosses configured min/max thresholds. Only emits on state
    transitions (OK → ALARM, ALARM → OK) to avoid alarm flooding.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        if min_value is None and max_value is None:
            raise ValueError("AlarmTransform requires at least one of min_value or max_value")
        super().__init__(broker, input_channels, output_channel)
        self.min_value = min_value
        self.max_value = max_value

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Check thresholds and emit alarm on state change."""
        value = message.value
        if not isinstance(value, int | float):
            return None

        # Determine alarm condition
        alarm_type: str | None = None
        threshold: float | None = None
        if self.max_value is not None and value > self.max_value:
            alarm_type = "max"
            threshold = self.max_value
        elif self.min_value is not None and value < self.min_value:
            alarm_type = "min"
            threshold = self.min_value

        is_alarm = alarm_type is not None
        prev_status = state.get("status", "OK")

        if is_alarm and prev_status == "OK":
            # Transition OK → ALARM
            state["status"] = "ALARM"
            state["alarm_type"] = alarm_type
            state["threshold"] = threshold
            return Message(
                key=f"{message.key}.alarm",
                timestamp=message.timestamp,
                value={
                    "original_value": value,
                    "alarm_type": alarm_type,
                    "threshold": threshold,
                    "status": "ACTIVE",
                },
                tags={},
            )
        elif not is_alarm and prev_status == "ALARM":
            # Transition ALARM → OK
            prev_alarm_type = state.get("alarm_type", "unknown")
            prev_threshold = state.get("threshold")
            state["status"] = "OK"
            return Message(
                key=f"{message.key}.alarm",
                timestamp=message.timestamp,
                value={
                    "original_value": value,
                    "alarm_type": prev_alarm_type,
                    "threshold": prev_threshold,
                    "status": "CLEARED",
                },
                tags={},
            )

        # No state change → no message
        return None


class ThrottleTransform(StatefulTransform):
    """Throttle messages to at most one per interval.

    Forwards the first message immediately, then suppresses subsequent
    messages until ``interval`` seconds have elapsed since the last emit.

    With ``per_key=True``, each ``message.key`` is throttled independently —
    useful when downsampling a wildcard-subscribed stream where every key
    should keep its own emit cadence (e.g. one InfluxDB point every 100 ms
    per sensor channel).
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        interval: float = 1.0,
        per_key: bool = False,
    ) -> None:
        super().__init__(broker, input_channels, output_channel)
        self.interval = interval
        self.per_key = per_key

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Forward message only if interval has elapsed since last emit."""
        import time

        now = time.monotonic()
        if self.per_key:
            per_key_state: dict[str, float] = state.setdefault("last_emit", {})
            last_emit = per_key_state.get(message.key, 0.0)
            if now - last_emit >= self.interval:
                per_key_state[message.key] = now
                return message
            return None

        last_emit = state.get("last_emit", 0.0)
        if now - last_emit >= self.interval:
            state["last_emit"] = now
            return message
        return None


class UnpackTransform(Transformation):
    """Unpack a dict-valued message into one message per key.

    Each entry in the dict becomes a separate message published on a
    dedicated sub-channel ``{output_channel}.{key}``:

    - key: the dict key name
    - value: the corresponding scalar value
    - timestamp: inherited from the original message
    - tags: inherited from the original message

    Non-dict values pass through unchanged on ``output_channel``.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
    ) -> None:
        super().__init__(broker, input_channels, output_channel)

    async def transform(self, message: Message) -> Message | list[Message] | None:
        """Fallback for non-dict values (called by base ``_process_message``)."""
        if not isinstance(message.value, dict):
            return message
        # Dict case is handled entirely by _process_message override
        return None

    async def _process_message(self, message: Message) -> None:
        """Route each dict entry to ``{output_channel}.{key}``."""
        try:
            # Observatory: RECEIVED
            if self._bridge is not None:
                try:  # noqa: SIM105
                    await self._bridge.on_message_received(
                        self._component_id, "transformation", message
                    )
                except Exception:
                    pass

            if not isinstance(message.value, dict):
                # Non-dict: delegate to base (publishes on output_channel)
                results = await self.transform(message)
                if results and self._bridge is not None:
                    try:  # noqa: SIM105
                        out_list = results if isinstance(results, list) else [results]
                        await self._bridge.on_message_processed(
                            self._component_id,
                            "transformation",
                            message,
                            out_list,
                            self.output_channel,
                        )
                    except Exception:
                        pass
                if results:
                    for result in results if isinstance(results, list) else [results]:
                        await self.broker.publish(self.output_channel, result)
                return

            if not message.value:
                return

            # Dict: one message per entry, on {output_channel}.{key}
            out_messages: list[Message] = [
                Message(key=k, timestamp=message.timestamp, value=v, tags=message.tags)
                for k, v in message.value.items()
            ]

            # Observatory: PROCESSED, before publishing and not after. It is
            # what ties each output to the input it came from; publishing first
            # meant the broker announced a message the Observatory did not yet
            # know the parent of, which opened a fresh trace per output — the
            # real trace then lost its PUBLISHED steps, and the orphans crowded
            # out genuine journeys. The base class already had this order.
            if out_messages and self._bridge is not None:
                try:  # noqa: SIM105
                    await self._bridge.on_message_processed(
                        self._component_id,
                        "transformation",
                        message,
                        out_messages,
                        self.output_channel,
                    )
                except Exception:
                    pass

            for out_msg in out_messages:
                await self.broker.publish(f"{self.output_channel}.{out_msg.key}", out_msg)

        except Exception:
            pass


class _SlidingWindowTransform(StatefulTransform):
    """Base for sliding-window aggregations (mean, median, ...).

    Per-key buffer; emits on every input message once min_samples is reached.
    Differs from AggregateTransform (tumbling, global): this is sliding, per-key.

    Optional ``key_suffix`` is appended to the output ``message.key`` (and
    re-published on a sub-channel ``{output_channel}.{new_key}``). This lets
    smoothed signals coexist with their raw counterparts in downstream sinks
    that key by ``message.key`` (e.g. InfluxDB measurements).
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        *,
        window_type: str = "count",
        window_size: int | None = None,
        window_duration: float | None = None,
        min_samples: int = 1,
        key_suffix: str = "",
    ) -> None:
        if window_type not in ("count", "time"):
            raise ValueError(f"window_type must be 'count' or 'time', got {window_type!r}")
        if window_type == "count" and not window_size:
            raise ValueError("window_type='count' requires window_size")
        if window_type == "time" and not window_duration:
            raise ValueError("window_type='time' requires window_duration")
        super().__init__(broker, input_channels, output_channel)
        self.window_type = window_type
        self.window_size = window_size
        self.window_duration = window_duration
        self.min_samples = min_samples
        self.key_suffix = key_suffix

    def _aggregate(self, values: list[float]) -> float:
        raise NotImplementedError

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        if not isinstance(message.value, int | float):
            return None

        buffers: dict[str, deque[tuple[datetime, float]]] = state.setdefault("buffers", {})
        buf = buffers.setdefault(message.key, deque())
        buf.append((message.timestamp, float(message.value)))

        if self.window_type == "count":
            assert self.window_size is not None
            while len(buf) > self.window_size:
                buf.popleft()
        else:  # time
            assert self.window_duration is not None
            cutoff = message.timestamp.timestamp() - self.window_duration
            while buf and buf[0][0].timestamp() < cutoff:
                buf.popleft()

        if len(buf) < self.min_samples:
            return None

        values = [v for _, v in buf]
        new_key = f"{message.key}{self.key_suffix}" if self.key_suffix else message.key
        return Message(
            key=new_key,
            timestamp=message.timestamp,
            value=self._aggregate(values),
            tags=message.tags,
        )

    async def _process_message(self, message: Message) -> None:
        """Override base routing when ``key_suffix`` is set.

        When ``key_suffix`` is non-empty, publish on a per-key sub-channel
        ``{output_channel}.{new_key}`` (mirroring :class:`UnpackTransform`)
        so downstream wildcards like ``output_channel.*`` dispatch by key
        without causing duplicate deliveries via deeper wildcards
        (``sensors.**``). When ``key_suffix`` is empty the base behavior
        (single publish on ``output_channel``) is used unchanged.
        """
        if not self.key_suffix:
            await super()._process_message(message)
            return

        try:
            if self._bridge is not None:
                try:  # noqa: SIM105
                    await self._bridge.on_message_received(
                        self._component_id, "transformation", message
                    )
                except Exception:
                    pass

            results = await self.transform(message)
            if not results:
                return

            out_list = results if isinstance(results, list) else [results]

            # PROCESSED first, as in the base class: it is what links an output
            # to its input, and the broker must not announce a message whose
            # parent the Observatory has not been told about yet.
            if self._bridge is not None:
                try:  # noqa: SIM105
                    await self._bridge.on_message_processed(
                        self._component_id,
                        "transformation",
                        message,
                        out_list,
                        self.output_channel,
                    )
                except Exception:
                    pass

            for result in out_list:
                await self.broker.publish(f"{self.output_channel}.{result.key}", result)
        except Exception:
            pass


class MovingAverageTransform(_SlidingWindowTransform):
    """Sliding-window mean per key.

    Emits one smoothed message per input message (preserves key, timestamp, tags),
    once at least ``min_samples`` values are buffered for that key.

    Use this for time-series smoothing on per-sensor channels (e.g. ``sensors.egm.*``).
    For tumbling-window aggregation (one output per closed window) use
    :class:`AggregateTransform` instead.
    """

    def _aggregate(self, values: list[float]) -> float:
        return sum(values) / len(values)


class MedianFilterTransform(_SlidingWindowTransform):
    """Sliding-window median per key.

    Like :class:`MovingAverageTransform` but uses the median, which is more
    robust to isolated spikes/outliers in the buffer.
    """

    def _aggregate(self, values: list[float]) -> float:
        return statistics.median(values)


class DeviationFilterTransform(StatelessTransform):
    """Reject or clip values that deviate from a setpoint by more than a tolerance.

    The setpoint can be a single scalar (applied to all keys) or a dict
    ``{key: setpoint}`` for per-key thresholds. Messages whose key is not
    in the dict pass through unchanged. Non-numeric values pass through.

    Exactly one of ``tolerance_pct`` (percentage of the setpoint) or
    ``tolerance_abs`` (absolute units) must be provided.

    - mode='reject': drop messages outside the tolerance band (return None)
    - mode='clip':   clamp value to ``[setpoint - tol, setpoint + tol]``
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        *,
        setpoint: float | dict[str, float],
        tolerance_pct: float | None = None,
        tolerance_abs: float | None = None,
        mode: str = "reject",
        key_suffix: str = "",
    ) -> None:
        if (tolerance_pct is None) == (tolerance_abs is None):
            raise ValueError(
                "DeviationFilterTransform requires exactly one of tolerance_pct or tolerance_abs"
            )
        if mode not in ("reject", "clip"):
            raise ValueError(f"mode must be 'reject' or 'clip', got {mode!r}")

        self.setpoint = setpoint
        self.tolerance_pct = tolerance_pct
        self.tolerance_abs = tolerance_abs
        self.mode = mode
        self.key_suffix = key_suffix

        def filter_fn(msg: Message) -> Message | None:
            return self._apply(msg)

        super().__init__(broker, input_channels, output_channel, filter_fn)

    def _resolve_setpoint(self, key: str) -> float | None:
        if isinstance(self.setpoint, dict):
            return self.setpoint.get(key)
        return float(self.setpoint)

    def _tolerance(self, sp: float) -> float:
        if self.tolerance_abs is not None:
            return self.tolerance_abs
        assert self.tolerance_pct is not None
        return abs(sp) * self.tolerance_pct / 100.0

    def _apply(self, msg: Message) -> Message | None:
        if not isinstance(msg.value, int | float):
            return self._with_suffix(msg)
        sp = self._resolve_setpoint(msg.key)
        if sp is None:
            return self._with_suffix(msg)

        tol = self._tolerance(sp)
        value = float(msg.value)
        deviation = abs(value - sp)

        if deviation <= tol:
            return self._with_suffix(msg)

        if self.mode == "reject":
            return None
        clipped = max(sp - tol, min(sp + tol, value))
        return self._with_suffix(msg.with_value(clipped))

    def _with_suffix(self, msg: Message) -> Message:
        if not self.key_suffix:
            return msg
        return Message(
            key=f"{msg.key}{self.key_suffix}",
            timestamp=msg.timestamp,
            value=msg.value,
            tags=msg.tags,
        )


class RelativeAlarmTransform(StatefulTransform):
    """Alarm on |value - setpoint| > tolerance, per-key state, transitions only.

    Generalises absolute-threshold alarms (cf. :class:`AlarmTransform`) by
    monitoring deviation from a target value (the setpoint). Emits only on
    state transitions OK -> ACTIVE and ACTIVE -> CLEARED, suppressing repeats.

    State is tracked **per message key**, so a single transform on a wildcard
    channel (e.g. ``sensors.smoothed.*``) handles each sensor independently.

    The setpoint can be a scalar (applied to every key) or a per-key dict.
    Messages with no setpoint mapping or non-numeric values are ignored.

    Exactly one of ``tolerance_pct`` or ``tolerance_abs`` must be provided.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        *,
        setpoint: float | dict[str, float],
        tolerance_pct: float | None = None,
        tolerance_abs: float | None = None,
        alarm_type_label: str = "relative_threshold",
    ) -> None:
        if (tolerance_pct is None) == (tolerance_abs is None):
            raise ValueError(
                "RelativeAlarmTransform requires exactly one of tolerance_pct or tolerance_abs"
            )
        super().__init__(broker, input_channels, output_channel)
        self.setpoint = setpoint
        self.tolerance_pct = tolerance_pct
        self.tolerance_abs = tolerance_abs
        self.alarm_type_label = alarm_type_label

    def _resolve_setpoint(self, key: str) -> float | None:
        if isinstance(self.setpoint, dict):
            return self.setpoint.get(key)
        return float(self.setpoint)

    def _tolerance(self, sp: float) -> float:
        if self.tolerance_abs is not None:
            return self.tolerance_abs
        assert self.tolerance_pct is not None
        return abs(sp) * self.tolerance_pct / 100.0

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Emit an alarm when the message key crosses into or out of tolerance.

        Args:
            message: Incoming measurement; ignored unless its value is numeric
            state: Per-transform state holding the last status of each key

        Returns:
            An alarm message on an OK -> ACTIVE or ACTIVE -> CLEARED
            transition, and None otherwise — including when the key has no
            setpoint, and when the deviation has not changed side.
        """
        if not isinstance(message.value, int | float):
            return None
        sp = self._resolve_setpoint(message.key)
        if sp is None:
            return None

        tol = self._tolerance(sp)
        value = float(message.value)
        deviation = value - sp
        is_alarm = abs(deviation) > tol

        per_key: dict[str, str] = state.setdefault("status", {})
        prev = per_key.get(message.key, "OK")

        if is_alarm and prev == "OK":
            per_key[message.key] = "ALARM"
            return self._build_alarm(message, value, sp, deviation, tol, "ACTIVE")
        if not is_alarm and prev == "ALARM":
            per_key[message.key] = "OK"
            return self._build_alarm(message, value, sp, deviation, tol, "CLEARED")
        return None

    def _build_alarm(
        self,
        message: Message,
        value: float,
        sp: float,
        deviation: float,
        tolerance: float,
        status: str,
    ) -> Message:
        original_value: dict[str, Any] = {
            "actual": value,
            "setpoint": sp,
            "deviation": round(deviation, 4),
            "tolerance": tolerance,
        }
        if self.tolerance_pct is not None and sp != 0:
            original_value["deviation_pct"] = round(abs(deviation) / abs(sp) * 100.0, 4)

        direction = "" if status == "CLEARED" else ("OVER" if deviation > 0 else "UNDER")

        return Message(
            key=f"{message.key}.alarm",
            timestamp=message.timestamp,
            value={
                "status": status,
                "alarm_type": self.alarm_type_label,
                "direction": direction,
                "original_value": original_value,
            },
            tags={**message.tags},
        )


class BoundsAlarmTransform(StatefulTransform):
    """Alarm on a value leaving ``[min, max]``, with the bounds fed in live.

    Completes the alarm family: :class:`AlarmTransform` compares against
    thresholds fixed in the configuration, :class:`RelativeAlarmTransform`
    against a setpoint, and this one against an interval that an operator can
    move while the pipeline runs.

    The interval is not learned from the data stream: it is the ``bounds``
    parameter, a mapping of setpoint name to value. Declared as a ``ParamRef``
    with ``merge: true`` (see ``config/models.py``), it is rebound by a
    :class:`~cod3s_data.transformations.param_store.ParameterStore` on every
    message the operator publishes — one setpoint per message — and the whole
    interval stays visible and editable in Observatory. ``input_channels``
    therefore carries monitored values only.

    ``bounds_map`` says which key and which side each setpoint name sets, so
    the machine's naming stays out of the mechanism.

    State is per key, and only transitions are emitted (OK → ACTIVE,
    ACTIVE → CLEARED), in the same shape as the rest of the alarm family. A key
    stays silent until both of its bounds are known: an interval that has not
    been announced yet cannot be violated.

    Args:
        broker: Message broker
        input_channels: Channels carrying the monitored values
        output_channel: Channel the alarms are published on
        bounds: Setpoint name → bound value, usually a merging ``ParamRef``
        bounds_map: Setpoint name → ``(monitored key, "min" | "max")``
        alarm_type_label: Value of the ``alarm_type`` field in emitted alarms

    Raises:
        ValueError: If a ``bounds_map`` entry is not a name/side pair, or names
            a side other than ``min`` or ``max``
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        *,
        bounds_map: dict[str, tuple[str, str] | list[str]],
        bounds: dict[str, Any] | None = None,
        alarm_type_label: str = "out_of_bounds",
    ) -> None:
        super().__init__(broker, input_channels, output_channel)
        # YAML gives lists where the API documents pairs; normalise, and reject
        # a malformed entry here rather than silently never alarming on it.
        normalised: dict[str, tuple[str, str]] = {}
        by_key: dict[str, dict[str, str]] = {}
        for name, mapping in bounds_map.items():
            if len(mapping) != 2:
                raise ValueError(
                    f"bounds_map[{name!r}] must be a (key, side) pair, got {mapping!r}"
                )
            key, side = mapping
            if side not in ("min", "max"):
                raise ValueError(f"bounds_map[{name!r}] side must be 'min' or 'max', got {side!r}")
            normalised[name] = (key, side)
            by_key.setdefault(key, {})[side] = name
        self.bounds_map = normalised
        # Reverse view, built once: monitored key -> {"min": name, "max": name}.
        self._sides_by_key = by_key
        # Rebound wholesale by the ParameterStore, under the transform's lock.
        self.bounds = dict(bounds or {})
        self.alarm_type_label = alarm_type_label

    def _interval(self, key: str) -> tuple[float, float] | None:
        """The ``[min, max]`` currently announced for ``key``, if it is complete."""
        sides = self._sides_by_key.get(key)
        if sides is None or "min" not in sides or "max" not in sides:
            return None
        try:
            low = float(self.bounds[sides["min"]])
            high = float(self.bounds[sides["max"]])
        except (KeyError, ValueError, TypeError):
            return None
        return low, high

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Check a monitored value against the interval currently announced.

        Args:
            message: A numeric measurement whose key names the quantity
            state: Per-transform state holding the alarm status of each key

        Returns:
            An alarm message on an OK -> ACTIVE or ACTIVE -> CLEARED
            transition, and None otherwise — including while a key's interval
            is still unknown.
        """
        if not isinstance(message.value, int | float):
            return None
        interval = self._interval(message.key)
        if interval is None:
            return None  # interval not announced yet for this key

        status: dict[str, str] = state.setdefault("status", {})
        value = float(message.value)
        low, high = interval
        is_alarm = value < low or value > high
        previous = status.get(message.key, "OK")

        if is_alarm and previous == "OK":
            status[message.key] = "ALARM"
            return self._build(message, value, low, high, "ACTIVE")
        if not is_alarm and previous == "ALARM":
            status[message.key] = "OK"
            return self._build(message, value, low, high, "CLEARED")
        return None

    def _build(
        self, message: Message, value: float, low: float, high: float, status: str
    ) -> Message:
        direction = "" if status == "CLEARED" else ("OVER" if value > high else "UNDER")
        return Message(
            key=f"{message.key}.alarm",
            timestamp=message.timestamp,
            value={
                "status": status,
                "alarm_type": self.alarm_type_label,
                "direction": direction,
                "original_value": {"actual": value, "min": low, "max": high},
            },
            tags={**message.tags},
        )


def _slug(text: str) -> str:
    """``"Over Extrusion"`` -> ``"over_extrusion"``: a measurement-safe name."""
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_") or "unknown"


def _dotted_get(value: Any, path: str) -> Any:
    """Read ``a.b.c`` from nested dicts; None when any step is missing."""
    node = value
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class RateAlarmTransform(StatefulTransform):
    """Alarm on an event *rate*, per kind of event, transitions only.

    The other alarms of the family watch a value. This one watches a stream of
    punctual events and raises when they come too fast: at least ``min_count``
    events within a sliding window of ``window_s`` seconds. It is what turns a
    burst of detections — a quality-control camera flagging the same defect
    dozens of times a second — into **one** alarm episode, instead of one alarm
    per detection.

    Events are grouped by *kind*, read from the message value at ``key_field``
    (a dotted path such as ``original_value.error_type``). Each kind has its own
    state, its own threshold, and its own measurement:
    ``<input key>.<kind slug>.alarm`` — so a dashboard that lists alarms by
    measurement shows one row per kind, like one row per sensor. ``min_count``
    is either one threshold for every kind, or a mapping of kind to threshold,
    in which case kinds absent from the mapping are not monitored at all.

    Clearing needs a clock. The rest of the family clears when a *value* comes
    back within limits; here it is the rate *falling* below the threshold that
    clears the alarm, and a falling rate is made of events that do not arrive.
    A ticker therefore runs every ``tick_s``, re-evaluates each window, and
    clears an alarm once the rate has stayed below ``min_count`` for ``hold_s``
    seconds. The hold starts when the rate drops, **not** at the last event: a
    trickle of events below the threshold does not keep an alarm alive — for a
    chronic, diffuse kind of event that distinction is the difference between
    an alarm active 8 % of the time and one active 27 % of the time. The window
    and the hold are measured on the wall clock, as the sliding-window
    transforms do; the CLEARED message itself is stamped ``hold_s`` after the
    last event that kept the rate above threshold, so both transitions of an
    episode live on the event clock.

    Payloads carry the family's common fields — ``status``, ``alarm_type``,
    ``direction`` (always ``OVER``: a rate can only be exceeded), and
    ``original_value.actual`` / ``setpoint`` / ``deviation`` as the count in
    the window against ``min_count``, so the generic transitions table reads
    them as it reads any other alarm. On top of that, ACTIVE carries the
    ``rate`` and a snapshot of the first event of the episode (``first_event``:
    where it started, for a positioned event), and CLEARED carries the episode's
    ``events`` total, ``peak_count`` and ``duration_s``.
    """

    def __init__(
        self,
        broker: Broker,
        input_channels: str | list[str],
        output_channel: str,
        *,
        min_count: int | dict[str, int],
        key_field: str | None = None,
        window_s: float = 1.0,
        hold_s: float = 5.0,
        tick_s: float = 0.5,
        alarm_key_prefix: str | None = None,
        alarm_type_label: str = "event_rate",
    ) -> None:
        if window_s <= 0 or hold_s < 0 or tick_s <= 0:
            raise ValueError("RateAlarmTransform requires window_s > 0, hold_s >= 0, tick_s > 0")
        if isinstance(min_count, dict):
            if not min_count or any(int(v) < 1 for v in min_count.values()):
                raise ValueError("RateAlarmTransform: every min_count must be >= 1")
        elif int(min_count) < 1:
            raise ValueError("RateAlarmTransform: min_count must be >= 1")
        super().__init__(broker, input_channels, output_channel)
        self.key_field = key_field
        self.window_s = float(window_s)
        self.hold_s = float(hold_s)
        self.tick_s = float(tick_s)
        self.alarm_key_prefix = alarm_key_prefix
        self.alarm_type_label = alarm_type_label
        self._min_count: int | dict[str, int] = (
            {str(k).casefold(): int(v) for k, v in min_count.items()}
            if isinstance(min_count, dict)
            else int(min_count)
        )
        self._ticker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Subscribe, then start the ticker that clears expired alarms."""
        await super().start()
        self._ticker = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        """Stop the ticker before unsubscribing; no CLEARED is emitted on stop."""
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
            self._ticker = None
        await super().stop()

    def _threshold(self, kind: str) -> int | None:
        if isinstance(self._min_count, dict):
            return self._min_count.get(kind.casefold())
        return self._min_count

    def _kind_of(self, message: Message) -> str | None:
        if self.key_field is None:
            return message.key
        kind = _dotted_get(message.value, self.key_field)
        return None if kind is None else str(kind)

    def _alarm_key(self, message: Message, kind: str) -> str:
        prefix = self.alarm_key_prefix or message.key.removesuffix(".alarm")
        return f"{prefix}.{_slug(kind)}.alarm"

    async def transform_with_state(
        self, message: Message, state: dict[str, Any]
    ) -> Message | list[Message] | None:
        """Count the event in its kind's window; raise on the crossing only.

        Args:
            message: One event. Ignored when its kind cannot be read, or has
                no threshold.
            state: Per-transform state, one entry per kind.

        Returns:
            An ACTIVE alarm the first time the kind's window reaches its
            threshold, None otherwise. Clearing is the ticker's job.
        """
        kind = self._kind_of(message)
        if kind is None:
            return None
        threshold = self._threshold(kind)
        if threshold is None:
            return None

        now = time.monotonic()
        kinds: dict[str, dict[str, Any]] = state.setdefault("kinds", {})
        entry = kinds.setdefault(
            kind, {"events": deque(), "status": "OK", "episode": None, "key": None, "tags": {}}
        )
        window: deque[tuple[float, Message]] = entry["events"]
        window.append((now, message))
        self._prune(window, now)
        count = len(window)
        entry["key"] = self._alarm_key(message, kind)
        entry["tags"] = dict(message.tags)
        if count >= threshold:
            # The rate is above threshold *now*: the hold, if any, restarts here.
            entry["above_mono"] = now
            entry["above_ts"] = message.timestamp

        if entry["status"] == "ALARM":
            episode = entry["episode"]
            episode["events"] += 1
            episode["peak"] = max(episode["peak"], count)
            return None
        if count < threshold:
            return None

        first = window[0][1]
        entry["status"] = "ALARM"
        entry["episode"] = {"events": count, "peak": count, "started": first.timestamp}
        return Message(
            key=entry["key"],
            timestamp=message.timestamp,
            value={
                "status": "ACTIVE",
                "alarm_type": self.alarm_type_label,
                "direction": "OVER",
                "original_value": {
                    "kind": kind,
                    "actual": count,
                    "setpoint": threshold,
                    "deviation": count - threshold,
                    "window_s": self.window_s,
                    "rate": round(count / self.window_s, 4),
                    "first_event": _scalar_fields(first.value),
                },
            },
            tags={**message.tags},
        )

    async def _tick_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.tick_s)
            async with self._lock:
                cleared = self._clear_expired(time.monotonic())
            for alarm in cleared:
                await self.broker.publish(self.output_channel, alarm)

    def _prune(self, window: deque[tuple[float, Message]], now: float) -> None:
        while window and now - window[0][0] > self.window_s:
            window.popleft()

    def _clear_expired(self, now: float) -> list[Message]:
        """CLEARED for every kind whose rate has been below threshold for the hold.

        The windows are re-evaluated here as well as on arrival: with no event
        coming in, only the ticker can notice that a window has emptied.
        """
        out: list[Message] = []
        for kind, entry in self.state.get("kinds", {}).items():
            if entry["status"] != "ALARM":
                continue
            self._prune(entry["events"], now)
            if len(entry["events"]) >= (self._threshold(kind) or 1):
                entry["above_mono"] = now
                continue
            if now - entry["above_mono"] < self.hold_s:
                continue
            episode = entry["episode"]
            cleared_at = entry["above_ts"] + timedelta(seconds=self.hold_s)
            duration = (cleared_at - episode["started"]).total_seconds()
            entry["status"] = "OK"
            entry["episode"] = None
            entry["events"].clear()
            out.append(
                Message(
                    key=entry["key"],
                    timestamp=cleared_at,
                    value={
                        "status": "CLEARED",
                        "alarm_type": self.alarm_type_label,
                        "direction": "",
                        "original_value": {
                            "kind": kind,
                            "actual": 0,
                            "setpoint": self._threshold(kind),
                            "deviation": -(self._threshold(kind) or 0),
                            "window_s": self.window_s,
                            "hold_s": self.hold_s,
                            "events": episode["events"],
                            "peak_count": episode["peak"],
                            "duration_s": round(duration, 3),
                        },
                    },
                    tags=dict(entry["tags"]),
                )
            )
        return out


def _scalar_fields(value: Any) -> dict[str, Any]:
    """The scalar leaves of an event value, one level of ``original_value`` deep.

    Enough to say *where* a positioned event happened (``tool_X``…) without
    dragging nested structures into the alarm.
    """
    if not isinstance(value, dict):
        return {"value": value} if isinstance(value, int | float | str | bool) else {}
    inner = value.get("original_value")
    source: dict[str, Any] = inner if isinstance(inner, dict) else value
    return {k: v for k, v in source.items() if isinstance(v, int | float | str | bool)}


class AlarmGateTransform(Transformation):
    """Keep only the alarms that are ACTIVE, and label them by name.

    Placed after the alarm transforms, it turns their output into something a
    log or a notifier can consume directly: CLEARED messages are dropped, the
    alarm's name (its key without the trailing ``.alarm``) and type move into
    tags, and the value is reduced to the reading that triggered it.
    """

    async def transform(self, message: Message) -> Message | None:
        """Forward an ACTIVE alarm with name and type as tags; drop anything else."""
        if not isinstance(message.value, dict):
            return None
        if message.value.get("status") != "ACTIVE":
            return None
        return Message(
            key=message.key,
            timestamp=message.timestamp,
            value={"value": message.value.get("original_value")},
            tags={
                **message.tags,
                "alarm_name": message.key.removesuffix(".alarm"),
                "alarm_type": str(message.value.get("alarm_type", "")),
            },
        )
