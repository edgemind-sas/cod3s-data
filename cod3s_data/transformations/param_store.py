"""Parameter store: rebinds component attributes from broker messages.

Backs the ``ParamRef`` mechanism (see ``config/models.py``). One store per
referenced parameter; the factory creates them and attaches them to the
component via ``component._param_stores``. The owning component lifecycle
(``start``/``stop``) drives the store lifecycle.

Reads the latest value from broker history at ``start()`` so a transform
that begins after the parameter source has already published is hydrated
synchronously before its first data message arrives.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from cod3s_data.broker.base import Broker, SubscriptionHandle
from cod3s_data.core.message import Message

_logger = structlog.get_logger()


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
    ) -> None:
        self.broker = broker
        self.owner = owner
        self.param_name = param_name
        self.ref = ref
        self.default = default
        self.dict_key = dict_key

        self._handle: SubscriptionHandle | None = None
        self._current: Any = default

    @property
    def current(self) -> Any:
        """Last applied value (or default before any message)."""
        return self._current

    async def start(self) -> None:
        """Hydrate from history then subscribe for live updates."""
        history = self.broker.get_history(self.ref, count=1)
        if history:
            await self._apply(history[0], emit_event=False)

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
        if lock is not None:
            async with lock:
                setattr(self.owner, self.param_name, new_value)
        else:
            setattr(self.owner, self.param_name, new_value)
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
        return raw

    def _owner_lock(self) -> asyncio.Lock | None:
        """Use the StatefulTransform lock when available, else None."""
        lock = getattr(self.owner, "_lock", None)
        return lock if isinstance(lock, asyncio.Lock) else None
