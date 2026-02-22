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
    FilterTransform,
    MapTransform,
    StatefulTransform,
    StatelessTransform,
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
