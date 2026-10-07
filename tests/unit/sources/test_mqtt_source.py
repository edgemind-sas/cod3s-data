"""Unit tests for MQTTSource.

The payload parsing is what this source is for, and it is reachable without a
broker: ``produce()`` only wraps ``_parse`` in a subscription loop. These tests
therefore drive ``_parse`` directly rather than standing up a real MQTT server,
which would move them to ``tests/integration`` and make them skippable — the
parsing rules would then go unchecked on most runs.
"""

import json
from datetime import UTC, datetime

import pytest

aiomqtt = pytest.importorskip("aiomqtt")

from cod3s_data.broker import InMemoryBroker  # noqa: E402
from cod3s_data.sources import MQTTSource  # noqa: E402


def _source(**kwargs) -> MQTTSource:
    broker = InMemoryBroker(enable_metrics=False)
    return MQTTSource(broker, "raw.test", **kwargs)


def _payload(data: dict) -> bytes:
    return json.dumps(data).encode()


async def _no_sleep(_delay, _is_running):
    """Collapse the reconnection wait so the tests stay instant."""
    return


class _FakeConnection:
    """Stands in for MQTTConnection: hands out scripted clients, logs nothing."""

    def __init__(self, episodes, on_connect=None):
        self._episodes = episodes
        self._on_connect = on_connect

    def client(self, **_kwargs):
        if self._on_connect is not None:
            self._on_connect()
        return self._episodes.pop(0)

    def describe(self):
        return {"host": "fake", "port": 1883, "tls": False, "authenticated": False}


class TestSourceFormatValidation:
    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="must be 'native' or 'telegraf'"):
            _source(source_format="parquet")


class TestNativeFormat:
    def test_fields_become_the_value(self):
        source = _source(default_key="reading", default_tags={"source": "egm"})
        msg = source._parse(_payload({"ts": 1700000000.5, "fields": {"temp": 300.0}}))

        assert msg is not None
        assert msg.key == "reading"
        assert msg.value == {"temp": 300.0}
        assert msg.tags == {"source": "egm"}
        assert msg.timestamp == datetime.fromtimestamp(1700000000.5, tz=UTC)

    def test_session_is_tagged_under_the_configured_name(self):
        source = _source(session_field="OF", session_tag="OF")
        msg = source._parse(_payload({"ts": 1.0, "OF": "OF-1234", "fields": {"p": 1}}))

        assert msg is not None
        assert msg.tags["OF"] == "OF-1234"

    def test_session_tag_none_drops_the_session(self):
        source = _source(session_tag=None)
        msg = source._parse(_payload({"ts": 1.0, "session": "s1", "fields": {"p": 1}}))

        assert msg is not None
        assert msg.tags == {}

    def test_missing_timestamp_falls_back_to_now(self):
        before = datetime.now(UTC)
        msg = _source()._parse(_payload({"fields": {"p": 1}}))

        assert msg is not None
        assert msg.timestamp >= before

    def test_unusable_timestamp_falls_back_to_now(self):
        before = datetime.now(UTC)
        msg = _source()._parse(_payload({"ts": "not-a-number", "fields": {"p": 1}}))

        assert msg is not None
        assert msg.timestamp >= before

    def test_missing_fields_gives_an_empty_value(self):
        msg = _source()._parse(_payload({"ts": 1.0}))

        assert msg is not None
        assert msg.value == {}


class TestTelegrafFormat:
    def test_measurement_name_becomes_the_key(self):
        source = _source(source_format="telegraf")
        msg = source._parse(
            _payload({"name": "vision5d", "timestamp": 1700000000, "fields": {"tool_X": 1.0}})
        )

        assert msg is not None
        assert msg.key == "vision5d"
        assert msg.value == {"tool_X": 1.0}

    def test_name_as_key_false_keeps_the_default_key(self):
        source = _source(source_format="telegraf", name_as_key=False, default_key="fixed")
        msg = source._parse(_payload({"name": "vision5d", "timestamp": 1.0, "fields": {}}))

        assert msg is not None
        assert msg.key == "fixed"

    def test_session_is_mined_from_a_tag(self):
        source = _source(source_format="telegraf", session_from_tag="path")
        msg = source._parse(
            _payload(
                {
                    "name": "egm",
                    "timestamp": 1.0,
                    "tags": {"path": "/data/2026-02-26_13-54-30_logEgm.csv"},
                    "fields": {"t": 1.0},
                }
            )
        )

        assert msg is not None
        assert msg.tags["session"] == "2026-02-26_13-54-30"

    def test_tag_without_a_session_leaves_the_tag_unset(self):
        source = _source(source_format="telegraf")
        msg = source._parse(
            _payload({"name": "egm", "timestamp": 1.0, "tags": {"path": "/data/live.csv"}})
        )

        assert msg is not None
        assert "session" not in msg.tags

    def test_custom_session_regex(self):
        source = _source(
            source_format="telegraf",
            session_from_tag="job",
            session_regex=r"job-(\d+)",
        )
        msg = source._parse(
            _payload({"name": "egm", "timestamp": 1.0, "tags": {"job": "run/job-42/x"}})
        )

        assert msg is not None
        assert msg.tags["session"] == "42"


