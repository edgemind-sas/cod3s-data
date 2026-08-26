"""Integration tests for InfluxDBDestination (requires a running InfluxDB instance).

Start InfluxDB before running these tests::

    docker compose -f docker-compose.influxdb.yml up -d

Run with::

    uv run pytest tests/integration/test_influxdb_integration.py -v -m integration

Connection settings come from the environment, defaulting to what
``docker-compose.influxdb.yml`` sets up, so a local run needs no configuration.
CI points ``COD3S_TEST_INFLUXDB_URL`` at its ``services:`` host and sets
``COD3S_TEST_INFLUXDB_REQUIRED``, which turns "no server, skip everything" into
a failure — the reason these tests went unrun for so long is that skipping is
indistinguishable from passing in a CI report.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest

influxdb_client = pytest.importorskip("influxdb_client")

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync  # noqa: E402

from cod3s_data.broker import InMemoryBroker  # noqa: E402
from cod3s_data.core.message import Message  # noqa: E402
from cod3s_data.destinations.influxdb import InfluxDBDestination  # noqa: E402
from cod3s_data.sources import SequenceSource  # noqa: E402

# ---------------------------------------------------------------------------
# Connection settings — defaults match docker-compose.influxdb.yml
# ---------------------------------------------------------------------------
INFLUXDB_URL = os.environ.get("COD3S_TEST_INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.environ.get("COD3S_TEST_INFLUXDB_TOKEN", "test-token")
INFLUXDB_ORG = os.environ.get("COD3S_TEST_INFLUXDB_ORG", "cod3s")
INFLUXDB_BUCKET = os.environ.get("COD3S_TEST_INFLUXDB_BUCKET", "test")

# Set where a server is guaranteed to be there: the module then fails instead of
# skipping, so a broken service cannot leave the job green.
INFLUXDB_REQUIRED = os.environ.get("COD3S_TEST_INFLUXDB_REQUIRED", "") not in ("", "0", "false")

# A container needs a moment to finish its setup before it answers a ping.
STARTUP_TIMEOUT_S = 60.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _influxdb_is_ready() -> bool:
    """Check if InfluxDB is reachable."""
    try:
        client = InfluxDBClientAsync(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
        ready = await client.ping()
        await client.close()
        return ready
    except Exception:
        return False


async def _wait_until_ready() -> bool:
    """Poll until InfluxDB answers, or give up.

    A single ping is enough locally, where the container has long been up. It is
    not enough in CI, where the service starts alongside the job and spends a few
    seconds on its initial setup.
    """
    deadline = asyncio.get_event_loop().time() + (STARTUP_TIMEOUT_S if INFLUXDB_REQUIRED else 0.0)
    while True:
        if await _influxdb_is_ready():
            return True
        if asyncio.get_event_loop().time() >= deadline:
            return False
        await asyncio.sleep(1.0)


async def _query_influxdb(flux_query: str) -> list[object]:
    """Run a Flux query and return all records."""
    client = InfluxDBClientAsync(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    try:
        query_api = client.query_api()
        tables = await query_api.query(flux_query)
        records = []
        for table in tables:
            for record in table.records:
                records.append(record)
        return records
    finally:
        await client.close()


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def event_loop():
    """Create a single event loop for the entire module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
