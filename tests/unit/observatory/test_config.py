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
        assert config.history_size == 5000
        # One knob for the two stores counted in messages, so a listed row is
        # always a row whose details still exist. Journeys are counted in
        # traces and carry their own budget.
        assert config.buffer_size is None
        assert config.message_detail_cache_size is None
        assert config.retained_events == 5000
        assert config.retained_details == 5000
        assert config.journey_size == 500
        assert config.retained_traces == 500
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


class TestRetentionKnob:
    """`history_size` is the one setting; the explicit caps only override it.

    The three stores have to agree: the UI lists what the ring buffer holds, and
    clicking a row asks the detail and journey stores about it. Set apart — 1000
    listed against 500 inspectable — half the table answered "no longer
    available" when clicked.
    """

    def test_history_size_drives_both_stores(self):
        config = ObservatoryConfig(history_size=2000)
        assert config.retained_events == 2000
        assert config.retained_details == 2000

    def test_journeys_have_their_own_budget(self):
        # A trace holds every step of a whole fan-out — some sixty of them for
        # nineteen published messages — so tying it to `history_size` bought
        # nineteen times more journey history than message history, at 26 kB a
        # trace. Raising the message history must not drag it along.
        config = ObservatoryConfig(history_size=50000)
        assert config.retained_traces == 500
        assert ObservatoryConfig(journey_size=2000).retained_traces == 2000

    def test_explicit_caps_win(self):
        config = ObservatoryConfig(
            history_size=500, buffer_size=4000, message_detail_cache_size=800
        )
        assert config.retained_events == 4000
        assert config.retained_details == 800

    def test_stores_are_built_from_the_knob(self):
        from cod3s_data.observatory import create_observatory

        bridge = create_observatory(ObservatoryConfig(history_size=120, journey_size=60))
        assert bridge._buffer.max_size == 120
        assert bridge._message_store._max_entries == 120
        assert bridge._journey_store._max_entries == 60


class TestChannelEnvOverrides:
    """Channel patterns are overridable like every other Observatory setting."""

    def test_lists_come_from_comma_separated_variables(self, monkeypatch):
        from cod3s_data.config.loaders import load_dict

        monkeypatch.setenv("COD3S_OBSERVATORY_CHANNELS_EXCLUDE", "influx.**, sensors.egm.*")
        monkeypatch.setenv("COD3S_OBSERVATORY_CHANNELS_INCLUDE", "alerts.**")

        config = load_dict({"name": "p", "sources": [], "destinations": []})

        # `PipelineConfig.observatory` stays a plain dict; the section is
        # validated when the Observatory is built from it.
        assert config.observatory is not None
        observatory = ObservatoryConfig.model_validate(config.observatory)
        assert observatory.channels.exclude == ["influx.**", "sensors.egm.*"]
        assert observatory.channels.include == ["alerts.**"]


class TestCliOverridesDoNotReplaceTheFile:
    """`--observatory` must not discard the pipeline's own section.

    The CLI builds an `ObservatoryConfig` holding just a port and the
    interactive flag. Taking it whole threw away everything the file declared —
    retention, watched channels, sampling — every time the Observatory was
    started from the command line, which is how it is normally started.
    """

    def _framework(self, observatory_section, passed):
        from cod3s_data.config.models import PipelineConfig
        from cod3s_data.framework import Framework

        config = PipelineConfig(
            name="p", sources=[], destinations=[], observatory=observatory_section
        )
        return Framework(config, observatory=passed)._bridge

    def test_file_settings_survive_a_cli_port(self):
        bridge = self._framework(
            {"history_size": 1234, "journey_size": 77, "channels": {"exclude": ["influx.**"]}},
            ObservatoryConfig(port=9100),
        )
        assert bridge._buffer.max_size == 1234
        assert bridge._journey_store._max_entries == 77
        assert bridge._channels.observes("influx.smoothed") is False
        assert bridge._channels.observes("alerts.temperature") is True

    def test_what_the_caller_sets_still_wins(self):
        bridge = self._framework(
            {"history_size": 1234},
            ObservatoryConfig(port=9100, history_size=50),
        )
        assert bridge._buffer.max_size == 50

    def test_without_a_section_the_caller_config_is_used_as_is(self):
        bridge = self._framework(None, ObservatoryConfig(port=9100, history_size=321))
        assert bridge._buffer.max_size == 321
