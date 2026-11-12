"""Parameter store: rebinds component attributes from broker messages.

Backs the ``ParamRef`` mechanism (see ``config/models.py``). One store per
referenced parameter; the factory creates them and attaches them to the
component via ``component._param_stores``. The owning component lifecycle
(``start``/``stop``) drives the store lifecycle.

Reads the latest value from broker history at ``start()`` so a transform
that begins after the parameter source has already published is hydrated
synchronously before its first data message arrives. A merging store replays
everything the broker kept for the channel instead, oldest first, since each
message holds only a fragment of the value.
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

import structlog

from cod3s_data.broker.base import Broker, SubscriptionHandle
from cod3s_data.core.message import Message

_logger = structlog.get_logger()

#: Messages replayed at ``start()`` to rebuild a merging parameter, when the
#: broker does not say how much history it keeps per channel. A store that
#: replaces its value needs one message; a merging one has to see every fragment.
#: Either way the broker's own per-channel history is the real bound.
MERGE_HISTORY = 500


def _deep_merge(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """``update`` over ``current``, descending into the mappings both sides hold.

    A fragment ``{"Gap": {"min_count": 140}}`` changes that one leaf and keeps
    Gap's other entries, as a flat fragment keeps the other top-level keys.
    Neither argument is modified.
    """
    merged = dict(current)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class ParameterStore:
    """Subscribes to a broker channel and rebinds an attribute on the owner."""

    def __init__(
        self,
        *,
        broker: Broker,
        owner: Any,
        param_name: str,
        ref: str,
        default: Any = None,
        dict_key: str | None = None,
        merge: bool = False,
    ) -> None:
        self.broker = broker
        self.owner = owner
        self.param_name = param_name
        self.ref = ref
        self.default = default
        self.dict_key = dict_key
        self.merge = merge

        self._handle: SubscriptionHandle | None = None
        self._current: Any = default

    @property
    def current(self) -> Any:
        """Last applied value (or default before any message)."""
        return self._current

    def rejection(self, raw: Any) -> str | None:
        """Why this channel value would be refused, or None if it would not.

        Tries the value on a shallow copy of the owner, so that the owner's own
        validation answers and the owner itself stays untouched.
        """
        if self.merge and not isinstance(raw, dict):
            return f"{self.param_name} expects a mapping, got {raw!r}"
        new_value = self._extract(raw)
        if new_value is None:
            return None
        try:
            setattr(copy.copy(self.owner), self.param_name, new_value)
        except (TypeError, ValueError) as e:
            return str(e)
        return None

    async def start(self) -> None:
        """Hydrate from history then subscribe for live updates.

        A merging store replays the history the broker kept for the channel:
        each message carries only part of the value, so keeping the last one
        would rebuild a single fragment and silently lose the rest. The replay
        runs oldest first — ``get_history`` returns newest first, and applied
        in that order an old fragment would overwrite a newer one for the same
        key.
        """
        kept = getattr(self.broker, "default_history_size", None)
        if not self.merge:
            count = 1
        elif isinstance(kept, int) and kept > 0:
            count = kept
        else:
            count = MERGE_HISTORY
        history = self.broker.get_history(self.ref, count=count)
        for message in reversed(history):
            await self._apply(message, emit_event=False)
        if self.merge and len(history) >= count:
            # A full buffer may have evicted fragments that nothing replaced:
            # the value is rebuilt from the most recent ones only.
            _logger.warning(
                "Parameter history full, oldest fragments may be lost",
                param=self.param_name,
                ref=self.ref,
                replayed=len(history),
            )

        self._handle = self.broker.subscribe(self.ref, self._on_message)

    async def stop(self) -> None:
        """Unsubscribe from the parameter channel."""
        if self._handle is not None:
            self.broker.unsubscribe(self._handle)
            self._handle = None

    async def _on_message(self, message: Message) -> None:
        await self._apply(message, emit_event=True)

    async def _apply(self, message: Message, *, emit_event: bool) -> None:
        new_value = self._extract(message.value)
        if new_value is None:
            return

        old = self._current
        lock = self._owner_lock()
        try:
            if lock is not None:
                async with lock:
                    setattr(self.owner, self.param_name, new_value)
            else:
                setattr(self.owner, self.param_name, new_value)
        except (TypeError, ValueError) as e:
            # The owner refused the value. It keeps the previous one; a value
            # left in the channel history must not stop the pipeline at start.
            _logger.warning(
                "Parameter value rejected", param=self.param_name, ref=self.ref, error=str(e)
            )
            return
        self._current = new_value

        if not emit_event:
            return

        bridge = getattr(self.owner, "_bridge", None)
        if bridge is None:
            return
        try:
            await bridge.on_param_updated(
                getattr(self.owner, "_component_id", ""),
                self.param_name,
                old,
                new_value,
                channel=self.ref,
            )
        except AttributeError:
            # Bridge predates on_param_updated — silent.
            pass
        except Exception as e:  # noqa: BLE001
            _logger.warning("Observatory hook error", hook="on_param_updated", error=str(e))

    def _extract(self, raw: Any) -> Any:
        if self.dict_key is not None:
            if not isinstance(raw, dict):
                return None
            return raw.get(self.dict_key)
        if self.merge:
            if not isinstance(raw, dict):
                return None
            current = self._current if isinstance(self._current, dict) else {}
            return _deep_merge(current, raw)
        return raw

    def _owner_lock(self) -> asyncio.Lock | None:
        """Use the StatefulTransform lock when available, else None."""
        lock = getattr(self.owner, "_lock", None)
        return lock if isinstance(lock, asyncio.Lock) else None
