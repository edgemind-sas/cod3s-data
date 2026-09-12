"""Tests for the Observatory's channel filter."""

from cod3s_data.observatory.channel_filter import ChannelFilter


class TestChannelFilter:
    """Which channels the Observatory watches at all.

    Retention is counted in messages, so the loudest channel decides how far
    back the Observatory can see. On the six-sensor bench, `influx.smoothed`
    and the raw sensor channels are nine messages in ten, and an alarm — one
    message per transition — is evicted seconds after it fires.
    """

    def test_watches_everything_by_default(self):
        f = ChannelFilter()
        assert f.observes("anything.at.all") is True
        assert f.filters_anything is False

    def test_include_restricts(self):
        f = ChannelFilter(include=["alerts.**", "params.**"])
        assert f.observes("alerts.temperature") is True
        assert f.observes("params.consignes") is True
        assert f.observes("influx.smoothed") is False
        assert f.observes("sensors.egm.temperature_top") is False
        assert f.filters_anything is True

    def test_exclude_removes(self):
        f = ChannelFilter(exclude=["influx.**", "sensors.egm.*"])
        assert f.observes("alerts.temperature") is True
        assert f.observes("influx.smoothed") is False
        assert f.observes("sensors.egm.pressure") is False
        # `*` is one segment, so a deeper channel is untouched by that pattern.
        assert f.observes("sensors.smoothed.pressure_smoothed") is True

    def test_exclude_applies_within_include(self):
        f = ChannelFilter(include=["sensors.**"], exclude=["sensors.egm.**"])
        assert f.observes("sensors.smoothed.pressure_smoothed") is True
        assert f.observes("sensors.egm.pressure") is False
        assert f.observes("alerts.temperature") is False

    def test_metrics_are_never_filtered(self):
        # The Metrics page is fed by them, and they are low-frequency anyway.
        f = ChannelFilter(include=["alerts.**"], exclude=["_metrics.**"])
        assert f.observes("_metrics.broker.published") is True

    def test_decisions_are_cached(self):
        f = ChannelFilter(include=["alerts.**"])
        assert f.observes("alerts.temperature") is True
        assert f.observes("alerts.temperature") is True
        assert f._decisions == {"alerts.temperature": True}
