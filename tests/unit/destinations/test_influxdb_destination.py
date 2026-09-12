"""Unit tests for InfluxDBDestination (mocked — no real InfluxDB needed)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

influxdb_client = pytest.importorskip("influxdb_client")


from cod3s_data.broker import InMemoryBroker  # noqa: E402
from cod3s_data.core.message import Message  # noqa: E402
from cod3s_data.destinations.influxdb import InfluxDBDestination  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    key: str = "temperature",
    value: object = 42.5,
    tags: dict[str, str] | None = None,
    ts: datetime | None = None,
) -> Message:
    return Message(
        key=key,
        timestamp=ts or datetime.now(UTC),
        value=value,
        tags=tags or {},
    )


def _make_destination(
    broker: InMemoryBroker | None = None,
    **kwargs: object,
) -> InfluxDBDestination:
    """Create an InfluxDBDestination with sensible defaults for tests."""
    if broker is None:
        broker = InMemoryBroker(enable_metrics=False)
    defaults: dict[str, object] = {
        "url": "http://localhost:8086",
        "token": "test-token",
        "org": "test-org",
        "bucket": "test-bucket",
    }
    defaults.update(kwargs)
    return InfluxDBDestination(broker, "test.**", **defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------


class TestImportGuard:
    def test_import_error_without_library(self) -> None:
        """ImportError is raised with a helpful message when the library is missing."""
        with (
            patch.dict(
                "sys.modules",
                {
                    "influxdb_client": None,
                    "influxdb_client.client": None,
                    "influxdb_client.client.influxdb_client_async": None,
                },
            ),
            pytest.raises(ImportError, match="influxdb-client"),
        ):
            broker = InMemoryBroker(enable_metrics=False)
            # Need to reload the module to pick up the patched import
            import importlib

            import cod3s_data.destinations.influxdb as mod

            importlib.reload(mod)
            mod.InfluxDBDestination(broker, "test.**", token="t", org="o", bucket="b")


# ---------------------------------------------------------------------------
# _message_to_point mapping
# ---------------------------------------------------------------------------


class TestMessageToPoint:
    def test_scalar_float(self) -> None:
        """Scalar float value → single field named 'value'."""
        dest = _make_destination()
        msg = _make_message(value=42.5)
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert "value=42.5" in line

    def test_scalar_int(self) -> None:
        """Scalar int value → single field named 'value'."""
        dest = _make_destination()
        msg = _make_message(value=42)
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert "value=42i" in line

    def test_scalar_string(self) -> None:
        """String value → single field named 'value'."""
        dest = _make_destination()
        msg = _make_message(value="ok")
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert 'value="ok"' in line

    def test_scalar_bool(self) -> None:
        """Boolean value → single field named 'value'."""
        dest = _make_destination()
        msg = _make_message(value=True)
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        # InfluxDB line protocol uses lowercase booleans
        assert "value=true" in line.lower()

    def test_dict_value_multi_fields(self) -> None:
        """Dict value → one field per key."""
        dest = _make_destination()
        msg = _make_message(value={"temp": 22.0, "humidity": 65})
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert "temp=22" in line
        assert "humidity=65i" in line

    def test_empty_string_field_is_dropped(self) -> None:
        """A CLEARED alarm carries direction="" — InfluxDB would misalign it on read."""
        dest = _make_destination()
        msg = _make_message(
            value={"status": "CLEARED", "direction": "", "original_value": {"actual": 1.0}}
        )
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert 'status="CLEARED"' in line
        assert "original_value.actual=1" in line
        assert "direction" not in line

    def test_measurement_from_key(self) -> None:
        """When measurement is None, message.key is used."""
        dest = _make_destination(measurement=None)
        msg = _make_message(key="cpu_usage")
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert line.startswith("cpu_usage")

    def test_measurement_override(self) -> None:
        """When measurement is set, it overrides message.key."""
        dest = _make_destination(measurement="sensors")
        msg = _make_message(key="cpu_usage")
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert line.startswith("sensors")

    def test_tags_from_message(self) -> None:
        """Message tags are set on the Point."""
        dest = _make_destination()
        msg = _make_message(tags={"sensor": "TH001", "location": "room_A"})
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert "sensor=TH001" in line
        assert "location=room_A" in line

    def test_extra_tags_merged(self) -> None:
        """extra_tags are merged with message tags."""
        dest = _make_destination(extra_tags={"env": "prod", "host": "printer-01"})
        msg = _make_message(tags={"sensor": "TH001"})
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert "sensor=TH001" in line
        assert "env=prod" in line
        assert "host=printer-01" in line

    def test_extra_tags_override_message_tags(self) -> None:
        """extra_tags take precedence over message tags on conflict."""
        dest = _make_destination(extra_tags={"env": "staging"})
        msg = _make_message(tags={"env": "dev"})
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        assert "env=staging" in line

    def test_timestamp_preserved(self) -> None:
        """The UTC timestamp from the message is preserved in the Point."""
        ts = datetime(2025, 6, 15, 12, 30, 0, tzinfo=UTC)
        dest = _make_destination()
        msg = _make_message(ts=ts)
        point = dest._message_to_point(msg)

        line = point.to_line_protocol()
        # InfluxDB line protocol timestamp is in nanoseconds
        assert str(int(ts.timestamp())) in line


# ---------------------------------------------------------------------------
# write() and close()
# ---------------------------------------------------------------------------


class TestWriteAndClose:
    @pytest.mark.asyncio
    async def test_write_calls_api(self) -> None:
        """write() calls the write API with the correct bucket and point."""
        dest = _make_destination()

        mock_write_api = AsyncMock()
        mock_client = MagicMock()
        dest._client = mock_client
        dest._write_api = mock_write_api

        msg = _make_message(value=42.5)
        await dest.write(msg)

        mock_write_api.write.assert_awaited_once()
        call_kwargs = mock_write_api.write.call_args
        assert call_kwargs.kwargs["bucket"] == "test-bucket"

    @pytest.mark.asyncio
    async def test_write_lazy_init(self) -> None:
        """write() lazily initializes the client on first call."""
        dest = _make_destination()
        assert dest._client is None

        mock_write_api = AsyncMock()
        mock_client = MagicMock()
        mock_client.write_api.return_value = mock_write_api

        with patch(
            "influxdb_client.client.influxdb_client_async.InfluxDBClientAsync",
            return_value=mock_client,
        ):
            msg = _make_message(value=1.0)
            await dest.write(msg)

            assert dest._client is mock_client
            assert dest._write_api is mock_write_api
            mock_write_api.write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """close() calls client.close() and resets internal state."""
        dest = _make_destination()

        mock_client = AsyncMock()
        mock_write_api = AsyncMock()
        dest._client = mock_client
        dest._write_api = mock_write_api

        await dest.close()

        mock_client.close.assert_awaited_once()
        assert dest._client is None
        assert dest._write_api is None

    @pytest.mark.asyncio
    async def test_close_noop_when_not_initialized(self) -> None:
        """close() is a no-op when the client was never initialized."""
        dest = _make_destination()
        await dest.close()  # Should not raise
        assert dest._client is None


# ---------------------------------------------------------------------------
# Dead-letter channel
# ---------------------------------------------------------------------------


class TestDeadLetter:
    """This destination writes a whole batch in one call and keeps its own retry
    loop, so it reaches the dead-letter channel by a different path than the
    base class. It has to enrich the message just the same — and it is the
    destination most likely to have a DLQ configured, being the one that talks
    to a network service.
    """

    @pytest.mark.asyncio
    async def test_batch_failure_tags_every_message(self) -> None:
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        dead_letters: list[Message] = []

        async def collect(msg: Message) -> None:
            dead_letters.append(msg)

        broker.subscribe("rebuts.**", collect)

        dest = _make_destination(
            broker=broker,
            retry_attempts=1,
            dlq_channel="rebuts.influxdb",
        )
        dest._client = MagicMock()
        dest._write_api = AsyncMock()
        dest._write_api.write.side_effect = ValueError("field type conflict")

        batch = [_make_message(key="extruder", value=213.4), _make_message(key="bed", value=60.0)]
        await dest._write_batch_with_retry(batch)
        await asyncio.sleep(0.1)

        assert len(dead_letters) == 2
        for dead in dead_letters:
            assert dead.tags["dlq_error_type"] == "ValueError"
            assert dead.tags["dlq_error"] == "field type conflict"
            assert dead.tags["dlq_destination"] == "InfluxDBDestination"
            assert dead.tags["dlq_channel_pattern"] == "test.**"
            assert dead.tags["dlq_attempts"] == "1"

        assert {dead.key for dead in dead_letters} == {"extruder", "bed"}
        assert dest.error_count == 2

        await broker.stop()
