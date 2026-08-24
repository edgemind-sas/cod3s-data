"""Tests for Observatory configuration models."""

import pytest
from pydantic import ValidationError

from cod3s_data.observatory.config import DebugConfig, ObservatoryConfig, SamplingConfig


class TestSamplingConfig:
    """Tests for SamplingConfig."""

    def test_defaults(self):
        config = SamplingConfig()
        assert config.strategy == "none"
        assert config.rate == 1
        assert config.interval_ms == 100

    def test_valid_strategies(self):
        for strategy in ("none", "every_nth", "time_based"):
            config = SamplingConfig(strategy=strategy)
            assert config.strategy == strategy

    def test_invalid_strategy(self):
        with pytest.raises(ValidationError):
            SamplingConfig(strategy="invalid")

    def test_rate_bounds(self):
        SamplingConfig(rate=1)
        SamplingConfig(rate=10000)
        with pytest.raises(ValidationError):
            SamplingConfig(rate=0)
        with pytest.raises(ValidationError):
            SamplingConfig(rate=10001)

    def test_interval_ms_bounds(self):
        SamplingConfig(interval_ms=10)
        SamplingConfig(interval_ms=10000)
        with pytest.raises(ValidationError):
            SamplingConfig(interval_ms=9)
        with pytest.raises(ValidationError):
            SamplingConfig(interval_ms=10001)


class TestDebugConfig:
    """Tests for DebugConfig."""

    def test_defaults(self):
        config = DebugConfig()
        assert config.enabled is False
        assert config.granularity == "message"
        assert config.auto_pause is False

    def test_valid_granularities(self):
        for g in ("message", "stage", "breakpoint"):
            config = DebugConfig(granularity=g)
            assert config.granularity == g

    def test_invalid_granularity(self):
        with pytest.raises(ValidationError):
            DebugConfig(granularity="invalid")

    def test_enable_debug(self):
        config = DebugConfig(enabled=True, auto_pause=True)
        assert config.enabled is True
        assert config.auto_pause is True


class TestObservatoryConfig:
    """Tests for ObservatoryConfig."""

    def test_defaults(self):
        config = ObservatoryConfig()
        assert config.enabled is True
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.buffer_size == 1000
        assert config.memory_limit_mb == 50
        assert config.interactive is False
        assert isinstance(config.debug, DebugConfig)
        assert isinstance(config.sampling, SamplingConfig)

    def test_interactive_mode(self):
        config = ObservatoryConfig(interactive=True)
        assert config.interactive is True

    def test_port_bounds(self):
        ObservatoryConfig(port=1024)
        ObservatoryConfig(port=65535)
        with pytest.raises(ValidationError):
            ObservatoryConfig(port=1023)
        with pytest.raises(ValidationError):
            ObservatoryConfig(port=65536)

    def test_host_localhost(self):
        config = ObservatoryConfig(host="127.0.0.1")
        assert config.host == "127.0.0.1"
        config = ObservatoryConfig(host="localhost")
        assert config.host == "localhost"

    def test_host_rejects_remote(self):
        with pytest.raises(ValidationError):
            ObservatoryConfig(host="0.0.0.0")
        with pytest.raises(ValidationError):
            ObservatoryConfig(host="192.168.1.1")

    def test_buffer_size_bounds(self):
        ObservatoryConfig(buffer_size=100)
        ObservatoryConfig(buffer_size=100000)
        with pytest.raises(ValidationError):
            ObservatoryConfig(buffer_size=99)
        with pytest.raises(ValidationError):
            ObservatoryConfig(buffer_size=100001)

    def test_memory_limit_bounds(self):
        ObservatoryConfig(memory_limit_mb=10)
        ObservatoryConfig(memory_limit_mb=500)
        with pytest.raises(ValidationError):
            ObservatoryConfig(memory_limit_mb=9)
        with pytest.raises(ValidationError):
            ObservatoryConfig(memory_limit_mb=501)

    def test_nested_debug_config(self):
        config = ObservatoryConfig(
            debug=DebugConfig(enabled=True, granularity="stage"),
        )
        assert config.debug.enabled is True
        assert config.debug.granularity == "stage"

    def test_nested_sampling_config(self):
        config = ObservatoryConfig(
            sampling=SamplingConfig(strategy="every_nth", rate=10),
        )
        assert config.sampling.strategy == "every_nth"
        assert config.sampling.rate == 10

    def test_from_dict(self):
        config = ObservatoryConfig.model_validate(
            {
                "enabled": True,
                "port": 9000,
                "debug": {"enabled": True, "granularity": "breakpoint"},
                "sampling": {"strategy": "time_based", "interval_ms": 500},
            }
        )
        assert config.port == 9000
        assert config.debug.enabled is True
        assert config.debug.granularity == "breakpoint"
        assert config.sampling.strategy == "time_based"
        assert config.sampling.interval_ms == 500
