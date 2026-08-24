"""Tests for MessageDetailStore and JourneyStore."""


from cod3s_data.observatory.message_store import (
    JourneyStep,
    JourneyStore,
    MessageDetailStore,
)


class TestMessageDetailStore:
    """Tests for the LRU message detail cache."""

    def test_store_and_retrieve(self):
        store = MessageDetailStore(max_entries=10)
        store.store("msg-1", "sensors.temp", {"key": "temp", "value": 42}, 3, "trace-1")
        result = store.get("msg-1")
        assert result is not None
        assert result["message_id"] == "msg-1"
        assert result["channel"] == "sensors.temp"
        assert result["trace_id"] == "trace-1"
        assert result["subscriber_count"] == 3
        assert result["key"] == "temp"
        assert result["value"] == 42

    def test_get_missing_key(self):
        store = MessageDetailStore()
        assert store.get("nonexistent") is None

    def test_lru_eviction(self):
        store = MessageDetailStore(max_entries=3)
        store.store("msg-1", "ch", {}, 1, "t-1")
        store.store("msg-2", "ch", {}, 1, "t-2")
        store.store("msg-3", "ch", {}, 1, "t-3")
        assert store.size == 3

        # Adding a 4th should evict msg-1 (oldest)
        store.store("msg-4", "ch", {}, 1, "t-4")
        assert store.size == 3
        assert store.get("msg-1") is None
        assert store.get("msg-2") is not None

    def test_lru_access_updates_order(self):
        store = MessageDetailStore(max_entries=3)
        store.store("msg-1", "ch", {}, 1, "t-1")
        store.store("msg-2", "ch", {}, 1, "t-2")
        store.store("msg-3", "ch", {}, 1, "t-3")

        # Access msg-1, making msg-2 the oldest
        store.get("msg-1")

        store.store("msg-4", "ch", {}, 1, "t-4")
        assert store.get("msg-2") is None  # msg-2 evicted
        assert store.get("msg-1") is not None  # msg-1 still present

    def test_update_existing_entry(self):
        store = MessageDetailStore(max_entries=10)
        store.store("msg-1", "ch1", {"value": 1}, 1, "t-1")
        store.store("msg-1", "ch2", {"value": 2}, 2, "t-1")
        assert store.size == 1
        result = store.get("msg-1")
        assert result["channel"] == "ch2"
        assert result["value"] == 2

    def test_size_property(self):
        store = MessageDetailStore()
        assert store.size == 0
        store.store("msg-1", "ch", {}, 1, "t-1")
        assert store.size == 1


class TestJourneyStore:
    """Tests for the journey tracking store."""

    def test_add_and_retrieve_step(self):
        store = JourneyStore(max_entries=10)
        step = JourneyStep(
            stage="PUBLISHED",
            component_id="src-0",
            component_type="source",
            channel="sensors.temp",
        )
        store.add_step("trace-1", step)
        journey = store.get_journey("trace-1")
        assert journey is not None
        assert len(journey) == 1
        assert journey[0]["stage"] == "PUBLISHED"
        assert journey[0]["component_id"] == "src-0"

    def test_multiple_steps_same_trace(self):
        store = JourneyStore()
        store.add_step("trace-1", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        store.add_step("trace-1", JourneyStep("RECEIVED", "tfm-0", "transformation", "ch"))
        store.add_step("trace-1", JourneyStep("PROCESSED", "tfm-0", "transformation", "ch"))
        journey = store.get_journey("trace-1")
        assert len(journey) == 3
        assert [s["stage"] for s in journey] == ["PUBLISHED", "RECEIVED", "PROCESSED"]

    def test_get_missing_trace(self):
        store = JourneyStore()
        assert store.get_journey("nonexistent") is None

    def test_lru_eviction(self):
        store = JourneyStore(max_entries=2)
        store.add_step("trace-1", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        store.add_step("trace-2", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        assert store.size == 2

        # Adding trace-3 should evict trace-1
        store.add_step("trace-3", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        assert store.size == 2
        assert store.get_journey("trace-1") is None
        assert store.get_journey("trace-2") is not None

    def test_lru_access_updates_order(self):
        store = JourneyStore(max_entries=2)
        store.add_step("trace-1", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        store.add_step("trace-2", JourneyStep("PUBLISHED", "src-0", "source", "ch"))

        # Access trace-1, making trace-2 the oldest
        store.add_step("trace-1", JourneyStep("RECEIVED", "tfm-0", "transformation", "ch"))

        store.add_step("trace-3", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        assert store.get_journey("trace-2") is None
        assert store.get_journey("trace-1") is not None

    def test_size_property(self):
        store = JourneyStore()
        assert store.size == 0
        store.add_step("trace-1", JourneyStep("PUBLISHED", "src-0", "source", "ch"))
        assert store.size == 1

    def test_journey_step_to_dict(self):
        step = JourneyStep(
            stage="DELIVERED",
            component_id="dst-0",
            component_type="destination",
            channel="alerts.high",
            message_id="msg-1",
            parent_message_id="msg-0",
            label="Alert Dest",
            timestamp="2024-01-01T00:00:00Z",
        )
        d = step.to_dict()
        assert d["stage"] == "DELIVERED"
        assert d["component_id"] == "dst-0"
        assert d["component_type"] == "destination"
        assert d["channel"] == "alerts.high"
        assert d["message_id"] == "msg-1"
        assert d["parent_message_id"] == "msg-0"
        assert d["label"] == "Alert Dest"
        assert d["timestamp"] == "2024-01-01T00:00:00Z"
