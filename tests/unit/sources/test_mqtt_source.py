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

from cod3s_data.broker import InMemoryBroker
from cod3s_data.sources import MQTTSource


def _source(**kwargs) -> MQTTSource:
    broker = InMemoryBroker(enable_metrics=False)
    return MQTTSource(broker, "raw.test", **kwargs)


def _payload(data: dict) -> bytes:
    return json.dumps(data).encode()


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