class TestFieldNormalisation:
    def test_strip_suffix_undoes_basicstats_renaming(self):
        source = _source(source_format="telegraf", strip_suffix="_mean")
        msg = source._parse(
            _payload({"name": "egm", "timestamp": 1.0, "fields": {"TemperatureTop_mean": 300.0}})
        )

        assert msg is not None
        assert msg.value == {"TemperatureTop": 300.0}

    def test_field_map_renames_after_stripping(self):
        source = _source(
            source_format="telegraf",
            strip_suffix="_mean",
            field_map={"TemperatureTop": "temperature_top"},
        )
        msg = source._parse(
            _payload({"name": "egm", "timestamp": 1.0, "fields": {"TemperatureTop_mean": 300.0}})
        )

        assert msg is not None
        assert msg.value == {"temperature_top": 300.0}

    def test_field_keep_filters_on_the_mapped_name(self):
        source = _source(
            field_map={"Pression": "pressure"},
            field_keep=["pressure"],
        )
        msg = source._parse(_payload({"ts": 1.0, "fields": {"Pression": 35.0, "Force": 12.0}}))

        assert msg is not None
        assert msg.value == {"pressure": 35.0}

    def test_no_field_keep_keeps_everything(self):
        msg = _source()._parse(_payload({"ts": 1.0, "fields": {"a": 1, "b": 2}}))

        assert msg is not None
        assert msg.value == {"a": 1, "b": 2}


class TestMalformedPayloads:
    def test_invalid_json_is_dropped(self):
        assert _source()._parse(b"{not json") is None

    def test_non_object_payload_is_dropped(self):
        assert _source()._parse(b"[1, 2, 3]") is None


class TestSubscriptionOptions:
    """What reaches the broker when the source connects."""

    def test_a_single_filter_stays_a_string(self):
        assert _source(topic="gemini/egm")._topics == ["gemini/egm"]

    def test_several_filters_are_all_subscribed(self):
        source = _source(topic=["gemini/egm", "gemini/consignes"])
        assert source._topics == ["gemini/egm", "gemini/consignes"]

    def test_connection_settings_reach_the_shared_transport(self):
        source = _source(host="broker", port=8883, username="gemini", tls=True)

        assert source._conn.host == "broker"
        assert source._conn.port == 8883
        assert source._conn.username == "gemini"
        assert source._conn.tls is True


class TestReconnection:
    """A dropped connection must not look like the end of the stream.

    Before this, an ``MqttError`` left ``produce()`` and the framework notified
    ``running → completed``: a broker restart stopped the ingestion while the
    pipeline still reported itself healthy.
    """

    @staticmethod
    def _fake_client(script, on_exhausted=None):
        """Build one scripted client per episode of ``script``.

        An episode either ends on an ``MqttError`` — the source must reconnect —
        or runs out of payloads, which stands for the framework stopping the
        source: ``on_exhausted`` clears its running flag, exactly as ``stop()``
        does, so the loop ends instead of asking for yet another client.
        """

        class FakeMessages:
            def __init__(self, payloads, raise_at_end):
                self._payloads = list(payloads)
                self._raise = raise_at_end

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._payloads:
                    msg = type("M", (), {"payload": self._payloads.pop(0)})()
                    return msg
                if self._raise:
                    raise aiomqtt.MqttError("connection lost")
                if on_exhausted is not None:
                    on_exhausted()
                raise StopAsyncIteration

        class FakeClient:
            def __init__(self, payloads, raise_at_end):
                self.messages = FakeMessages(payloads, raise_at_end)
                self.subscribed: list[tuple[str, int]] = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def subscribe(self, topic, qos=0, **_kwargs):
                self.subscribed.append((topic, qos))

        episodes = [FakeClient(payloads, raise_at_end) for payloads, raise_at_end in script]
        return episodes

    async def test_a_drop_is_followed_by_a_new_subscription(self, monkeypatch):
        source = _source(topic="gemini/egm", qos=1)
        episodes = self._fake_client(
            [
                ([_payload({"ts": 1.0, "fields": {"a": 1}})], True),  # drops
                ([_payload({"ts": 2.0, "fields": {"a": 2}})], False),  # then stopped
            ],
            on_exhausted=lambda: setattr(source, "_running", False),
        )
        monkeypatch.setattr(source, "_conn", _FakeConnection(episodes))
        monkeypatch.setattr("cod3s_data.core.mqtt_client._sleep_while_running", _no_sleep)

        source._running = True
        values = [msg.value async for msg in source.produce()]

        assert values == [{"a": 1}, {"a": 2}]

    async def test_every_filter_is_resubscribed_after_a_drop(self, monkeypatch):
        source = _source(topic=["gemini/egm", "gemini/consignes"], qos=1)
        episodes = self._fake_client(
            [([], True), ([], False)],
            on_exhausted=lambda: setattr(source, "_running", False),
        )
        monkeypatch.setattr(source, "_conn", _FakeConnection(list(episodes)))
        monkeypatch.setattr("cod3s_data.core.mqtt_client._sleep_while_running", _no_sleep)

        source._running = True
        assert [msg async for msg in source.produce()] == []

        for episode in episodes:
            assert episode.subscribed == [("gemini/egm", 1), ("gemini/consignes", 1)]

    async def test_a_stopped_source_does_not_reconnect(self, monkeypatch):
        source = _source()
        episodes = self._fake_client([([], True)])
        conn = _FakeConnection(episodes, on_connect=lambda: setattr(source, "_running", False))
        monkeypatch.setattr(source, "_conn", conn)

        source._running = True
        assert [msg async for msg in source.produce()] == []
        assert episodes == []  # no second attempt
