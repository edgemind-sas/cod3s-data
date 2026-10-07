"""Unit tests for MQTTDestination.

No broker is started: what matters here is what gets published and where — the
topic resolved from the message, the payload shape, the QoS and retain flags —
plus the failure path, since a destination that swallowed an error would lose
the message instead of dead-lettering it. The real round trip against Mosquitto
lives in ``tests/integration/test_mqtt_integration.py``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("aiomqtt")

from cod3s_data.broker import InMemoryBroker  # noqa: E402
from cod3s_data.core.message import Message  # noqa: E402
from cod3s_data.destinations.mqtt import MQTTDestination  # noqa: E402

TS = datetime(2026, 9, 10, 14, 15, 0, tzinfo=UTC)


def _make_message(
    key: str = "temperature_top",
    value: object = 293.8,
    tags: dict[str, str] | None = None,
) -> Message:
    return Message(key=key, timestamp=TS, value=value, tags=tags or {})


def _make_destination(broker: InMemoryBroker | None = None, **kwargs) -> MQTTDestination:
    return MQTTDestination(
        broker or InMemoryBroker(enable_metrics=False),
        kwargs.pop("channel_pattern", "sensors.**"),
        **kwargs,
    )


def _connected(dest: MQTTDestination) -> AsyncMock:
    """Give the destination a client that is already up."""
    client = MagicMock()
    client.publish = AsyncMock()
    client.__aexit__ = AsyncMock()
    dest._client = client
    return client


class TestConstruction:
    def test_unknown_payload_format_raises(self):
        with pytest.raises(ValueError, match="payload_format must be one of"):
            _make_destination(payload_format="protobuf")

    def test_unknown_topic_field_raises(self):
        with pytest.raises(ValueError, match="unknown field"):
            _make_destination(topic="gemini/{sensor}")

    def test_malformed_topic_raises(self):
        with pytest.raises(ValueError, match="not a valid template"):
            _make_destination(topic="gemini/{key")

    def test_known_topic_fields_are_accepted(self):
        dest = _make_destination(topic="gemini/{channel}/{tags[OF]}/{key}")
        assert dest.topic == "gemini/{channel}/{tags[OF]}/{key}"


class TestTopicResolution:
    def test_literal_topic_is_used_as_is(self):
        dest = _make_destination(topic="gemini/alertes")
        assert dest._topic_for(_make_message()) == "gemini/alertes"

    def test_key_substitution(self):
        dest = _make_destination(topic="gemini/{key}")
        assert dest._topic_for(_make_message(key="pressure")) == "gemini/pressure"

    def test_tag_substitution(self):
        dest = _make_destination(topic="usine/{tags[OF]}/alertes")
        msg = _make_message(tags={"OF": "OF-1234"})
        assert dest._topic_for(msg) == "usine/OF-1234/alertes"

    def test_channel_substitution(self):
        dest = _make_destination(channel_pattern="alerts.**", topic="bridge/{channel}")
        assert dest._topic_for(_make_message()) == "bridge/alerts.**"

    def test_missing_tag_names_itself_and_the_message(self):
        dest = _make_destination(topic="usine/{tags[OF]}/alertes")

        with pytest.raises(KeyError, match="OF"):
            dest._topic_for(_make_message(key="pressure"))


class TestNativePayload:
    def test_dict_value_becomes_fields(self):
        dest = _make_destination()
        payload = json.loads(dest._encode(_make_message(value={"temp": 293.8, "p": 2.0})))

        assert payload == {"ts": TS.timestamp(), "fields": {"temp": 293.8, "p": 2.0}}

    def test_scalar_value_is_wrapped_under_value(self):
        dest = _make_destination()
        payload = json.loads(dest._encode(_make_message(value=293.8)))

        assert payload["fields"] == {"value": 293.8}

    def test_session_tag_is_carried_over(self):
        dest = _make_destination(session_tag="OF", session_field="OF")
        payload = json.loads(dest._encode(_make_message(tags={"OF": "OF-1234"})))

        assert payload["OF"] == "OF-1234"

    def test_session_is_omitted_when_the_tag_is_absent(self):
        dest = _make_destination(session_tag="OF", session_field="OF")
        assert "OF" not in json.loads(dest._encode(_make_message()))

    def test_field_names_are_configurable(self):
        dest = _make_destination(ts_field="time", fields_field="values")
        payload = json.loads(dest._encode(_make_message(value={"t": 1})))

        assert set(payload) == {"time", "values"}

    def test_the_shape_is_what_the_source_reads_back(self):
        """A pipeline publishing `native` must be readable by MQTTSource."""
        from cod3s_data.sources import MQTTSource

        dest = _make_destination(session_tag="OF", session_field="OF")
        encoded = dest._encode(_make_message(value={"temp": 293.8}, tags={"OF": "OF-1234"}))

        source = MQTTSource(
            InMemoryBroker(enable_metrics=False),
            "raw.test",
            session_field="OF",
            session_tag="OF",
            default_key="reading",
        )
        parsed = source._parse(encoded.encode())

        assert parsed is not None
        assert parsed.value == {"temp": 293.8}
        assert parsed.tags["OF"] == "OF-1234"
        assert parsed.timestamp == TS


class TestRawPayload:
    def test_scalar_is_published_bare(self):
        dest = _make_destination(payload_format="raw")
        assert dest._encode(_make_message(value=293.8)) == "293.8"

    def test_string_is_published_as_json_string(self):
        dest = _make_destination(payload_format="raw")
        assert dest._encode(_make_message(value="ACTIVE")) == '"ACTIVE"'

    def test_dict_is_published_without_envelope(self):
        dest = _make_destination(payload_format="raw")
        assert json.loads(dest._encode(_make_message(value={"a": 1}))) == {"a": 1}


class TestPublishing:
    async def test_message_reaches_the_client(self):
        dest = _make_destination(topic="gemini/{key}", qos=1, retain=True)
        client = _connected(dest)

        await dest.write(_make_message(key="pressure", value=2.0))

        client.publish.assert_awaited_once()
        topic, payload = client.publish.await_args.args
        assert topic == "gemini/pressure"
        assert json.loads(payload)["fields"] == {"value": 2.0}
        assert client.publish.await_args.kwargs == {"qos": 1, "retain": True}

    async def test_defaults_are_qos_zero_without_retain(self):
        dest = _make_destination()
        client = _connected(dest)

        await dest.write(_make_message())

        assert client.publish.await_args.kwargs == {"qos": 0, "retain": False}

    async def test_publish_failure_propagates(self):
        dest = _make_destination()
        client = _connected(dest)
        client.publish.side_effect = RuntimeError("broker gone")

        with pytest.raises(RuntimeError, match="broker gone"):
            await dest.write(_make_message())

    async def test_a_failed_publish_drops_the_client(self):
        """The next attempt must reconnect rather than retry on a dead socket."""
        dest = _make_destination()
        client = _connected(dest)
        client.publish.side_effect = RuntimeError("broker gone")

        with pytest.raises(RuntimeError):
            await dest.write(_make_message())

        assert dest._client is None
        client.__aexit__.assert_awaited_once()


class TestLifecycle:
    async def test_close_is_idempotent(self):
        dest = _make_destination()
        client = _connected(dest)

        await dest.close()
        await dest.close()

        assert dest._client is None
        client.__aexit__.assert_awaited_once()

    async def test_close_survives_a_broken_connection(self):
        dest = _make_destination()
        client = _connected(dest)
        client.__aexit__.side_effect = RuntimeError("socket already gone")

        await dest.close()

        assert dest._client is None

    async def test_messages_published_through_the_broker(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dest = _make_destination(broker, channel_pattern="sensors.**", topic="gemini/{key}")
        client = _connected(dest)
        await dest.start()

        await broker.publish("sensors.temp", _make_message(key="temp", value=1.0))
        await asyncio.sleep(0.3)
        await dest.stop()

        client.publish.assert_awaited_once()
        assert client.publish.await_args.args[0] == "gemini/temp"
        await broker.stop()


class TestDeadLetter:
    async def test_an_undeliverable_message_lands_on_the_dlq(self):
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()
        dead: list[Message] = []

        async def collect(msg: Message) -> None:
            dead.append(msg)

        broker.subscribe("rebuts", collect)

        dest = _make_destination(
            broker,
            channel_pattern="sensors.**",
            topic="usine/{tags[OF]}/alertes",
            dlq_channel="rebuts",
            retry_attempts=1,
        )
        _connected(dest)
        await dest.start()

        await broker.publish("sensors.temp", _make_message(key="temp"))
        # The writer loop needs a tick to pick the message up; the retry and the
        # dead-letter publication both happen inside it.
        await asyncio.sleep(0.3)
        await dest.stop()

        assert len(dead) == 1
        assert dead[0].tags["dlq_error_type"] == "KeyError"
        assert "OF" in dead[0].tags["dlq_error"]
        await broker.stop()


class TestImportGuard:
    def test_missing_extra_names_the_component(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "aiomqtt", None)
        with pytest.raises(ImportError, match=r"MQTTDestination.*cod3s-data\[mqtt\]"):
            _make_destination()
