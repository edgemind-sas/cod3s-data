"""Tests for Observatory EventBuffer."""


from cod3s_data.observatory.buffer import EventBuffer, EventType, ObservatoryEvent


class TestEventBuffer:
    """Tests for the ring buffer."""

    def test_empty_buffer(self):
        buf = EventBuffer(max_size=10)
        assert buf.size == 0
        assert buf.max_size == 10
        assert buf.estimated_memory_mb == 0.0

    def test_push_and_retrieve(self):
        buf = EventBuffer(max_size=10)
        event = ObservatoryEvent(type=EventType.MESSAGE, data={"channel": "test"})
        buf.push(event)
        assert buf.size == 1
        recent = buf.get_recent(10)
        assert len(recent) == 1
        assert recent[0]["type"] == "message"
        assert recent[0]["data"]["channel"] == "test"

    def test_ring_eviction(self):
        buf = EventBuffer(max_size=3)
        for i in range(5):
            buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"i": i}))
        assert buf.size == 3
        recent = buf.get_recent(10)
        # Should have the last 3 events (i=2,3,4)
        assert [e["data"]["i"] for e in recent] == [2, 3, 4]

    def test_memory_cap_eviction(self):
        # Set a very low memory limit to force eviction
        buf = EventBuffer(max_size=1000, memory_limit_bytes=100)
        for i in range(50):
            buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"i": i}))
        # Buffer should have fewer than 50 events due to memory cap
        assert buf.size < 50

    def test_get_recent_with_type_filter(self):
        buf = EventBuffer(max_size=100)
        buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"k": "msg"}))
        buf.push(ObservatoryEvent(type=EventType.METRIC, data={"k": "met"}))
        buf.push(ObservatoryEvent(type=EventType.ERROR, data={"k": "err"}))

        msgs = buf.get_recent(10, EventType.MESSAGE)
        assert len(msgs) == 1
        assert msgs[0]["data"]["k"] == "msg"

        metrics = buf.get_recent(10, EventType.METRIC)
        assert len(metrics) == 1

    def test_get_recent_limit(self):
        buf = EventBuffer(max_size=100)
        for i in range(10):
            buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"i": i}))
        recent = buf.get_recent(3)
        assert len(recent) == 3
        # Should be the last 3
        assert [e["data"]["i"] for e in recent] == [7, 8, 9]

    def test_get_channel_messages(self):
        buf = EventBuffer(max_size=100)
        buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"channel": "a"}))
        buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"channel": "b"}))
        buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"channel": "a"}))

        a_msgs = buf.get_channel_messages("a")
        assert len(a_msgs) == 2
        b_msgs = buf.get_channel_messages("b")
        assert len(b_msgs) == 1

    def test_get_snapshot(self):
        buf = EventBuffer(max_size=100)
        buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={}))
        buf.push(ObservatoryEvent(type=EventType.METRIC, data={}))
        buf.push(ObservatoryEvent(type=EventType.ERROR, data={}))

        snapshot = buf.get_snapshot()
        assert "messages" in snapshot
        assert "metrics" in snapshot
        assert "errors" in snapshot
        assert "component_states" in snapshot
        assert "debug_events" in snapshot
        assert len(snapshot["messages"]) == 1
        assert len(snapshot["metrics"]) == 1
        assert len(snapshot["errors"]) == 1

    def test_clear(self):
        buf = EventBuffer(max_size=100)
        for _ in range(10):
            buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={}))
        assert buf.size == 10
        buf.clear()
        assert buf.size == 0
        assert buf.estimated_memory_mb == 0.0

    def test_event_to_dict(self):
        event = ObservatoryEvent(type=EventType.MESSAGE, data={"key": "value"})
        d = event.to_dict()
        assert d["type"] == "message"
        assert "timestamp" in d
        assert d["data"]["key"] == "value"

    def test_memory_tracking(self):
        buf = EventBuffer(max_size=100)
        assert buf.estimated_memory_mb == 0.0
        buf.push(ObservatoryEvent(type=EventType.MESSAGE, data={"x": "y"}))
        assert buf.estimated_memory_mb > 0.0
