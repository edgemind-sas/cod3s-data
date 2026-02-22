"""Built-in transformations for COD3S Data Framework."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cod3s_data.broker.base import Broker
from cod3s_data.core.message import Message
from cod3s_data.transformations.base import StatefulTransform, StatelessTransform


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
        aggregation_fn: Callable[[list[Message]], Any] = lambda msgs: sum(m.value for m in msgs) / len(msgs),  # noqa: E501
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
        if self.window_type == "count" and self.window_size:
            if len(state["window"]) >= self.window_size:
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
