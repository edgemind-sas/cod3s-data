"""Unit tests for SubscriptionRegistry."""

import pytest

from cod3s_data.core.message import Message
from cod3s_data.core.subscription_registry import SubscriptionRegistry


class TestExactMatches:
    """Test exact channel matching."""

    @pytest.mark.asyncio
    async def test_exact_match_single_subscriber(self):
        """Test exact match with single subscriber."""
        registry = SubscriptionRegistry()
        received = []

        async def callback(msg: Message):
            received.append(msg)

        registry.add_subscription("sensors.temp", callback)

        # Match exact channel
        callbacks = registry.match_channel("sensors.temp")
        assert len(callbacks) == 1
        assert callbacks[0] == callback

        # No match for different channel
        callbacks = registry.match_channel("sensors.pressure")
        assert len(callbacks) == 0

    @pytest.mark.asyncio
    async def test_exact_match_multiple_subscribers(self):
        """Test exact match with multiple subscribers."""
        registry = SubscriptionRegistry()

        async def callback1(msg: Message):
            pass

        async def callback2(msg: Message):
            pass

        registry.add_subscription("sensors.temp", callback1)
        registry.add_subscription("sensors.temp", callback2)

        # Both callbacks should match
        callbacks = registry.match_channel("sensors.temp")
        assert len(callbacks) == 2
        assert callback1 in callbacks
        assert callback2 in callbacks


class TestSingleLevelWildcards:
    """Test single-level wildcard matching (*)."""

    @pytest.mark.asyncio
    async def test_single_wildcard_match(self):
        """Test single-level wildcard matching."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("sensors.*.temp", callback)

        # Should match
        assert len(registry.match_channel("sensors.printer1.temp")) == 1
        assert len(registry.match_channel("sensors.printer2.temp")) == 1
        assert len(registry.match_channel("sensors.extruder.temp")) == 1

        # Should not match (wrong number of levels)
        assert len(registry.match_channel("sensors.temp")) == 0
        assert len(registry.match_channel("sensors.printer1.zone1.temp")) == 0

        # Should not match (different suffix)
        assert len(registry.match_channel("sensors.printer1.pressure")) == 0

    @pytest.mark.asyncio
    async def test_multiple_single_wildcards(self):
        """Test pattern with multiple single-level wildcards."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("*.*.temp", callback)

        # Should match
        assert len(registry.match_channel("sensors.printer1.temp")) == 1
        assert len(registry.match_channel("devices.extruder.temp")) == 1

        # Should not match (wrong number of levels)
        assert len(registry.match_channel("sensors.temp")) == 0
        assert len(registry.match_channel("a.b.c.temp")) == 0


class TestMultiLevelWildcards:
    """Test multi-level wildcard matching (**)."""

    @pytest.mark.asyncio
    async def test_multi_wildcard_suffix(self):
        """Test multi-level wildcard at end."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("sensors.**", callback)

        # Should match (any suffix)
        assert len(registry.match_channel("sensors.temp")) == 1
        assert len(registry.match_channel("sensors.printer1.temp")) == 1
        assert len(registry.match_channel("sensors.printer1.zone1.temp")) == 1

        # Should not match (different prefix)
        assert len(registry.match_channel("alerts.temp")) == 0
        assert len(registry.match_channel("other.sensors.temp")) == 0

    @pytest.mark.asyncio
    async def test_multi_wildcard_prefix(self):
        """Test multi-level wildcard at beginning."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("**.temp", callback)

        # Should match (any prefix)
        assert len(registry.match_channel("temp")) == 1
        assert len(registry.match_channel("sensors.temp")) == 1
        assert len(registry.match_channel("sensors.printer1.temp")) == 1

        # Should not match (different suffix)
        assert len(registry.match_channel("sensors.pressure")) == 0

    @pytest.mark.asyncio
    async def test_multi_wildcard_middle(self):
        """Test multi-level wildcard in middle."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("sensors.**.temp", callback)

        # Should match
        assert len(registry.match_channel("sensors.temp")) == 1
        assert len(registry.match_channel("sensors.printer1.temp")) == 1
        assert len(registry.match_channel("sensors.printer1.zone1.temp")) == 1


class TestCombinedPatterns:
    """Test combined exact and wildcard patterns."""

    @pytest.mark.asyncio
    async def test_exact_and_wildcard_both_match(self):
        """Test that both exact and wildcard matches are returned."""
        registry = SubscriptionRegistry()

        async def exact_callback(msg: Message):
            pass

        async def wildcard_callback(msg: Message):
            pass

        registry.add_subscription("sensors.printer1.temp", exact_callback)
        registry.add_subscription("sensors.*.temp", wildcard_callback)

        # Both should match
        callbacks = registry.match_channel("sensors.printer1.temp")
        assert len(callbacks) == 2
        assert exact_callback in callbacks
        assert wildcard_callback in callbacks

    @pytest.mark.asyncio
    async def test_multiple_wildcard_patterns(self):
        """Test multiple wildcard patterns matching same channel."""
        registry = SubscriptionRegistry()

        async def callback1(msg: Message):
            pass

        async def callback2(msg: Message):
            pass

        async def callback3(msg: Message):
            pass

        registry.add_subscription("sensors.*.temp", callback1)
        registry.add_subscription("sensors.**", callback2)
        registry.add_subscription("**.temp", callback3)

        # All three should match
        callbacks = registry.match_channel("sensors.printer1.temp")
        assert len(callbacks) == 3
        assert callback1 in callbacks
        assert callback2 in callbacks
        assert callback3 in callbacks


class TestRemoveSubscription:
    """Test subscription removal."""

    @pytest.mark.asyncio
    async def test_remove_exact_subscription(self):
        """Test removing exact subscription."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("sensors.temp", callback)
        assert len(registry.match_channel("sensors.temp")) == 1

        registry.remove_subscription("sensors.temp", callback)
        assert len(registry.match_channel("sensors.temp")) == 0

    @pytest.mark.asyncio
    async def test_remove_wildcard_subscription(self):
        """Test removing wildcard subscription."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("sensors.*.temp", callback)
        assert len(registry.match_channel("sensors.printer1.temp")) == 1

        registry.remove_subscription("sensors.*.temp", callback)
        assert len(registry.match_channel("sensors.printer1.temp")) == 0

    @pytest.mark.asyncio
    async def test_remove_one_of_multiple(self):
        """Test removing one of multiple subscriptions."""
        registry = SubscriptionRegistry()

        async def callback1(msg: Message):
            pass

        async def callback2(msg: Message):
            pass

        registry.add_subscription("sensors.temp", callback1)
        registry.add_subscription("sensors.temp", callback2)

        registry.remove_subscription("sensors.temp", callback1)

        callbacks = registry.match_channel("sensors.temp")
        assert len(callbacks) == 1
        assert callbacks[0] == callback2

    @pytest.mark.asyncio
    async def test_remove_nonexistent_subscription(self):
        """Test that removing nonexistent subscription doesn't error."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        # Should not raise error
        registry.remove_subscription("sensors.temp", callback)


