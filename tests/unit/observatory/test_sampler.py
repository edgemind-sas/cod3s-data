"""Tests for Observatory MessageSampler."""

import time

from cod3s_data.observatory.sampler import MessageSampler


class TestMessageSampler:
    """Tests for sampling strategies."""

    def test_none_strategy_passes_all(self):
        sampler = MessageSampler(strategy="none")
        for _ in range(10):
            assert sampler.should_process("channel") is True

    def test_every_nth_strategy(self):
        sampler = MessageSampler(strategy="every_nth", rate=3)
        results = [sampler.should_process("ch") for _ in range(9)]
        # Every 3rd message should pass: indices 2, 5, 8
        assert results == [False, False, True, False, False, True, False, False, True]

    def test_every_nth_rate_1(self):
        sampler = MessageSampler(strategy="every_nth", rate=1)
        for _ in range(5):
            assert sampler.should_process("ch") is True

    def test_time_based_strategy(self):
        sampler = MessageSampler(strategy="time_based", interval_ms=50)
        # First call should pass (enough time since epoch 0)
        assert sampler.should_process("ch") is True
        # Immediate second call should not pass
        assert sampler.should_process("ch") is False

    def test_time_based_after_interval(self):
        sampler = MessageSampler(strategy="time_based", interval_ms=10)
        assert sampler.should_process("ch") is True
        time.sleep(0.02)  # Wait 20ms > 10ms interval
        assert sampler.should_process("ch") is True

    def test_metrics_always_pass(self):
        sampler = MessageSampler(strategy="every_nth", rate=1000)
        assert sampler.should_process("_metrics.throughput") is True
        assert sampler.should_process("_metrics.latency") is True

    def test_unknown_strategy_passes(self):
        sampler = MessageSampler(strategy="unknown")
        assert sampler.should_process("ch") is True

    def test_strategy_property(self):
        sampler = MessageSampler(strategy="every_nth")
        assert sampler.strategy == "every_nth"
