"""Integration tests for ParamRef-driven dynamic alarm setpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.config.factory import ComponentFactory
from cod3s_data.config.models import (
    TransformConfig,
)
from cod3s_data.core.message import Message
from cod3s_data.destinations.collect import CollectDestination


def _msg(key, value):
    return Message(key=key, timestamp=datetime.now(UTC), value=value, tags={})


@pytest.mark.integration
class TestDynamicRelativeAlarm:
    async def test_setpoint_change_shifts_alarm(self):
        """A republished setpoint must change which values trigger an alarm."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        factory = ComponentFactory(broker)
        transform_cfg = TransformConfig(
            type="relative_alarm",
            input_channels="sensors.temperature",
            output_channel="alarms.temperature",
            params={
                "setpoint": {"ref": "params.alarm.extruder", "default": 200.0},
                "tolerance_abs": 5.0,
            },
        )
        transform = factory.create_transformation(transform_cfg)
        assert len(transform._param_stores) == 1

        # Collect outgoing alarms
        dest = CollectDestination(broker, "alarms.**")

        await dest.start()
        await transform.start()

        # Within tolerance of default 200 +/- 5 — no alarm
        await broker.publish("sensors.temperature", _msg("extruder", 198.0))
        await asyncio.sleep(0.05)
        assert dest.messages == []

        # Outside tolerance of default — alarm fires
        await broker.publish("sensors.temperature", _msg("extruder", 220.0))
        await dest.wait_for_messages(1, timeout=2.0)
        assert dest.messages[0].value["status"] == "ACTIVE"

        # Republish setpoint to 220 — same physical value (220) should now be in tolerance
        await broker.publish("params.alarm.extruder", _msg("setpoint", 220.0))
        await asyncio.sleep(0.05)
        assert transform.setpoint == 220.0

        # Send the same 220 reading — alarm should clear (transition ALARM -> OK)
        await broker.publish("sensors.temperature", _msg("extruder", 220.0))
        await dest.wait_for_messages(2, timeout=2.0)
        assert dest.messages[1].value["status"] == "CLEARED"

        await transform.stop()
        await dest.stop()
        await broker.stop()

    async def test_history_replay_hydrates_before_data(self):
        """Setpoint published before the transform starts must reach it."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        # Param published BEFORE the alarm transform exists/starts
        await broker.publish("params.alarm.bed", _msg("setpoint", 60.0))

        factory = ComponentFactory(broker)
        transform_cfg = TransformConfig(
            type="relative_alarm",
            input_channels="sensors.temperature",
            output_channel="alarms.temperature",
            params={
                "setpoint": {"ref": "params.alarm.bed", "default": 999.0},
                "tolerance_abs": 1.0,
            },
        )
        transform = factory.create_transformation(transform_cfg)
        await transform.start()

        # The hydrated setpoint should be 60 (from history), not the default 999
        assert transform.setpoint == 60.0

        await transform.stop()
        await broker.stop()

    async def test_static_param_still_works(self):
        """Backward compat: a scalar setpoint must not create a ParameterStore."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        factory = ComponentFactory(broker)
        transform_cfg = TransformConfig(
            type="relative_alarm",
            input_channels="sensors.temperature",
            output_channel="alarms.temperature",
            params={"setpoint": 200.0, "tolerance_abs": 5.0},
        )
        transform = factory.create_transformation(transform_cfg)
        assert transform._param_stores == []
        assert transform.setpoint == 200.0
        await broker.stop()
