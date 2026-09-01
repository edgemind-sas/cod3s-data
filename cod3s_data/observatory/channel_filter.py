"""Which channels the Observatory watches at all."""

from __future__ import annotations

from cod3s_data.core.subscription_registry import SubscriptionRegistry


class ChannelFilter:
    """Decides whether a channel is observed, from include/exclude patterns.

    Retention is counted in messages, so the loudest channel decides how far
    back the Observatory can see: on a six-sensor pipeline, `influx.smoothed`
    and the raw sensor channels account for nine messages in ten, and an alarm
    — published only on a transition — is evicted within seconds of happening.
    Naming the channels worth watching buys history where it matters, and
    costs nothing anywhere else.

    Patterns are the broker's own: `sensors.*` matches one segment, `alerts.**`
    matches any depth. An empty `include` watches everything; `exclude` then
    removes from it. A channel excluded here is not observed at all — it leaves
    no message, and no journey step, so a journey crossing it stops at that
    boundary.

    `_metrics.*` is never filtered: the Metrics page is fed by it, and it is
    low-frequency by construction.
    """

    def __init__(
        self,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> None:
        self._include = list(include or [])
        self._exclude = list(exclude or [])
        # Channels are few and repeat forever; the decision is taken once each.
        self._decisions: dict[str, bool] = {}

    @property
    def filters_anything(self) -> bool:
        """Whether this filter can reject a channel at all."""
        return bool(self._include or self._exclude)

    def observes(self, channel: str) -> bool:
        """Whether messages on `channel` are observed."""
        cached = self._decisions.get(channel)
        if cached is not None:
            return cached
        decision = self._decide(channel)
        self._decisions[channel] = decision
        return decision

    def _decide(self, channel: str) -> bool:
        if channel.startswith("_metrics."):
            return True
        if self._include and not any(
            SubscriptionRegistry.matches(pattern, channel) for pattern in self._include
        ):
            return False
        return not any(SubscriptionRegistry.matches(pattern, channel) for pattern in self._exclude)
