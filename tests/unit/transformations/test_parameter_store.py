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
            broker=broker,
            owner=owner,
            param_name="setpoint",
            ref="params.s",
            default=100.0,
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
            broker=broker,
            owner=owner,
            param_name="setpoint",
            ref="params.s",
            default=100.0,
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
            broker=broker,
            owner=owner,
            param_name="setpoint",
            ref="params.s",
            default=0.0,
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
            broker=broker,
            owner=owner,
            param_name="setpoint",
            ref="params.bundle",
            default=None,
            dict_key="extruder",
        )
        await store.start()

        await broker.publish("params.bundle", _msg({"extruder": 215.0, "bed": 60.0}))
        await asyncio.sleep(0.05)

        assert owner.setpoint == 215.0
        await store.stop()
        await broker.stop()

    async def test_merge_accumulates_partial_updates(self):
        """Each message carries one entry; the others must survive."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(bounds={})
        store = ParameterStore(
            broker=broker,
            owner=owner,
            param_name="bounds",
            ref="params.b",
            default={},
            merge=True,
        )
        await store.start()

        await broker.publish("params.b", _msg({"TopMIN": 295.0}))
        await asyncio.sleep(0.05)
        await broker.publish("params.b", _msg({"TopMAX": 305.0}))
        await asyncio.sleep(0.05)
        await broker.publish("params.b", _msg({"TopMAX": 315.0}))
        await asyncio.sleep(0.05)

        assert owner.bounds == {"TopMIN": 295.0, "TopMAX": 315.0}
        await store.stop()
        await broker.stop()

    async def test_merge_descends_into_nested_mappings(self):
        """A fragment changing one leaf of a nested entry keeps that entry's other leaves."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        default = {"Gap": {"min_count": 130, "window_s": 10.0}, "Blob": {"min_count": 12}}
        owner = SimpleNamespace(per_kind=default)
        store = ParameterStore(
            broker=broker,
            owner=owner,
            param_name="per_kind",
            ref="params.k",
            default=default,
            merge=True,
        )
        await store.start()

        await broker.publish("params.k", _msg({"Gap": {"min_count": 140}}))
        await asyncio.sleep(0.05)
        await broker.publish("params.k", _msg({"Scars": {"min_count": 1}}))
        await asyncio.sleep(0.05)

        assert owner.per_kind == {
            "Gap": {"min_count": 140, "window_s": 10.0},
            "Blob": {"min_count": 12},
            "Scars": {"min_count": 1},
        }
        assert default == {"Gap": {"min_count": 130, "window_s": 10.0}, "Blob": {"min_count": 12}}
        await store.stop()
        await broker.stop()

    async def test_rejected_value_keeps_the_previous_one(self):
        """A value the owner refuses changes nothing, live or replayed from history."""

        class Owner:
            def __init__(self):
                self._limit = 10

            @property
            def limit(self):
                return self._limit

            @limit.setter
            def limit(self, value):
                if value < 0:
                    raise ValueError("limit must be >= 0")
                self._limit = value

        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        await broker.publish("params.l", _msg(-1))

        owner = Owner()
        store = ParameterStore(
            broker=broker, owner=owner, param_name="limit", ref="params.l", default=10
        )
        await store.start()
        assert owner.limit == 10

        await broker.publish("params.l", _msg(-2))
        await asyncio.sleep(0.05)
        assert owner.limit == 10
        assert store.current == 10

        await broker.publish("params.l", _msg(20))
        await asyncio.sleep(0.05)
        assert owner.limit == 20
        await store.stop()
        await broker.stop()

    async def test_merge_replays_whole_history_at_start(self):
        """Hydrating from the last message only would rebuild a single entry."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        await broker.publish("params.b", _msg({"TopMIN": 295.0}))
        await broker.publish("params.b", _msg({"TopMAX": 305.0}))
        await asyncio.sleep(0.05)

        owner = SimpleNamespace(bounds={})
        store = ParameterStore(
            broker=broker,
            owner=owner,
            param_name="bounds",
            ref="params.b",
            default={},
            merge=True,
        )
        await store.start()

        assert owner.bounds == {"TopMIN": 295.0, "TopMAX": 305.0}
        await store.stop()
        await broker.stop()

    async def test_merge_ignores_non_dict_message(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(bounds={"TopMIN": 295.0})
        store = ParameterStore(
            broker=broker,
            owner=owner,
            param_name="bounds",
            ref="params.b",
            default={"TopMIN": 295.0},
            merge=True,
        )
        await store.start()

        await broker.publish("params.b", _msg(42.0))
        await asyncio.sleep(0.05)

        assert owner.bounds == {"TopMIN": 295.0}
        await store.stop()
        await broker.stop()

    async def test_unsubscribe_on_stop(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        owner = SimpleNamespace(setpoint=0)
        store = ParameterStore(
            broker=broker,
            owner=owner,
            param_name="setpoint",
            ref="params.s",
            default=0,
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
            broker=broker,
            owner=owner,
            param_name="setpoint",
            ref="params.bundle",
            default=10,
            dict_key="nope",
        )
        await store.start()

        await broker.publish("params.bundle", _msg({"other": 5}))
        await asyncio.sleep(0.05)
        # Missing key -> no rebind, owner keeps its prior value
        assert owner.setpoint == 10
        await store.stop()
        await broker.stop()
