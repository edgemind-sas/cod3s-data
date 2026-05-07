"""Unit tests for ParameterStore."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from cod3s_data.broker import InMemoryBroker
from cod3s_data.core.message import Message
from cod3s_data.transformations.param_store import ParameterStore


def _msg(value):
    return Message(key="p", timestamp=datetime.now(UTC), value=value, tags={})


class TestParameterStore:
    async def test_default_until_first_message(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(setpoint=None)
        store = ParameterStore(
            broker=broker, owner=owner, param_name="setpoint",
            ref="params.s", default=100.0,
        )
        await store.start()
        # No messages yet — owner should hold the constructor default,
        # which the factory already injected before instantiating the store.
        assert store.current == 100.0
        await store.stop()
        await broker.stop()

    async def test_first_publish_rebinds_owner(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(setpoint=100.0)
        store = ParameterStore(
            broker=broker, owner=owner, param_name="setpoint",
            ref="params.s", default=100.0,
        )
        await store.start()

        await broker.publish("params.s", _msg(215.0))
        await asyncio.sleep(0.05)

        assert owner.setpoint == 215.0
        assert store.current == 215.0
        await store.stop()
        await broker.stop()

    async def test_history_replay_hydrates_at_start(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        # Publish BEFORE the consumer subscribes
        await broker.publish("params.s", _msg(42.0))

        owner = SimpleNamespace(setpoint=0.0)
        store = ParameterStore(
            broker=broker, owner=owner, param_name="setpoint",
            ref="params.s", default=0.0,
        )
        await store.start()

        # History replay should have applied the previously-published value
        assert owner.setpoint == 42.0
        assert store.current == 42.0
        await store.stop()
        await broker.stop()

    async def test_dict_key_extraction(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(setpoint=None)
        store = ParameterStore(
            broker=broker, owner=owner, param_name="setpoint",
            ref="params.bundle", default=None, dict_key="extruder",
        )
        await store.start()

        await broker.publish("params.bundle", _msg({"extruder": 215.0, "bed": 60.0}))
        await asyncio.sleep(0.05)

        assert owner.setpoint == 215.0
        await store.stop()
        await broker.stop()

    async def test_unsubscribe_on_stop(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(setpoint=0)
        store = ParameterStore(
            broker=broker, owner=owner, param_name="setpoint",
            ref="params.s", default=0,
        )
        await store.start()
        await store.stop()

        # After stop, further publishes must NOT change owner
        await broker.publish("params.s", _msg(999))
        await asyncio.sleep(0.05)
        assert owner.setpoint == 0
        await broker.stop()

    async def test_dict_key_missing_is_noop(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(setpoint=10)
        store = ParameterStore(
            broker=broker, owner=owner, param_name="setpoint",
            ref="params.bundle", default=10, dict_key="nope",
        )
        await store.start()

        await broker.publish("params.bundle", _msg({"other": 5}))
        await asyncio.sleep(0.05)
        # Missing key -> no rebind, owner keeps its prior value
        assert owner.setpoint == 10
        await store.stop()
        await broker.stop()
