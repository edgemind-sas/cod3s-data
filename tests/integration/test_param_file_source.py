"""Integration tests for ParamFileSource."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.sources.param_file import ParamFileSource


@pytest.mark.integration
class TestParamFileSource:
    async def test_flatten_yaml_publishes_per_path(self, tmp_path: Path):
        params_file = tmp_path / "job.yaml"
        params_file.write_text(
            "alarm:\n  extruder:\n    setpoint: 215\n    tolerance: 5\n  bed:\n    setpoint: 60\n"
        )

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: dict[str, float] = {}

        async def collect(msg: Message) -> None:
            received[msg.key] = msg.value

        broker.subscribe("params.**", collect)

        source = ParamFileSource(broker, channel="params", file_path=params_file)
        await source.start()
        await asyncio.sleep(0.05)

        assert received == {
            "params.alarm.extruder.setpoint": 215,
            "params.alarm.extruder.tolerance": 5,
            "params.alarm.bed.setpoint": 60,
        }
        await broker.stop()

    async def test_json_file_supported(self, tmp_path: Path):
        params_file = tmp_path / "job.json"
        params_file.write_text(json.dumps({"foo": {"bar": 42}}))

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        received: dict[str, float] = {}

        async def collect(msg: Message) -> None:
            received[msg.key] = msg.value

        broker.subscribe("params.**", collect)

        source = ParamFileSource(broker, channel="params", file_path=params_file)
        await source.start()
        await asyncio.sleep(0.05)

        assert received == {"params.foo.bar": 42}
        await broker.stop()

    async def test_published_values_replay_to_late_subscribers(self, tmp_path: Path):
        """A consumer that subscribes after start() must still see params via history."""
        params_file = tmp_path / "job.yaml"
        params_file.write_text("setpoint: 200\n")

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        source = ParamFileSource(broker, channel="params", file_path=params_file)
        await source.start()
        await asyncio.sleep(0.05)

        # Subscribe AFTER source completed
        history = broker.get_history("params.setpoint", count=1)
        assert len(history) == 1
        assert history[0].value == 200
        await broker.stop()

    async def test_missing_file_raises(self, tmp_path: Path):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        source = ParamFileSource(broker, channel="params", file_path=tmp_path / "missing.yaml")
        with pytest.raises(FileNotFoundError):
            await source.start()
        await broker.stop()