class TestUtilityMethods:
    """Test utility methods."""

    @pytest.mark.asyncio
    async def test_count_subscriptions(self):
        """Test counting total subscriptions."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        assert registry.count_subscriptions() == 0

        registry.add_subscription("sensors.temp", callback)
        assert registry.count_subscriptions() == 1

        registry.add_subscription("sensors.pressure", callback)
        assert registry.count_subscriptions() == 2

        registry.add_subscription("sensors.*.temp", callback)
        assert registry.count_subscriptions() == 3

    @pytest.mark.asyncio
    async def test_get_all_patterns(self):
        """Test getting all registered patterns."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("sensors.temp", callback)
        registry.add_subscription("sensors.*.temp", callback)
        registry.add_subscription("alerts.**", callback)

        patterns = registry.get_all_patterns()
        assert len(patterns) == 3
        assert "sensors.temp" in patterns


class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_exact_match_is_fast(self):
        """Test that exact matches are O(1)."""
        import time

        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        # Add many subscriptions
        for i in range(1000):
            registry.add_subscription(f"channel{i}", callback)

        # Exact match should be fast regardless of registry size
        start = time.perf_counter()
        for _ in range(1000):
            registry.match_channel("channel500")
        elapsed = time.perf_counter() - start

        # Should be very fast (< 20ms for 1000 lookups)
        assert elapsed < 0.02

    @pytest.mark.asyncio
    async def test_wildcard_scales_with_patterns(self):
        """Test wildcard matching performance."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        # Add wildcard subscriptions
        for i in range(100):
            registry.add_subscription(f"channel{i}.*", callback)

        # Should still be reasonably fast
        callbacks = registry.match_channel("channel50.temp")
        assert len(callbacks) == 1


class TestStaticMatches:
    """Test the static matches() method."""

    def test_exact_match(self):
        assert SubscriptionRegistry.matches("sensors.temp", "sensors.temp") is True
        assert SubscriptionRegistry.matches("sensors.temp", "sensors.pressure") is False

    def test_single_wildcard(self):
        assert SubscriptionRegistry.matches("sensors.*.temp", "sensors.printer1.temp") is True
        assert SubscriptionRegistry.matches("sensors.*.temp", "sensors.temp") is False
        assert SubscriptionRegistry.matches("sensors.*.temp", "sensors.a.b.temp") is False

    def test_multi_wildcard_suffix(self):
        assert SubscriptionRegistry.matches("sensors.**", "sensors.temp") is True
        assert SubscriptionRegistry.matches("sensors.**", "sensors.a.b.c") is True
        assert SubscriptionRegistry.matches("sensors.**", "alerts.temp") is False

    def test_multi_wildcard_prefix(self):
        assert SubscriptionRegistry.matches("**.temp", "temp") is True
        assert SubscriptionRegistry.matches("**.temp", "sensors.temp") is True
        assert SubscriptionRegistry.matches("**.temp", "a.b.temp") is True
        assert SubscriptionRegistry.matches("**.temp", "sensors.pressure") is False

    def test_multi_wildcard_middle(self):
        assert SubscriptionRegistry.matches("sensors.**.temp", "sensors.temp") is True
        assert SubscriptionRegistry.matches("sensors.**.temp", "sensors.a.temp") is True
        assert SubscriptionRegistry.matches("sensors.**.temp", "sensors.a.b.temp") is True


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_empty_registry(self):
        """Test matching on empty registry."""
        registry = SubscriptionRegistry()

        callbacks = registry.match_channel("any.channel")
        assert len(callbacks) == 0

    @pytest.mark.asyncio
    async def test_channel_with_dots(self):
        """Test channel names with multiple dots."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("a.b.c.d.e", callback)

        assert len(registry.match_channel("a.b.c.d.e")) == 1
        assert len(registry.match_channel("a.b.c.d.f")) == 0

    @pytest.mark.asyncio
    async def test_single_level_channel(self):
        """Test single-level channel names."""
        registry = SubscriptionRegistry()

        async def callback(msg: Message):
            pass

        registry.add_subscription("temp", callback)

        assert len(registry.match_channel("temp")) == 1
        assert len(registry.match_channel("pressure")) == 0
