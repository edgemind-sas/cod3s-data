"""Tests for Observatory Debug Controller."""

from dataclasses import dataclass
from typing import Any

import pytest

from cod3s_data.observatory.debug import (
    BreakpointEvaluator,
    DebugController,
    DebugGranularity,
    DebugState,
)


@dataclass
class FakeMessage:
    key: str = "temp"
    value: Any = 42.0
    tags: dict[str, str] | None = None


class TestBreakpointEvaluator:
    """Tests for breakpoint evaluation."""

    def test_no_breakpoints(self):
        evaluator = BreakpointEvaluator()
        assert evaluator.has_breakpoints is False
        assert evaluator.evaluate("ch", FakeMessage()) is None

    def test_add_and_list(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "sensor.*", condition=None)
        assert evaluator.has_breakpoints is True
        bps = evaluator.list_all()
        assert len(bps) == 1
        assert bps[0]["id"] == "bp1"

    def test_remove(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "sensor.*")
        evaluator.remove("bp1")
        assert evaluator.has_breakpoints is False

    def test_remove_nonexistent(self):
        evaluator = BreakpointEvaluator()
        with pytest.raises(KeyError):
            evaluator.remove("nope")

    def test_toggle(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*")
        evaluator.toggle("bp1", False)
        assert evaluator.has_breakpoints is False
        evaluator.toggle("bp1", True)
        assert evaluator.has_breakpoints is True

    def test_match_exact_channel(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "sensor.temp")
        assert evaluator.evaluate("sensor.temp", FakeMessage()) is not None
        assert evaluator.evaluate("sensor.humid", FakeMessage()) is None

    def test_match_wildcard(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "sensor.*")
        assert evaluator.evaluate("sensor.temp", FakeMessage()) is not None
        assert evaluator.evaluate("other.temp", FakeMessage()) is None

    def test_match_star_all(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*")
        assert evaluator.evaluate("anything", FakeMessage()) is not None

    def test_match_with_condition(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*", condition="value > 100")
        assert evaluator.evaluate("ch", FakeMessage(value=150)) is not None
        assert evaluator.evaluate("ch", FakeMessage(value=50)) is None

    def test_match_with_component_id(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*", component_id="src-0")
        assert evaluator.evaluate("ch", FakeMessage(), component_id="src-0") is not None
        assert evaluator.evaluate("ch", FakeMessage(), component_id="src-1") is None

    def test_hit_count(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*")
        evaluator.evaluate("ch", FakeMessage())
        evaluator.evaluate("ch", FakeMessage())
        bps = evaluator.list_all()
        assert bps[0]["hit_count"] == 2

    def test_disabled_breakpoint_skipped(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*")
        evaluator.toggle("bp1", False)
        assert evaluator.evaluate("ch", FakeMessage()) is None

    def test_invalid_condition_rejected(self):
        evaluator = BreakpointEvaluator()
        with pytest.raises(ValueError):
            evaluator.add("bp1", "*", condition="import os")

    def test_condition_with_tags(self):
        evaluator = BreakpointEvaluator()
        evaluator.add("bp1", "*", condition="tags.unit == 'celsius'")
        msg_match = FakeMessage(tags={"unit": "celsius"})
        msg_no_match = FakeMessage(tags={"unit": "fahrenheit"})
        assert evaluator.evaluate("ch", msg_match) is not None
        assert evaluator.evaluate("ch", msg_no_match) is None


class TestDebugController:
    """Tests for the debug state machine."""

    def test_inactive_by_default(self):
        ctrl = DebugController(enabled=False)
        assert ctrl.state == DebugState.INACTIVE
        assert ctrl.is_active is False

    def test_active_when_enabled(self):
        ctrl = DebugController(enabled=True)
        assert ctrl.state == DebugState.RUNNING
        assert ctrl.is_active is True

    @pytest.mark.asyncio
    async def test_pause_resume(self):
        ctrl = DebugController(enabled=True)
        await ctrl.pause()
        assert ctrl.state == DebugState.PAUSED
        await ctrl.resume()
        assert ctrl.state == DebugState.RUNNING

    @pytest.mark.asyncio
    async def test_pause_from_inactive(self):
        ctrl = DebugController(enabled=False)
        await ctrl.pause()
        # Should transition through RUNNING to PAUSED
        assert ctrl.state == DebugState.PAUSED

    def test_set_granularity(self):
        ctrl = DebugController(enabled=True)
        ctrl.set_granularity("stage")
        assert ctrl.granularity == DebugGranularity.STAGE

    def test_set_slow_motion(self):
        ctrl = DebugController(enabled=True)
        ctrl.set_slow_motion(True, 1000)
        assert ctrl._slow_motion is True
        assert ctrl._slow_motion_delay_ms == 1000

    def test_slow_motion_clamped(self):
        ctrl = DebugController(enabled=True)
        ctrl.set_slow_motion(True, 10)  # Below minimum
        assert ctrl._slow_motion_delay_ms == 100
        ctrl.set_slow_motion(True, 99999)  # Above maximum
        assert ctrl._slow_motion_delay_ms == 5000

    def test_get_state_dict(self):
        ctrl = DebugController(enabled=True)
        d = ctrl.get_state_dict()
        assert d["state"] == "running"
        assert d["granularity"] == "message"
        assert isinstance(d["breakpoints"], list)
        assert "slow_motion" in d
        assert "step_count" in d

    @pytest.mark.asyncio
    async def test_check_message_breakpoint_hit(self):
        ctrl = DebugController(enabled=True)
        ctrl.breakpoint_evaluator.add("bp1", "*", condition="value > 100")

        msg = FakeMessage(value=150)
        await ctrl.check_message("sensor.temp", msg)
        assert ctrl.state == DebugState.PAUSED

    @pytest.mark.asyncio
    async def test_check_message_breakpoint_miss(self):
        ctrl = DebugController(enabled=True)
        ctrl.breakpoint_evaluator.add("bp1", "*", condition="value > 100")

        msg = FakeMessage(value=50)
        await ctrl.check_message("sensor.temp", msg)
        # Should remain running (no breakpoint hit, no pause)
        assert ctrl.state == DebugState.RUNNING
