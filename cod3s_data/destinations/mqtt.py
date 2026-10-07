"""MQTT publishing destination.

The counterpart of :class:`cod3s_data.sources.mqtt_source.MQTTSource`: where the
source brings a broker's traffic into the pipeline, this one puts the pipeline's
own messages back on a broker — a computed indicator, an alarm, a suggested
setpoint — for an HMI, a PLC, or another pipeline to pick up.

Two payload shapes, through ``payload_format``:

- ``native`` (default) — the shape ``MQTTSource`` reads back::

      {"ts": <epoch seconds>, "session": "<id>", "fields": {<name>: <value>, ...}}

  so one pipeline can feed another with no glue in between.

- ``raw`` — the value alone, JSON-encoded (``293.8``, ``"ACTIVE"``). What a
  display or a controller subscribing to one topic per quantity expects, usually
  together with ``retain: true`` so a late subscriber gets the last value.

The topic is either a literal or a template over the message: ``{key}``,
``{channel}`` and ``{tags[NAME]}``. One destination subscribed to ``alerts.**``
can therefore fan its publications out per sensor or per production order.

Requires the ``mqtt`` extra::

    pip install cod3s-data[mqtt]
"""

from __future__ import annotations

import json
import string
from typing import Any

import structlog

from cod3s_data.broker.base import Broker
from cod3s_data.core.buffers import OverflowStrategy
from cod3s_data.core.message import Message
from cod3s_data.core.mqtt_client import MQTTConnection, require_aiomqtt
from cod3s_data.destinations.base import Destination, RetryStrategy

_logger = structlog.get_logger()

#: Template fields a topic may use. Anything else is a typo, and a typo caught
#: at construction beats one found on the thousandth publication.
TOPIC_FIELDS = frozenset({"key", "channel", "tags"})

#: Payload shapes understood by ``payload_format``.
PAYLOAD_FORMATS = ("native", "raw")


