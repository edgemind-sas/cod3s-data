"""Unit tests for transformations."""

import asyncio
from datetime import UTC, datetime

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.destinations import CollectDestination
from cod3s_data.transformations import (
    AggregateTransform,
    AlarmTransform,
    DeviationFilterTransform,
    FilterTransform,
    MapTransform,
    MedianFilterTransform,
    MovingAverageTransform,
    RelativeAlarmTransform,
    StatefulTransform,
    StatelessTransform,
    ThrottleTransform,
    UnpackTransform,
)


def create_message(key: str = "test", value: float = 42.0) -> Message:
    return Message(key=key, timestamp=datetime.now(UTC), value=value, tags={})


class TestStatelessTransform:
    @pytest.mark.asyncio
    async def test_basic_transform(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = StatelessTransform(
            broker,
            "input.channel",
            "output.channel",
            lambda msg: msg.with_value(msg.value * 2),
        )
        await transform.start()

        await broker.publish("input.channel", create_message(value=10.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].value == 20.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_multiple_outputs(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        def duplicate(msg: Message) -> list[Message]:
            return [msg, msg.with_value(msg.value * 2)]

        transform = StatelessTransform(broker, "input.channel", "output.channel", duplicate)
        await transform.start()

        await broker.publish("input.channel", create_message(value=5.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        assert messages[0].value == 5.0
        assert messages[1].value == 10.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_filter_with_none(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = StatelessTransform(
            broker,
            "input.channel",
            "output.channel",
            lambda msg: msg if msg.value > 10 else None,
        )
        await transform.start()

        await broker.publish("input.channel", create_message(value=5.0))
        await broker.publish("input.channel", create_message(value=15.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].value == 15.0

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestFilterTransform:
    @pytest.mark.asyncio
    async def test_filter_by_value(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = FilterTransform(
            broker, "input.channel", "output.channel", lambda msg: msg.value > 10
        )
        await transform.start()

        await broker.publish("input.channel", create_message(value=5.0))
        await broker.publish("input.channel", create_message(value=15.0))
        await broker.publish("input.channel", create_message(value=20.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        assert all(m.value > 10 for m in messages)

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_filter_by_key(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = FilterTransform(
            broker, "input.channel", "output.channel", lambda msg: msg.key == "temp"
        )
        await transform.start()

        await broker.publish("input.channel", create_message(key="temp", value=1.0))
        await broker.publish("input.channel", create_message(key="pressure", value=2.0))
        await broker.publish("input.channel", create_message(key="temp", value=3.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        assert all(m.key == "temp" for m in messages)

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestMapTransform:
    @pytest.mark.asyncio
    async def test_multiply_values(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = MapTransform(broker, "input.channel", "output.channel", lambda x: x * 2)
        await transform.start()

        await broker.publish("input.channel", create_message(value=5.0))
        await broker.publish("input.channel", create_message(value=10.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        assert messages[0].value == 10.0
        assert messages[1].value == 20.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_convert_values(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = MapTransform(broker, "input.channel", "output.channel", lambda x: f"value_{x}")
        await transform.start()

        await broker.publish("input.channel", create_message(value=42))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].value == "value_42"

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestAggregateTransform:
    @pytest.mark.asyncio
    async def test_count_window(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = AggregateTransform(
            broker,
            "input.channel",
            "output.channel",
            window_type="count",
            window_size=3,
            aggregation_fn=lambda msgs: sum(m.value for m in msgs),
        )
        await transform.start()

        for i in range(7):
            await broker.publish("input.channel", create_message(value=float(i)))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2  # 2 complete windows (3 messages each)
        assert messages[0].value == 0 + 1 + 2  # First window
        assert messages[1].value == 3 + 4 + 5  # Second window

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_time_window(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = AggregateTransform(
            broker,
            "input.channel",
            "output.channel",
            window_type="time",
            window_duration=0.15,
            aggregation_fn=lambda msgs: len(msgs),
        )
        await transform.start()

        # First window
        await broker.publish("input.channel", create_message(value=1.0))
        await broker.publish("input.channel", create_message(value=2.0))
        await asyncio.sleep(0.2)  # Exceed window duration

        # Trigger window emission with new message
        await broker.publish("input.channel", create_message(value=3.0))
        await asyncio.sleep(0.2)

        # Trigger second window emission
        await broker.publish("input.channel", create_message(value=4.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2  # 2 time windows
        assert messages[0].value == 2  # First window: 2 messages
        assert messages[1].value == 1  # Second window: 1 message (msg 3)

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_average_aggregation(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = AggregateTransform(
            broker,
            "input.channel",
            "output.channel",
            window_type="count",
            window_size=2,
            aggregation_fn=lambda msgs: sum(m.value for m in msgs) / len(msgs),
        )
        await transform.start()

        await broker.publish("input.channel", create_message(value=10.0))
        await broker.publish("input.channel", create_message(value=20.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].value == 15.0  # Average of 10 and 20

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestStatefulTransform:
    @pytest.mark.asyncio
    async def test_custom_stateful_transform(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        class CounterTransform(StatefulTransform):
            async def transform_with_state(self, message, state):
                if "count" not in state:
                    state["count"] = 0
                state["count"] += 1
                if state["count"] % 2 == 0:
                    return message.with_value(state["count"])
                return None

        transform = CounterTransform(broker, "input.channel", "output.channel")
        await transform.start()

        for i in range(5):
            await broker.publish("input.channel", create_message(value=float(i)))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2  # Only messages at count 2 and 4
        assert messages[0].value == 2
        assert messages[1].value == 4

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestAlarmTransform:
    @pytest.mark.asyncio
    async def test_alarm_max_exceeded(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(broker, "input.channel", "alarms.channel", max_value=100.0)
        await transform.start()

        await broker.publish("input.channel", create_message(key="temp", value=105.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].key == "temp.alarm"
        assert messages[0].value["original_value"] == 105.0
        assert messages[0].value["alarm_type"] == "max"
        assert messages[0].value["threshold"] == 100.0
        assert messages[0].value["status"] == "ACTIVE"

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_alarm_min_exceeded(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(broker, "input.channel", "alarms.channel", min_value=10.0)
        await transform.start()

        await broker.publish("input.channel", create_message(key="temp", value=5.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].value["alarm_type"] == "min"
        assert messages[0].value["threshold"] == 10.0
        assert messages[0].value["status"] == "ACTIVE"

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_alarm_cleared(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(broker, "input.channel", "alarms.channel", max_value=100.0)
        await transform.start()

        # Trigger alarm
        await broker.publish("input.channel", create_message(key="temp", value=105.0))
        await asyncio.sleep(0.1)
        # Return to normal
        await broker.publish("input.channel", create_message(key="temp", value=80.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        assert messages[0].value["status"] == "ACTIVE"
        assert messages[1].value["status"] == "CLEARED"
        assert messages[1].value["alarm_type"] == "max"
        assert messages[1].value["threshold"] == 100.0
        assert messages[1].value["original_value"] == 80.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_no_message_when_normal(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(
            broker, "input.channel", "alarms.channel", min_value=0.0, max_value=100.0
        )
        await transform.start()

        await broker.publish("input.channel", create_message(value=50.0))
        await broker.publish("input.channel", create_message(value=75.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_no_message_when_still_in_alarm(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(broker, "input.channel", "alarms.channel", max_value=100.0)
        await transform.start()

        await broker.publish("input.channel", create_message(value=105.0))
        await broker.publish("input.channel", create_message(value=110.0))
        await broker.publish("input.channel", create_message(value=120.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1  # Only the first ACTIVE, no repeats

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_min_and_max(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(
            broker, "input.channel", "alarms.channel", min_value=10.0, max_value=90.0
        )
        await transform.start()

        # Max alarm
        await broker.publish("input.channel", create_message(value=95.0))
        await asyncio.sleep(0.1)
        # Clear
        await broker.publish("input.channel", create_message(value=50.0))
        await asyncio.sleep(0.1)
        # Min alarm
        await broker.publish("input.channel", create_message(value=5.0))
        await asyncio.sleep(0.1)
        # Clear
        await broker.publish("input.channel", create_message(value=50.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 4
        assert messages[0].value["alarm_type"] == "max"
        assert messages[0].value["status"] == "ACTIVE"
        assert messages[1].value["status"] == "CLEARED"
        assert messages[2].value["alarm_type"] == "min"
        assert messages[2].value["status"] == "ACTIVE"
        assert messages[3].value["status"] == "CLEARED"

        await transform.stop()
        await dest.stop()
        await broker.stop()

    def test_requires_at_least_one_threshold(self):
        broker = InMemoryBroker(enable_metrics=False)
        with pytest.raises(ValueError, match="at least one"):
            AlarmTransform(broker, "input.channel", "alarms.channel")

    @pytest.mark.asyncio
    async def test_non_numeric_value_ignored(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "alarms.channel")
        await dest.start()

        transform = AlarmTransform(broker, "input.channel", "alarms.channel", max_value=100.0)
        await transform.start()

        await broker.publish(
            "input.channel",
            Message(
                key="test",
                timestamp=datetime.now(UTC),
                value="not a number",
                tags={},
            ),
        )
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 0

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestThrottleTransform:
    @pytest.mark.asyncio
    async def test_first_message_passes(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = ThrottleTransform(broker, "input.channel", "output.channel", interval=1.0)
        await transform.start()

        await broker.publish("input.channel", create_message(value=1.0))
        await asyncio.sleep(0.05)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].value == 1.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_suppresses_within_interval(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = ThrottleTransform(broker, "input.channel", "output.channel", interval=1.0)
        await transform.start()

        for i in range(5):
            await broker.publish("input.channel", create_message(value=float(i)))
        await asyncio.sleep(0.05)

        messages = dest.get_all()
        assert len(messages) == 1  # Only first passes

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_passes_after_interval(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = ThrottleTransform(broker, "input.channel", "output.channel", interval=0.15)
        await transform.start()

        await broker.publish("input.channel", create_message(value=1.0))
        await asyncio.sleep(0.2)  # Wait for interval to elapse
        await broker.publish("input.channel", create_message(value=2.0))
        await asyncio.sleep(0.05)

        messages = dest.get_all()
        assert len(messages) == 2
        assert messages[0].value == 1.0
        assert messages[1].value == 2.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_per_key_throttles_each_key_independently(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = ThrottleTransform(
            broker, "input.channel", "output.channel", interval=1.0, per_key=True
        )
        await transform.start()

        # Burst: 3 messages of "a" then 3 of "b" within the throttle interval.
        # Per-key throttling should let the first of each key through.
        for _ in range(3):
            await broker.publish("input.channel", create_message(key="a", value=1.0))
        for _ in range(3):
            await broker.publish("input.channel", create_message(key="b", value=2.0))
        await asyncio.sleep(0.05)

        messages = dest.get_all()
        keys = [m.key for m in messages]
        assert sorted(keys) == ["a", "b"]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_per_key_allows_second_emit_after_interval(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = ThrottleTransform(
            broker, "input.channel", "output.channel", interval=0.15, per_key=True
        )
        await transform.start()

        await broker.publish("input.channel", create_message(key="a", value=1.0))
        await broker.publish("input.channel", create_message(key="b", value=2.0))
        await asyncio.sleep(0.2)
        await broker.publish("input.channel", create_message(key="a", value=3.0))
        await broker.publish("input.channel", create_message(key="b", value=4.0))
        await asyncio.sleep(0.05)

        messages = dest.get_all()
        assert len(messages) == 4

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestUnpackTransform:
    @pytest.mark.asyncio
    async def test_unpack_dict_value(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel.**")
        await dest.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        await broker.publish(
            "input.channel",
            Message(
                key="sensor",
                timestamp=datetime.now(UTC),
                value={"a": 1, "b": 2},
                tags={},
            ),
        )
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        result = {m.key: m.value for m in messages}
        assert result == {"a": 1, "b": 2}

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_unpack_preserves_timestamp_and_tags(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel.**")
        await dest.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        ts = datetime.now(UTC)
        tags = {"loc": "A", "unit": "celsius"}
        await broker.publish(
            "input.channel",
            Message(
                key="sensor",
                timestamp=ts,
                value={"temperature": 25.5, "pressure": 1013},
                tags=tags,
            ),
        )
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        for msg in messages:
            assert msg.timestamp == ts
            assert msg.tags == {"loc": "A", "unit": "celsius"}

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_unpack_non_dict_passthrough(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        await broker.publish("input.channel", create_message(key="sensor", value=42))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].key == "sensor"
        assert messages[0].value == 42

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_unpack_empty_dict(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel.**")
        await dest.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        await broker.publish(
            "input.channel",
            Message(
                key="sensor",
                timestamp=datetime.now(UTC),
                value={},
                tags={},
            ),
        )
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_unpack_single_entry(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel.**")
        await dest.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        await broker.publish(
            "input.channel",
            Message(
                key="sensor",
                timestamp=datetime.now(UTC),
                value={"x": 1},
                tags={},
            ),
        )
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].key == "x"
        assert messages[0].value == 1

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_unpack_per_key_channels(self):
        """Each dict key is published on its own sub-channel."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest_a = CollectDestination(broker, "output.channel.a")
        dest_b = CollectDestination(broker, "output.channel.b")
        await dest_a.start()
        await dest_b.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        await broker.publish(
            "input.channel",
            Message(
                key="sensor",
                timestamp=datetime.now(UTC),
                value={"a": 1, "b": 2},
                tags={},
            ),
        )
        await asyncio.sleep(0.1)

        msgs_a = dest_a.get_all()
        msgs_b = dest_b.get_all()
        assert len(msgs_a) == 1
        assert msgs_a[0].key == "a"
        assert msgs_a[0].value == 1
        assert len(msgs_b) == 1
        assert msgs_b[0].key == "b"
        assert msgs_b[0].value == 2

        await transform.stop()
        await dest_a.stop()
        await dest_b.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_unpack_channel_name_with_key(self):
        """Verify the exact channel name: {output_channel}.{key}."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel.temperature_top")
        await dest.start()

        transform = UnpackTransform(broker, "input.channel", "output.channel")
        await transform.start()

        await broker.publish(
            "input.channel",
            Message(
                key="sensor",
                timestamp=datetime.now(UTC),
                value={"temperature_top": 25.5},
                tags={},
            ),
        )
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 1
        assert messages[0].key == "temperature_top"
        assert messages[0].value == 25.5

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestTransformationChaining:
    @pytest.mark.asyncio
    async def test_filter_then_map(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "final.channel")
        await dest.start()

        filter_transform = FilterTransform(
            broker, "input.channel", "filtered.channel", lambda msg: msg.value > 5
        )
        await filter_transform.start()

        map_transform = MapTransform(broker, "filtered.channel", "final.channel", lambda x: x * 2)
        await map_transform.start()

        for i in range(10):
            await broker.publish("input.channel", create_message(value=float(i)))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 4  # Values 6, 7, 8, 9 pass filter
        assert [m.value for m in messages] == [12.0, 14.0, 16.0, 18.0]

        await map_transform.stop()
        await filter_transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_multiple_inputs(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dest = CollectDestination(broker, "output.channel")
        await dest.start()

        transform = MapTransform(
            broker, ["input1.channel", "input2.channel"], "output.channel", lambda x: x * 2
        )
        await transform.start()

        await broker.publish("input1.channel", create_message(value=5.0))
        await broker.publish("input2.channel", create_message(value=10.0))
        await asyncio.sleep(0.1)

        messages = dest.get_all()
        assert len(messages) == 2
        assert sorted([m.value for m in messages]) == [10.0, 20.0]

        await transform.stop()
        await dest.stop()
        await broker.stop()


def _make_message(key: str, value: float, ts: datetime | None = None) -> Message:
    return Message(key=key, timestamp=ts or datetime.now(UTC), value=value, tags={})


class TestMovingAverageTransform:
    @pytest.mark.asyncio
    async def test_count_window_mean(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = MovingAverageTransform(
            broker, "in", "out", window_type="count", window_size=3
        )
        await transform.start()

        for v in [10.0, 20.0, 30.0, 40.0]:
            await broker.publish("in", _make_message("temp", v))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        # First message has 1 sample (avg=10), then 2 (15), then 3 (20), then sliding 3 (30)
        assert [m.value for m in msgs] == [10.0, 15.0, 20.0, 30.0]
        # Key preserved
        assert all(m.key == "temp" for m in msgs)

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_min_samples_skips_initial(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = MovingAverageTransform(
            broker, "in", "out", window_type="count", window_size=5, min_samples=3
        )
        await transform.start()

        for v in [1.0, 2.0, 3.0, 4.0]:
            await broker.publish("in", _make_message("k", v))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        # First two messages skipped (not enough samples), then mean of 3 then 4
        assert [m.value for m in msgs] == [2.0, 2.5]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_per_key_isolation(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = MovingAverageTransform(
            broker, "in", "out", window_type="count", window_size=2
        )
        await transform.start()

        await broker.publish("in", _make_message("a", 100.0))
        await broker.publish("in", _make_message("b", 1.0))
        await broker.publish("in", _make_message("a", 200.0))
        await broker.publish("in", _make_message("b", 3.0))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert msgs[0].key == "a" and msgs[0].value == 100.0
        assert msgs[1].key == "b" and msgs[1].value == 1.0
        assert msgs[2].key == "a" and msgs[2].value == 150.0
        assert msgs[3].key == "b" and msgs[3].value == 2.0

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_time_window(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = MovingAverageTransform(
            broker, "in", "out", window_type="time", window_duration=1.0
        )
        await transform.start()

        base = datetime.now(UTC)
        # Three messages at t=0, t=0.5s, t=2.0s — last one drops the first two
        from datetime import timedelta

        await broker.publish("in", _make_message("k", 10.0, base))
        await broker.publish("in", _make_message("k", 20.0, base + timedelta(milliseconds=500)))
        await broker.publish("in", _make_message("k", 100.0, base + timedelta(seconds=2)))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert msgs[0].value == 10.0  # only itself in window
        assert msgs[1].value == 15.0  # mean of 10,20
        assert msgs[2].value == 100.0  # window expired, only newest

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_non_numeric_skipped(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = MovingAverageTransform(
            broker, "in", "out", window_type="count", window_size=3
        )
        await transform.start()

        await broker.publish(
            "in", Message(key="k", timestamp=datetime.now(UTC), value="bad", tags={})
        )
        await asyncio.sleep(0.1)

        assert dest.get_all() == []

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_key_suffix_publishes_per_key_subchannel(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        # Subscribe with a wildcard on per-key sub-channels
        wildcard_dest = CollectDestination(broker, "out.*")
        await wildcard_dest.start()

        transform = MovingAverageTransform(
            broker,
            "in",
            "out",
            window_type="count",
            window_size=2,
            key_suffix="_smoothed",
        )
        await transform.start()

        await broker.publish("in", _make_message("temp_top", 100.0))
        await broker.publish("in", _make_message("temp_top", 200.0))
        await asyncio.sleep(0.1)

        msgs = wildcard_dest.get_all()
        # First message: 1 sample (avg=100), second: 2 samples (avg=150)
        assert [m.value for m in msgs] == [100.0, 150.0]
        assert all(m.key == "temp_top_smoothed" for m in msgs)

        await transform.stop()
        await wildcard_dest.stop()
        await broker.stop()

    def test_invalid_config(self):
        broker = InMemoryBroker(enable_metrics=False)
        with pytest.raises(ValueError):
            MovingAverageTransform(broker, "in", "out", window_type="bogus")
        with pytest.raises(ValueError):
            MovingAverageTransform(broker, "in", "out", window_type="count")
        with pytest.raises(ValueError):
            MovingAverageTransform(broker, "in", "out", window_type="time")


class TestMedianFilterTransform:
    @pytest.mark.asyncio
    async def test_outlier_robust(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = MedianFilterTransform(
            broker, "in", "out", window_type="count", window_size=5, min_samples=5
        )
        await transform.start()

        # Median is robust to a single 1000.0 spike
        for v in [10.0, 11.0, 1000.0, 12.0, 13.0]:
            await broker.publish("in", _make_message("k", v))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert len(msgs) == 1
        assert msgs[0].value == 12.0  # median of [10,11,1000,12,13]

        await transform.stop()
        await dest.stop()
        await broker.stop()


class TestDeviationFilterTransform:
    @pytest.mark.asyncio
    async def test_reject_pct(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = DeviationFilterTransform(
            broker, "in", "out", setpoint=300.0, tolerance_pct=3.0, mode="reject"
        )
        await transform.start()

        # +3% of 300 = 9 → bounds [291, 309]
        for v in [300.0, 305.0, 320.0, 295.0, 280.0]:
            await broker.publish("in", _make_message("k", v))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert [m.value for m in msgs] == [300.0, 305.0, 295.0]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_clip_abs(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = DeviationFilterTransform(
            broker, "in", "out", setpoint=100.0, tolerance_abs=10.0, mode="clip"
        )
        await transform.start()

        for v in [100.0, 95.0, 150.0, 50.0]:
            await broker.publish("in", _make_message("k", v))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert [m.value for m in msgs] == [100.0, 95.0, 110.0, 90.0]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_per_key_setpoint(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = DeviationFilterTransform(
            broker,
            "in",
            "out",
            setpoint={"a": 100.0, "b": 10.0},
            tolerance_abs=1.0,
            mode="reject",
        )
        await transform.start()

        await broker.publish("in", _make_message("a", 100.5))  # in band
        await broker.publish("in", _make_message("a", 200.0))  # out
        await broker.publish("in", _make_message("b", 9.5))  # in band
        await broker.publish("in", _make_message("b", 50.0))  # out
        await broker.publish("in", _make_message("c", 99.0))  # no setpoint → pass-through
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        keys_values = [(m.key, m.value) for m in msgs]
        assert keys_values == [("a", 100.5), ("b", 9.5), ("c", 99.0)]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    def test_invalid_config(self):
        broker = InMemoryBroker(enable_metrics=False)
        with pytest.raises(ValueError):
            DeviationFilterTransform(broker, "in", "out", setpoint=10.0)
        with pytest.raises(ValueError):
            DeviationFilterTransform(
                broker, "in", "out", setpoint=10.0, tolerance_pct=1.0, tolerance_abs=1.0
            )
        with pytest.raises(ValueError):
            DeviationFilterTransform(
                broker, "in", "out", setpoint=10.0, tolerance_abs=1.0, mode="bogus"
            )


class TestRelativeAlarmTransform:
    @pytest.mark.asyncio
    async def test_transitions_only(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = RelativeAlarmTransform(
            broker, "in", "out", setpoint=300.0, tolerance_abs=10.0
        )
        await transform.start()

        # ok, ok, ALARM (transition emit), ALARM (no emit), ok (transition emit), ok (no emit)
        for v in [300.0, 305.0, 320.0, 325.0, 300.0, 301.0]:
            await broker.publish("in", _make_message("temp", v))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert len(msgs) == 2
        assert msgs[0].key == "temp.alarm"
        assert msgs[0].value["status"] == "ACTIVE"
        assert msgs[0].value["original_value"]["actual"] == 320.0
        assert msgs[0].value["original_value"]["setpoint"] == 300.0
        assert msgs[1].value["status"] == "CLEARED"

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_per_key_state(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = RelativeAlarmTransform(
            broker,
            "in",
            "out",
            setpoint={"top": 300.0, "bottom": 100.0},
            tolerance_abs=5.0,
        )
        await transform.start()

        await broker.publish("in", _make_message("top", 320.0))  # ACTIVE top
        await broker.publish("in", _make_message("bottom", 100.0))  # OK bottom (no emit)
        await broker.publish("in", _make_message("bottom", 120.0))  # ACTIVE bottom
        await broker.publish("in", _make_message("top", 300.0))  # CLEARED top
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        statuses = [(m.key, m.value["status"]) for m in msgs]
        assert statuses == [
            ("top.alarm", "ACTIVE"),
            ("bottom.alarm", "ACTIVE"),
            ("top.alarm", "CLEARED"),
        ]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_tolerance_pct(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = RelativeAlarmTransform(
            broker,
            "in",
            "out",
            setpoint=200.0,
            tolerance_pct=5.0,
            alarm_type_label="speed_dev",
        )
        await transform.start()

        # 5% of 200 = 10 → bounds [190, 210]
        await broker.publish("in", _make_message("speed", 215.0))
        await asyncio.sleep(0.1)

        msgs = dest.get_all()
        assert len(msgs) == 1
        assert msgs[0].value["alarm_type"] == "speed_dev"
        assert "deviation_pct" in msgs[0].value["original_value"]

        await transform.stop()
        await dest.stop()
        await broker.stop()

    @pytest.mark.asyncio
    async def test_no_setpoint_skipped(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = CollectDestination(broker, "out")
        await dest.start()

        transform = RelativeAlarmTransform(
            broker,
            "in",
            "out",
            setpoint={"a": 100.0},
            tolerance_abs=1.0,
        )
        await transform.start()

        await broker.publish("in", _make_message("b", 999.0))  # no setpoint → ignored
        await asyncio.sleep(0.1)

        assert dest.get_all() == []

        await transform.stop()
        await dest.stop()
        await broker.stop()

    def test_invalid_config(self):
        broker = InMemoryBroker(enable_metrics=False)
        with pytest.raises(ValueError):
            RelativeAlarmTransform(broker, "in", "out", setpoint=10.0)
        with pytest.raises(ValueError):
            RelativeAlarmTransform(
                broker, "in", "out", setpoint=10.0, tolerance_pct=1.0, tolerance_abs=1.0
            )
