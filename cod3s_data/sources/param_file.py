"""Parameter-file source: publishes initial parameter values at job launch.

Reads a YAML or JSON file at startup, flattens nested mappings into dotted
keys (e.g. ``alarm.extruder.setpoint``), and publishes one ``Message`` per
leaf on a sub-channel of ``self.channel``. Targets the same broker channels
that components reference via ``ParamRef``.

Typical use: an operator selects a print job; a per-job ``setpoints.yaml``
populates ``params.alarm.extruder``, ``params.alarm.bed``, etc., before
sensor data starts flowing. Live edits later (Observatory, REST, MQTT)
republish on the same channels.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cod3s_data.broker.base import Broker, DeliveryGuarantee
from cod3s_data.core.message import Message
from cod3s_data.sources.base import BatchMode, Source


class ParamFileSource(Source):
    """Publishes the contents of a YAML/JSON file as parameter messages."""

    def __init__(
        self,
        broker: Broker,
        channel: str,
        file_path: str | Path,
        *,
        flatten: bool = True,
        delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_MOST_ONCE,
    ) -> None:
        super().__init__(broker, channel, BatchMode.BATCH, delivery_guarantee)
        self.file_path = Path(file_path)
        self.flatten = flatten

    async def produce(self) -> AsyncIterator[Message]:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Parameter file not found: {self.file_path}")

        data = self._load()
        timestamp = datetime.now(UTC)

        if not isinstance(data, dict):
            raise ValueError(
                f"Parameter file must contain a mapping at the top level, "
                f"got {type(data).__name__} in {self.file_path}"
            )

        if self.flatten:
            for path, value in self._flatten(data, prefix=""):
                yield Message(key=path, timestamp=timestamp, value=value, tags={})
        else:
            for name, value in data.items():
                yield Message(key=name, timestamp=timestamp, value=value, tags={})

    async def _publish_message(self, message: Message) -> None:
        """Override: each param is published on ``{channel}.{key}``.

        ``message.key`` is the flattened parameter path (e.g.
        ``alarm.extruder.setpoint``). The base class would publish all
        messages on a single channel — here we route per-key.

        We also rewrite ``message.key`` to the full target channel so the
        downstream measurement name is consistent whether the value comes
        from this source or from ``ObservatoryBridge.update_param`` (which
        already uses the channel as the message key).
        """
        target = f"{self.channel}.{message.key}" if message.key else self.channel
        consistent = Message(
            key=target,
            timestamp=message.timestamp,
            value=message.value,
            tags=message.tags,
        )
        await self.broker.publish(target, consistent, self.delivery_guarantee)

    def _load(self) -> Any:
        text = self.file_path.read_text()
        suffix = self.file_path.suffix.lower()
        if suffix in (".yaml", ".yml"):
            import yaml  # local import to avoid hard dependency at import time

            return yaml.safe_load(text)
        if suffix == ".json":
            return json.loads(text)
        # Fallback: try YAML first (a superset of JSON), then JSON
        try:
            import yaml

            return yaml.safe_load(text)
        except Exception:
            return json.loads(text)

    def _flatten(self, obj: Any, prefix: str) -> list[tuple[str, Any]]:
        """Depth-first flattening: ``{a: {b: 1}}`` -> ``[("a.b", 1)]``."""
        out: list[tuple[str, Any]] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(v, dict):
                    out.extend(self._flatten(v, path))
                else:
                    out.append((path, v))
        else:
            out.append((prefix, obj))
        return out