class MQTTDestination(Destination):
    """Publish each message to an MQTT broker.

    Args:
        broker: Message broker
        channel_pattern: Channel pattern to subscribe to
        host: MQTT broker hostname
        port: MQTT broker port
        topic: Topic to publish on; may template ``{key}``, ``{channel}`` and
            ``{tags[NAME]}``
        payload_format: ``"native"`` or ``"raw"``
        qos: Quality of service of each publication
        retain: Ask the broker to keep the last message on the topic
        client_id: MQTT client identifier; None lets the library generate one
        keepalive: Seconds between pings on an idle connection
        username: User name, when the broker authenticates
        password: Password in clear; prefer ``password_env`` / ``password_file``
        password_env: Environment variable holding the password
        password_file: File holding the password
        tls: Wrap the connection in TLS
        tls_ca: Certificate authority bundle used to verify the broker
        tls_cert: Client certificate, for mutual TLS
        tls_key: Private key matching ``tls_cert``
        tls_insecure: Skip hostname verification
        ts_field: Payload field carrying the epoch timestamp (``native``)
        fields_field: Payload field carrying the measurements (``native``)
        session_field: Payload field carrying the session id (``native``)
        session_tag: Tag read to fill ``session_field``; None to never send one
        buffer_size: Maximum messages held while the broker is unreachable
        overflow_strategy: What to drop when that buffer is full
        retry_attempts: Total publication attempts per message
        retry_strategy: Backoff between those attempts
        dlq_channel: Channel receiving messages that never got through
        batch_size: Messages taken from the buffer per writer pass

    Raises:
        ImportError: If the ``mqtt`` extra is not installed
        ValueError: If ``payload_format`` or ``topic`` is not usable
    """

    def __init__(
        self,
        broker: Broker,
        channel_pattern: str,
        *,
        # --- Connection ---
        host: str = "localhost",
        port: int = 1883,
        client_id: str | None = None,
        keepalive: int = 60,
        username: str | None = None,
        password: str | None = None,
        password_env: str | None = None,
        password_file: str | None = None,
        tls: bool = False,
        tls_ca: str | None = None,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        tls_insecure: bool = False,
        # --- Publication ---
        topic: str = "cod3s/{key}",
        payload_format: str = "native",
        qos: int = 0,
        retain: bool = False,
        # --- Native payload shape ---
        ts_field: str = "ts",
        fields_field: str = "fields",
        session_field: str = "session",
        session_tag: str | None = "session",
        # --- Base class ---
        buffer_size: int = 1000,
        overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_OLDEST,
        retry_attempts: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        dlq_channel: str | None = None,
        batch_size: int = 1,
    ) -> None:
        require_aiomqtt("MQTTDestination")

        if payload_format not in PAYLOAD_FORMATS:
            raise ValueError(
                f"payload_format must be one of {PAYLOAD_FORMATS}, got {payload_format!r}"
            )
        _validate_topic(topic)

        super().__init__(
            broker,
            channel_pattern,
            buffer_size,
            overflow_strategy,
            retry_attempts,
            retry_strategy,
            dlq_channel,
            batch_size,
        )
        self._conn = MQTTConnection(
            host=host,
            port=port,
            client_id=client_id,
            keepalive=keepalive,
            username=username,
            password=password,
            password_env=password_env,
            password_file=password_file,
            tls=tls,
            tls_ca=tls_ca,
            tls_cert=tls_cert,
            tls_key=tls_key,
            tls_insecure=tls_insecure,
        )
        self.host = host
        self.port = port
        self.topic = topic
        self.payload_format = payload_format
        self.qos = qos
        self.retain = retain
        self.ts_field = ts_field
        self.fields_field = fields_field
        self.session_field = session_field
        self.session_tag = session_tag

        self._client: Any = None

    async def write(self, message: Message) -> None:
        """Publish one message.

        Raises so the base class can retry and, in the end, dead-letter: a
        destination that swallowed the error would lose the message silently.

        Args:
            message: Message to publish

        Raises:
            KeyError: If the topic template names a tag the message lacks
            Exception: Any error raised by the MQTT client
        """
        topic = self._topic_for(message)
        payload = self._encode(message)
        client = await self._ensure_client()
        try:
            await client.publish(topic, payload, qos=self.qos, retain=self.retain)
        except Exception:
            # Drop the client so the next attempt reconnects: a publication that
            # failed on a half-dead connection would otherwise keep failing
            # against the same corpse for the whole retry budget.
            await self.close()
            raise

    def _topic_for(self, message: Message) -> str:
        """Resolve the topic template against a message.

        Raises:
            KeyError: If the template names a tag the message does not carry
        """
        if "{" not in self.topic:
            return self.topic
        try:
            return self.topic.format(
                key=message.key,
                channel=self.channel_pattern,
                tags=message.tags,
            )
        except KeyError as exc:
            raise KeyError(
                f"topic {self.topic!r} needs tag {exc.args[0]!r}, "
                f"which message {message.key!r} does not carry"
            ) from None

    def _encode(self, message: Message) -> str:
        """Serialise a message into the configured payload shape."""
        if self.payload_format == "raw":
            return json.dumps(message.value, default=str)

        fields = message.value if isinstance(message.value, dict) else {"value": message.value}
        payload: dict[str, Any] = {
            self.ts_field: message.timestamp.timestamp(),
            self.fields_field: fields,
        }
        if self.session_tag:
            session = message.tags.get(self.session_tag)
            if session is not None:
                payload[self.session_field] = session
        return json.dumps(payload, default=str)

    async def _ensure_client(self) -> Any:
        """Connect on first use, as the InfluxDB destination does.

        Connecting in ``start()`` would make a pipeline fail to start because a
        broker it has nothing to say to yet is down.
        """
        if self._client is None:
            client = self._conn.client()
            await client.__aenter__()
            self._client = client
            _logger.info("mqtt.connected", component="MQTTDestination", **self._conn.describe())
        return self._client

    async def close(self) -> None:
        """Close the connection. Idempotent — ``stop()`` and ``write()`` both call it."""
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception as exc:  # noqa: BLE001 - closing a dead socket is not news
                _logger.debug("mqtt.close_failed", component="MQTTDestination", error=str(exc))


def _validate_topic(topic: str) -> None:
    """Reject a topic template that names something a message cannot provide.

    Raises:
        ValueError: If the template is malformed or uses an unknown field
    """
    try:
        fields = {name for _, name, _, _ in string.Formatter().parse(topic) if name}
    except ValueError as exc:
        raise ValueError(f"topic {topic!r} is not a valid template: {exc}") from None

    unknown = {f.split("[")[0].split(".")[0] for f in fields} - TOPIC_FIELDS
    if unknown:
        raise ValueError(
            f"topic {topic!r} uses unknown field(s) {sorted(unknown)}; "
            f"available: {sorted(TOPIC_FIELDS)}"
        )
