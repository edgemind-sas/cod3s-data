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
        self._counter: int = 0
        self._last_process_time: float = 0.0

    def should_process(self, channel: str) -> bool:
        """Determine if this message should be processed by the Observatory."""
        # Always forward metrics (they are already low-frequency)
        if channel.startswith("_metrics."):
            return True

        if self._strategy == "none":
            return True

        if self._strategy == "every_nth":
            self._counter += 1
            return self._counter % self._rate == 0

        if self._strategy == "time_based":
            now = time.monotonic()
            if now - self._last_process_time >= self._interval_s:
                self._last_process_time = now
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
