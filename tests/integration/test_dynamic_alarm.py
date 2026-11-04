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


def _event(kind):
    return _msg("vision5d_error", {"original_value": {"error_type": kind}})


@pytest.mark.integration
class TestDynamicRateAlarm:
    async def test_per_kind_overrides_from_a_merging_param(self):
        """One value of one kind changes live; everything else keeps its value."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        factory = ComponentFactory(broker)
        transform = factory.create_transformation(
            TransformConfig(
                type="rate_alarm",
                input_channels="events",
                output_channel="alarms.rate",
                params={
                    "key_field": "original_value.error_type",
                    "min_count": {"ref": "params.rate.default", "default": 10},
                    "per_kind": {
                        "ref": "params.rate.per_kind",
                        "merge": True,
                        "default": {
                            "Gap": {"min_count": 3, "window_s": 10.0},
                            "Blob": {"min_count": 2},
                        },
                    },
                    "hold_s": 60.0,
                },
            )
        )
        assert len(transform._param_stores) == 2
        dest = CollectDestination(broker, "alarms.**")
        await dest.start()
        await transform.start()

        # A partial update: only Gap's threshold moves; its window and Blob stay.
        await broker.publish("params.rate.per_kind", _msg("per_kind", {"Gap": {"min_count": 1}}))
        await asyncio.sleep(0.05)
        assert transform.per_kind == {
            "gap": {"min_count": 1, "window_s": 10.0},
            "blob": {"min_count": 2},
        }

        await broker.publish("events", _event("Gap"))
        await dest.wait_for_messages(1, timeout=2.0)
        await broker.publish("events", _event("Blob"))
        await asyncio.sleep(0.05)
        assert [m.key for m in dest.messages] == ["vision5d_error.gap.alarm"]

        # The default reaches kinds without an override, live as well.
        await broker.publish("params.rate.default", _msg("min_count", 1))
        await asyncio.sleep(0.05)
        await broker.publish("events", _event("Scars"))
        await dest.wait_for_messages(2, timeout=2.0)
        assert dest.messages[1].key == "vision5d_error.scars.alarm"

        await transform.stop()
        await dest.stop()
        await broker.stop()
