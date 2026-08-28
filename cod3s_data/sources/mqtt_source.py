"""MQTT ingestion source.

The framework's other sources all read files on the local machine. This one is
the boundary connector: it subscribes to an MQTT topic and turns each JSON
payload into a :class:`Message` on the in-process broker. MQTT is used only
*between* machines — once a message is in, the pipeline stays in-process.

Two payload shapes are supported through ``source_format``:

- ``native`` (default) — the shape a purpose-built forwarder emits::

      {"ts": <epoch seconds>, "session": "<id>", "fields": {<name>: <value>, ...}}

  Field names are configurable (``ts_field``, ``fields_field``,
  ``session_field``), so this also fits third-party publishers that use
  different names for the same three parts.

- ``telegraf`` — the JSON that Telegraf's ``outputs.mqtt`` writes with
  ``data_format = "json"``::

      {"name": "<measurement>", "timestamp": <epoch seconds>,
       "tags": {...}, "fields": {<name>: <value>, ...}}

  A session identifier is recovered from one of the tags (``session_from_tag``,
  typically the ``path`` tag that ``inputs.tail`` attaches) by matching
  ``session_regex`` against it.

In both cases ``fields`` becomes the message's dict value, so a downstream
``unpack`` behaves exactly as it would on a CSV source.

Requires the ``mqtt`` extra::

    pip install cod3s-data[mqtt]
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import structlog

from cod3s_data.broker.base import Broker
from cod3s_data.core.message import Message
from cod3s_data.sources.base import BatchMode, Source

_logger = structlog.get_logger()

#: Matches the ``YYYY-MM-DD_HH-MM-SS`` stamp that recording systems commonly put
#: at the head of a session's file name. Override via ``session_regex``.
DEFAULT_SESSION_REGEX = r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"


class MQTTSource(Source):
    """Subscribe to an MQTT topic and emit one message per JSON payload.

    Args:
        broker: Message broker
        channel: Target channel
        host: MQTT broker hostname
        port: MQTT broker port
        topic: Topic filter to subscribe to (wildcards allowed)
        default_key: Message key to use when the payload carries no name
        default_tags: Tags added to every emitted message
        ts_field: Payload field holding the epoch timestamp
        fields_field: Payload field holding the measurement dict
        session_field: Payload field holding the session id (``native`` only)
        session_tag: Tag name under which the session id is recorded; None to
            drop it
        source_format: ``"native"`` or ``"telegraf"``
        session_from_tag: Tag to mine the session id from (``telegraf`` only)
        session_regex: Pattern applied to that tag; group 1 is the session id
        name_as_key: Use the payload's ``name`` as the message key
            (``telegraf`` only)
        strip_suffix: Suffix removed from every field name before mapping —
            ``"_mean"`` undoes Telegraf's ``basicstats`` renaming
        field_map: Explicit renaming applied after ``strip_suffix``
        field_keep: When set, only these (post-mapping) field names are kept

    Raises:
        ValueError: If ``source_format`` is neither ``native`` nor ``telegraf``
    """

    def __init__(
        self,
        broker: Broker,
        channel: str,
        *,
        host: str = "localhost",
        port: int = 1883,
        topic: str = "#",
        default_key: str | None = None,
        default_tags: dict[str, str] | None = None,
        ts_field: str = "ts",
        fields_field: str = "fields",
        session_field: str = "session",
        session_tag: str | None = "session",
        source_format: str = "native",
        session_from_tag: str = "path",
        session_regex: str = DEFAULT_SESSION_REGEX,
        name_as_key: bool = True,
        strip_suffix: str | None = None,
        field_map: dict[str, str] | None = None,
        field_keep: list[str] | None = None,
    ) -> None:
        super().__init__(broker, channel, batch_mode=BatchMode.REALTIME)
        if source_format not in ("native", "telegraf"):
            raise ValueError(f"source_format must be 'native' or 'telegraf', got {source_format!r}")
        self._host = host
        self._port = port
        self._topic = topic
        self._default_key = default_key
        self._default_tags = default_tags or {}
        self._ts_field = ts_field
        self._fields_field = fields_field
        self._session_field = session_field
        self._session_tag = session_tag
        self._source_format = source_format
        self._session_from_tag = session_from_tag
        self._session_re = re.compile(session_regex)
        self._name_as_key = name_as_key
        self._strip_suffix = strip_suffix
        self._field_map = field_map or {}
        self._field_keep = set(field_keep) if field_keep else None

    def _remap_fields(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Normalise field names: strip suffix, rename, then filter."""
        out: dict[str, Any] = {}
        for raw_key, val in fields.items():
            key = raw_key
            if self._strip_suffix and key.endswith(self._strip_suffix):
                key = key[: -len(self._strip_suffix)]
            key = self._field_map.get(key, key)
            if self._field_keep is not None and key not in self._field_keep:
                continue
            out[key] = val
        return out

    async def produce(self) -> AsyncIterator[Message]:
        """Subscribe to the topic and yield a message per parsable payload.

        Raises:
            ImportError: If the ``mqtt`` extra is not installed
        """
        try:
            import aiomqtt
        except ImportError:
            raise ImportError(
                "MQTTSource requires the 'mqtt' extra: pip install cod3s-data[mqtt]"
            ) from None

        _logger.info("mqtt.start", host=self._host, port=self._port, topic=self._topic)
        async with aiomqtt.Client(hostname=self._host, port=self._port) as client:
            await client.subscribe(self._topic)
            async for mqtt_msg in client.messages:
                if not self._running:
                    break
                msg = self._parse(mqtt_msg.payload)
                if msg is not None:
                    yield msg

    def _parse(self, payload: bytes) -> Message | None:
        try:
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            _logger.warning("mqtt.bad_payload", error=str(exc))
            return None
        if not isinstance(data, dict):
            return None
        if self._source_format == "telegraf":
            return self._parse_telegraf(data)
        return self._parse_native(data)

    def _timestamp(self, raw: Any) -> datetime:
        """Epoch seconds to an aware datetime; now() when absent or unusable."""
        if raw is None:
            return datetime.now(tz=UTC)
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        except (ValueError, TypeError, OSError, OverflowError):
            _logger.warning("mqtt.bad_timestamp", value=repr(raw))
            return datetime.now(tz=UTC)

    def _parse_native(self, data: dict[str, Any]) -> Message | None:
        timestamp = self._timestamp(data.get(self._ts_field))
        value = self._remap_fields(data.get(self._fields_field, {}) or {})

        tags = dict(self._default_tags)
        session = data.get(self._session_field)
        if session and self._session_tag:
            tags[self._session_tag] = str(session)

        return Message(
            key=self._default_key or "mqtt_msg",
            timestamp=timestamp,
            value=value,
            tags=tags,
        )

    def _parse_telegraf(self, data: dict[str, Any]) -> Message | None:
        timestamp = self._timestamp(data.get(self._ts_field, data.get("timestamp")))
        value = self._remap_fields(data.get(self._fields_field, {}) or {})

        tags = dict(self._default_tags)
        src_tags = data.get("tags") or {}
        if self._session_tag:
            match = self._session_re.search(str(src_tags.get(self._session_from_tag, "")))
            if match:
                tags[self._session_tag] = match.group(1)

        key = self._default_key or "mqtt_msg"
        if self._name_as_key and data.get("name"):
            key = str(data["name"])

        return Message(key=key, timestamp=timestamp, value=value, tags=tags)