async def check_influxdb():
    """Wait for InfluxDB, then skip the module — or fail, if one was promised."""
    if await _wait_until_ready():
        return

    message = f"InfluxDB did not answer at {INFLUXDB_URL}"
    if INFLUXDB_REQUIRED:
        pytest.fail(
            f"{message} within {STARTUP_TIMEOUT_S:.0f}s, and "
            "COD3S_TEST_INFLUXDB_REQUIRED is set. Check the service definition; "
            "these tests must not be skipped where they are expected to run."
        )
    pytest.skip(f"{message} (start with: docker compose -f docker-compose.influxdb.yml up -d)")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestInfluxDBIntegration:
    @pytest.mark.asyncio
    async def test_write_and_query_scalar(self) -> None:
        """Write a scalar message, then query it back from InfluxDB."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        measurement = "test_scalar"
        ts = datetime.now(UTC)

        dest = InfluxDBDestination(
            broker,
            "test.**",
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
            bucket=INFLUXDB_BUCKET,
            measurement=measurement,
            batch_size=1,
        )
        await dest.start()

        msg = _make_message(key="ignored", value=42.5, ts=ts)
        await broker.publish("test.sensor", msg)
        await asyncio.sleep(0.5)

        await dest.stop()
        await broker.stop()

        # Query the data back
        flux = (
            f'from(bucket: "{INFLUXDB_BUCKET}")'
            f" |> range(start: -1m)"
            f' |> filter(fn: (r) => r._measurement == "{measurement}")'
        )
        records = await _query_influxdb(flux)
        assert len(records) >= 1
        assert records[0].get_value() == 42.5

    @pytest.mark.asyncio
    async def test_write_and_query_dict(self) -> None:
        """Write a dict message (multi-field), then verify both fields."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        measurement = "test_dict"

        dest = InfluxDBDestination(
            broker,
            "test.**",
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
            bucket=INFLUXDB_BUCKET,
            measurement=measurement,
            batch_size=1,
        )
        await dest.start()

        msg = _make_message(value={"temp": 22.0, "humidity": 65.0})
        await broker.publish("test.sensor", msg)
        await asyncio.sleep(0.5)

        await dest.stop()
        await broker.stop()

        flux = (
            f'from(bucket: "{INFLUXDB_BUCKET}")'
            f" |> range(start: -1m)"
            f' |> filter(fn: (r) => r._measurement == "{measurement}")'
        )
        records = await _query_influxdb(flux)
        fields = {r.get_field(): r.get_value() for r in records}
        assert fields.get("temp") == 22.0
        assert fields.get("humidity") == 65.0

    @pytest.mark.asyncio
    async def test_pipeline_source_to_influxdb(self) -> None:
        """Full pipeline: SequenceSource → InfluxDBDestination."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        measurement = "test_pipeline"

        dest = InfluxDBDestination(
            broker,
            "seq.**",
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
            bucket=INFLUXDB_BUCKET,
            measurement=measurement,
            batch_size=1,
        )
        await dest.start()

        source = SequenceSource(
            broker,
            "seq.numbers",
            start_value=0,
            end_value=5,
            rate=100.0,
        )
        await source.start()
        await asyncio.sleep(0.5)

        await dest.stop()
        await broker.stop()

        flux = (
            f'from(bucket: "{INFLUXDB_BUCKET}")'
            f" |> range(start: -1m)"
            f' |> filter(fn: (r) => r._measurement == "{measurement}")'
        )
        records = await _query_influxdb(flux)
        values = sorted([r.get_value() for r in records])
        assert values == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_extra_tags_written(self) -> None:
        """extra_tags are persisted in InfluxDB."""
        broker = InMemoryBroker(enable_metrics=False)
        await broker.start()

        measurement = "test_extra_tags"

        dest = InfluxDBDestination(
            broker,
            "test.**",
            url=INFLUXDB_URL,
            token=INFLUXDB_TOKEN,
            org=INFLUXDB_ORG,
            bucket=INFLUXDB_BUCKET,
            measurement=measurement,
            extra_tags={"printer": "gemini3d"},
            batch_size=1,
        )
        await dest.start()

        msg = _make_message(value=1.0)
        await broker.publish("test.sensor", msg)
        await asyncio.sleep(0.5)

        await dest.stop()
        await broker.stop()

        flux = (
            f'from(bucket: "{INFLUXDB_BUCKET}")'
            f" |> range(start: -1m)"
            f' |> filter(fn: (r) => r._measurement == "{measurement}")'
            f' |> filter(fn: (r) => r.printer == "gemini3d")'
        )
        records = await _query_influxdb(flux)
        assert len(records) >= 1
