"""Message sampler for Observatory - controls event forwarding rate."""

from __future__ import annotations

import time


class MessageSampler:
    """Sampling strategies for high-throughput pipelines.

    Strategies:
    - none: Forward all events (default)
    - every_nth: Forward every Nth event
    - time_based: Forward at most one event per time interval

    Metrics channels (_metrics.*) always bypass sampling.
    """

    def __init__(
        self,
        strategy: str = "none",
        rate: int = 1,
        interval_ms: int = 100,
    ) -> None:
        self._strategy = strategy
        self._rate = max(1, rate)
        self._interval_s = interval_ms / 1000.0
        # Per channel, both of them. A single shared counter let a fast channel
        # consume the quota and starve the slow ones: with `every_nth` at 10 and
        # one channel publishing a hundred times more than another, the quiet
        # channel was almost never the Nth message and effectively disappeared.
        self._counters: dict[str, int] = {}
        self._last_process_time: dict[str, float] = {}

    def should_process(self, channel: str) -> bool:
        """Determine if this message should be processed by the Observatory."""
        # Always forward metrics (they are already low-frequency)
        if channel.startswith("_metrics."):
            return True

        if self._strategy == "none":
            return True

        if self._strategy == "every_nth":
            count = self._counters.get(channel, 0) + 1
            self._counters[channel] = count
            return count % self._rate == 0

        if self._strategy == "time_based":
            now = time.monotonic()
            if now - self._last_process_time.get(channel, 0.0) >= self._interval_s:
                self._last_process_time[channel] = now
                return True
            return False

        return True

    @property
    def strategy(self) -> str:
        """The configured strategy: "none", "every_nth" or "time_based".

        An unrecognised value is kept as given and behaves as "none", since
        `should_process()` forwards everything it cannot match.
        """
        return self._strategy
