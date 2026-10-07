"""Integration tests for the MQTT pair (requires a running MQTT broker).

Start Mosquitto before running these tests::

    docker compose -f docker-compose.mqtt.yml up -d

Run with::

    uv run pytest tests/integration/test_mqtt_integration.py -v -m integration

Connection settings come from the environment, defaulting to what
``docker-compose.mqtt.yml`` sets up, so a local run needs no configuration. CI
points ``COD3S_TEST_MQTT_HOST`` at its ``services:`` host and sets
``COD3S_TEST_MQTT_REQUIRED``, which turns "no broker, skip everything" into a
failure — a skip is indistinguishable from a pass in a CI report.

What is worth exercising against a real broker, and cannot be faked: that what
the destination publishes is exactly what the source reads back, and that a
dropped connection is survived. The second one runs the source through a TCP
relay this module opens itself, so the test can cut the connection without
touching the container.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import UTC, datetime

import pytest

aiomqtt = pytest.importorskip("aiomqtt")

from cod3s_data.broker import InMemoryBroker  # noqa: E402
from cod3s_data.core.message import Message  # noqa: E402
from cod3s_data.destinations.mqtt import MQTTDestination  # noqa: E402
from cod3s_data.sources import MQTTSource  # noqa: E402

# ---------------------------------------------------------------------------
# Connection settings — defaults match docker-compose.mqtt.yml
# ---------------------------------------------------------------------------
MQTT_HOST = os.environ.get("COD3S_TEST_MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("COD3S_TEST_MQTT_PORT", "1883"))

# Set where a broker is guaranteed to be there: the module then fails instead of
# skipping, so a broken service cannot leave the job green.
MQTT_REQUIRED = os.environ.get("COD3S_TEST_MQTT_REQUIRED", "") not in ("", "0", "false")

STARTUP_TIMEOUT_S = 30.0

pytestmark = pytest.mark.integration


async def _broker_is_ready() -> bool:
    try:
        async with asyncio.timeout(5):
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT):
                return True
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
async def require_broker():
    """Skip the module when no broker answers — unless CI says there must be one."""
    deadline = asyncio.get_running_loop().time() + (STARTUP_TIMEOUT_S if MQTT_REQUIRED else 2.0)
    while asyncio.get_running_loop().time() < deadline:
        if await _broker_is_ready():
            return
        await asyncio.sleep(0.5)

    message = f"no MQTT broker on {MQTT_HOST}:{MQTT_PORT}"
    if MQTT_REQUIRED:
        pytest.fail(f"{message} and COD3S_TEST_MQTT_REQUIRED is set")
    pytest.skip(f"{message} (start docker-compose.mqtt.yml)")


def _message(key: str = "temperature_top", value=293.8, tags=None) -> Message:
    return Message(
        key=key,
        timestamp=datetime(2026, 9, 10, 14, 15, tzinfo=UTC),
        value=value,
        tags=tags or {},
    )


async def _collect(
    topic: str, count: int, subscribed: asyncio.Event, timeout: float = 10.0
) -> list[bytes]:
    """Subscribe with a bare client and return the first ``count`` payloads.

    ``subscribed`` is created by the caller rather than kept module-wide: each
    test runs in its own event loop, and an Event built at import time belongs
    to none of them.
    """
    received: list[bytes] = []
    async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
        await client.subscribe(topic)
        subscribed.set()
        async with asyncio.timeout(timeout):
            async for msg in client.messages:
                received.append(msg.payload)
                if len(received) >= count:
                    return received
    return received


class TestPublishing:
    async def test_native_payload_reaches_the_topic(self, unique_topic):
        subscribed = asyncio.Event()
        collector = asyncio.create_task(_collect(unique_topic, 1, subscribed))
        await subscribed.wait()

        dest = MQTTDestination(
            InMemoryBroker(enable_metrics=False),
            "sensors.**",
            host=MQTT_HOST,
            port=MQTT_PORT,
            topic=unique_topic,
            session_tag="OF",
            session_field="OF",
        )
        await dest.write(_message(value={"temp": 293.8}, tags={"OF": "OF-1234"}))
        await dest.close()

        payload = json.loads((await collector)[0])
        assert payload["fields"] == {"temp": 293.8}
        assert payload["OF"] == "OF-1234"

    async def test_raw_payload_is_the_bare_value(self, unique_topic):
        subscribed = asyncio.Event()
        collector = asyncio.create_task(_collect(unique_topic, 1, subscribed))
        await subscribed.wait()

        dest = MQTTDestination(
            InMemoryBroker(enable_metrics=False),
            "sensors.**",
            host=MQTT_HOST,
            port=MQTT_PORT,
            topic=unique_topic,
            payload_format="raw",
        )
        await dest.write(_message(value=293.8))
        await dest.close()

        assert (await collector)[0] == b"293.8"


class TestRoundTrip:
    async def test_what_the_destination_writes_the_source_reads(self, unique_topic):
        """The pair must compose: one pipeline feeding another with no glue."""
        in_broker = InMemoryBroker(enable_metrics=False)
        await in_broker.start()
        received: list[Message] = []

        async def keep(msg: Message) -> None:
            received.append(msg)

        in_broker.subscribe("raw.bridged", keep)

        source = MQTTSource(
            in_broker,
            "raw.bridged",
            host=MQTT_HOST,
            port=MQTT_PORT,
            topic=unique_topic,
            default_key="bridged",
            session_field="OF",
            session_tag="OF",
        )
        source_task = asyncio.create_task(source.start())
        await asyncio.sleep(1.0)  # let the subscription settle

        dest = MQTTDestination(
            InMemoryBroker(enable_metrics=False),
            "sensors.**",
            host=MQTT_HOST,
            port=MQTT_PORT,
            topic=unique_topic,
            session_tag="OF",
            session_field="OF",
        )
        await dest.write(_message(value={"temp": 293.8}, tags={"OF": "OF-1234"}))
        await dest.close()

        for _ in range(100):
            if received:
                break
            await asyncio.sleep(0.1)

        await source.stop()
        source_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await source_task
        await in_broker.stop()

        assert len(received) == 1
        assert received[0].value == {"temp": 293.8}
        assert received[0].tags["OF"] == "OF-1234"
        assert received[0].timestamp == datetime(2026, 9, 10, 14, 15, tzinfo=UTC)


class TestReconnection:
    async def test_the_source_comes_back_after_the_connection_drops(self, unique_topic):
        """The regression this pair was hardened for.

        The source talks to the broker through a relay opened here, so the test
        can sever the connection the way a broker restart would — without
        restarting the container, which a test has no business doing.
        """
        relay = _Relay(MQTT_HOST, MQTT_PORT)
        await relay.start()

        in_broker = InMemoryBroker(enable_metrics=False)
        await in_broker.start()
        received: list[Message] = []

        async def keep(msg: Message) -> None:
            received.append(msg)

        in_broker.subscribe("raw.bridged", keep)

        source = MQTTSource(
            in_broker,
            "raw.bridged",
            host="127.0.0.1",
            port=relay.port,
            topic=unique_topic,
            default_key="bridged",
        )
        source_task = asyncio.create_task(source.start())
        await asyncio.sleep(1.0)

        await _publish(unique_topic, {"ts": 1.0, "fields": {"a": 1}})
        await _wait_for(lambda: len(received) == 1)

        await relay.cut()  # the broker "restarts"
        await asyncio.sleep(2.0)  # first backoff is 1 s

        await _publish(unique_topic, {"ts": 2.0, "fields": {"a": 2}})
        await _wait_for(lambda: len(received) == 2, timeout=15.0)

        await source.stop()
        source_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await source_task
        await relay.stop()
        await in_broker.stop()

        assert [m.value for m in received] == [{"a": 1}, {"a": 2}]


async def _publish(topic: str, payload: dict) -> None:
    async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
        await client.publish(topic, json.dumps(payload))


async def _wait_for(predicate, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition not met within the timeout")


class _Relay:
    """A TCP relay in front of the broker, so a test can cut the connection."""

    def __init__(self, host: str, port: int) -> None:
        self._target = (host, port)
        self._server: asyncio.Server | None = None
        self._pipes: list[asyncio.Task[None]] = []
        self._writers: list[asyncio.StreamWriter] = []
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_reader, up_writer = await asyncio.open_connection(*self._target)
        except OSError:
            writer.close()
            return
        self._writers += [writer, up_writer]
        self._pipes += [
            asyncio.create_task(_pipe(reader, up_writer)),
            asyncio.create_task(_pipe(up_reader, writer)),
        ]

    async def cut(self) -> None:
        """Drop every live connection, leaving the relay open for the next one."""
        for writer in self._writers:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        self._writers.clear()
        for pipe in self._pipes:
            pipe.cancel()
        self._pipes.clear()

    async def stop(self) -> None:
        await self.cut()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    with contextlib.suppress(Exception):
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    with contextlib.suppress(Exception):
        writer.close()


@pytest.fixture
def unique_topic(request) -> str:
    """A topic of its own per test, so a retained or late message cannot leak."""
    return f"cod3s/test/{request.node.name}/{datetime.now(UTC).timestamp()}"
