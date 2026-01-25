"""Built-in transformations for COD3S Data Framework."""

from datetime import datetime, timezone
from typing import Any, Callable

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
        aggregation_fn: Callable[[list[Message]], Any] = lambda msgs: sum(m.value for m in msgs) / len(msgs),
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
            state["window_start"] = datetime.now(timezone.utc)

        result = None

        # Time-based window - check before adding message
        if self.window_type == "time" and self.window_duration and state["window"]:
            elapsed = (datetime.now(timezone.utc) - state["window_start"]).total_seconds()
            if elapsed >= self.window_duration:
                result = self._create_aggregate(state["window"], message.key)
                state["window"] = []
                state["window_start"] = datetime.now(timezone.utc)

        # Add message to window
        state["window"].append(message)

        # Count-based window - check after adding
        if self.window_type == "count" and self.window_size:
            if len(state["window"]) >= self.window_size:
                result = self._create_aggregate(state["window"], message.key)
                state["window"] = []
                state["window_start"] = datetime.now(timezone.utc)

        return result

    def _create_aggregate(self, messages: list[Message], key: str) -> Message:
        """Create aggregated message."""
        aggregated_value = self.aggregation_fn(messages)
        return Message(
            key=f"{key}_agg",
            timestamp=datetime.now(timezone.utc),
            value=aggregated_value,
            tags={},
        )
