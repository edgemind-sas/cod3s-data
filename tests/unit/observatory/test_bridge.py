"""Tests for Observatory Bridge."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cod3s_data.core.message import Message
from cod3s_data.observatory.bridge import ObservatoryBridge
from cod3s_data.observatory.buffer import EventBuffer, EventType
from cod3s_data.observatory.message_store import JourneyStore, MessageDetailStore
from cod3s_data.observatory.sampler import MessageSampler
from cod3s_data.observatory.websocket_manager import WebSocketManager


def _make_bridge(
    buffer: EventBuffer | None = None,
    sampler: MessageSampler | None = None,
    ws_manager: WebSocketManager | None = None,
    message_store: MessageDetailStore | None = None,
    journey_store: JourneyStore | None = None,
) -> ObservatoryBridge:
    """Create a bridge with default components for testing."""
    return ObservatoryBridge(
        event_buffer=buffer or EventBuffer(),
        sampler=sampler or MessageSampler(),
        websocket_manager=ws_manager or WebSocketManager(),
        message_store=message_store,
        journey_store=journey_store,
    )


def _make_message(**kwargs) -> Message:
    """Create a test Message."""
    defaults = {
        "key": "temperature",
        "timestamp": datetime.now(UTC),
        "value": 42.5,
        "tags": {"sensor": "TH001"},
    }
    defaults.update(kwargs)
    return Message(**defaults)


class TestObservatoryBridge:
    """Tests for the bridge hooks."""

    def test_create_bridge(self):
        bridge = _make_bridge()
        assert bridge._server is None

    @pytest.mark.asyncio
    async def test_on_message_published(self):
        buf = EventBuffer()
        bridge = _make_bridge(buffer=buf)
        await bridge.on_message_published("test_channel", object(), 3)
        assert buf.size == 1
        events = buf.get_recent(1, EventType.MESSAGE)
        assert events[0]["data"]["channel"] == "test_channel"

    @pytest.mark.asyncio
    async def test_on_message_published_sampling(self):
        buf = EventBuffer()
        sampler = MessageSampler(strategy="every_nth", rate=2)
        bridge = _make_bridge(buffer=buf, sampler=sampler)
        await bridge.on_message_published("ch", object(), 1)
        assert buf.size == 0  # First message skipped (counter=1, not divisible by 2)
        await bridge.on_message_published("ch", object(), 1)
        assert buf.size == 1  # Second message passes (counter=2)

    @pytest.mark.asyncio
    async def test_on_message_published_metrics_bypass_sampling(self):
        buf = EventBuffer()
        sampler = MessageSampler(strategy="every_nth", rate=100)
        bridge = _make_bridge(buffer=buf, sampler=sampler)
        await bridge.on_message_published("_metrics.throughput", object(), 0)
        assert buf.size == 1  # Metrics always pass

    @pytest.mark.asyncio
    async def test_on_component_state_change(self):
        buf = EventBuffer()
        bridge = _make_bridge(buffer=buf)
        await bridge.on_component_state_change("src-1", "source", "idle", "running")
        assert buf.size == 1
        events = buf.get_recent(1, EventType.COMPONENT_STATE)
        assert events[0]["data"]["component_id"] == "src-1"
        assert events[0]["data"]["new_state"] == "running"

    @pytest.mark.asyncio
    async def test_on_subscription_change(self):
        buf = EventBuffer()
        bridge = _make_bridge(buffer=buf)
        await bridge.on_subscription_change("sensor.*", "subscribe", "dest-1")
        assert buf.size == 1
        events = buf.get_recent(1, EventType.SUBSCRIPTION)
        assert events[0]["data"]["pattern"] == "sensor.*"

    @pytest.mark.asyncio
    async def test_on_metric_emitted(self):
        buf = EventBuffer()
        bridge = _make_bridge(buffer=buf)
        await bridge.on_metric_emitted("throughput", 42.0, {"component": "src-1"})
        assert buf.size == 1
        events = buf.get_recent(1, EventType.METRIC)
        assert events[0]["data"]["metric_name"] == "throughput"

    @pytest.mark.asyncio
    async def test_on_error(self):
        buf = EventBuffer()
        bridge = _make_bridge(buffer=buf)
        await bridge.on_error("src-1", RuntimeError("test"), {"phase": "emit"})
        assert buf.size == 1
        events = buf.get_recent(1, EventType.ERROR)
        assert events[0]["data"]["error_type"] == "RuntimeError"
        assert events[0]["data"]["error_message"] == "test"

    @pytest.mark.asyncio
    async def test_pause_resume_noop(self):
        bridge = _make_bridge()
        await bridge.pause_pipeline()
        await bridge.resume_pipeline()

    @pytest.mark.asyncio
    async def test_start_stop_without_server(self):
        bridge = _make_bridge()
        await bridge.start()
        await bridge.stop()


class _FakeSource:
    def __init__(self, component_id: str, channel: str, running: bool = False, label: str = ""):
        self._component_id = component_id
        self.channel = channel
        self._running = running
        self._label = label


class _FakeTransformation:
    def __init__(
        self,
        component_id: str,
        input_channels: list[str],
        output_channel: str,
        running: bool = False,
        label: str = "",
    ):
        self._component_id = component_id
        self.input_channels = input_channels
        self.output_channel = output_channel
        self._running = running
        self._label = label


class _FakeDestination:
    def __init__(
        self, component_id: str, channel_pattern: str, running: bool = False, label: str = ""
    ):
        self._component_id = component_id
        self.channel_pattern = channel_pattern
        self._running = running
        self._label = label


class _FakeFramework:
    def __init__(self, sources=None, transformations=None, destinations=None):
        self.sources = sources or []
        self.transformations = transformations or []
        self.destinations = destinations or []


class TestTopologySnapshot:
    """Tests for get_topology_snapshot()."""

    def test_no_framework(self):
        bridge = _make_bridge()
        result = bridge.get_topology_snapshot()
        assert result == {"nodes": [], "edges": []}

    def test_enriched_nodes(self):
        bridge = _make_bridge()
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "sensors.temperature")],
            transformations=[_FakeTransformation("tfm-0", ["sensors.**"], "alerts.high")],
            destinations=[_FakeDestination("dst-0", "alerts.**")],
        )
        result = bridge.get_topology_snapshot()
        nodes = result["nodes"]
        assert len(nodes) == 3

        src_node = nodes[0]
        assert src_node["component_id"] == "src-0"
        assert src_node["channels"]["publishes"] == ["sensors.temperature"]
        assert src_node["channels"]["subscribes"] == []

        tfm_node = nodes[1]
        assert tfm_node["channels"]["publishes"] == ["alerts.high"]
        assert tfm_node["channels"]["subscribes"] == ["sensors.**"]

        dst_node = nodes[2]
        assert dst_node["channels"]["publishes"] == []
        assert dst_node["channels"]["subscribes"] == ["alerts.**"]

    def test_edges_computed(self):
        bridge = _make_bridge()
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "sensors.temperature")],
            transformations=[_FakeTransformation("tfm-0", ["sensors.**"], "alerts.high")],
            destinations=[_FakeDestination("dst-0", "alerts.**")],
        )
        result = bridge.get_topology_snapshot()
        edges = result["edges"]
        assert len(edges) == 2

        # src-0 -> tfm-0 (sensors.temperature matches sensors.**)
        edge1 = edges[0]
        assert edge1["source_id"] == "src-0"
        assert edge1["target_id"] == "tfm-0"
        assert edge1["channel"] == "sensors.temperature"
        assert edge1["pattern"] == "sensors.**"

        # tfm-0 -> dst-0 (alerts.high matches alerts.**)
        edge2 = edges[1]
        assert edge2["source_id"] == "tfm-0"
        assert edge2["target_id"] == "dst-0"
        assert edge2["channel"] == "alerts.high"
        assert edge2["pattern"] == "alerts.**"

    def test_no_self_loop(self):
        bridge = _make_bridge()
        # Transformation subscribes to its own output pattern
        bridge._framework = _FakeFramework(
            transformations=[_FakeTransformation("tfm-0", ["alerts.**"], "alerts.high")],
        )
        result = bridge.get_topology_snapshot()
        edges = result["edges"]
        assert len(edges) == 0

    def test_edges_parent_child_channel(self):
        """UnpackTransform output_channel links to subscribers on sub-channels."""
        bridge = _make_bridge()
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "raw.egm")],
            transformations=[
                _FakeTransformation("tfm-unpack", ["raw.egm"], "sensors.egm"),
                _FakeTransformation(
                    "tfm-viscosity", ["sensors.egm.pressure"], "indicators.viscosity"
                ),
                _FakeTransformation(
                    "tfm-bead", ["sensors.egm.extruder_speed"], "indicators.bead_width"
                ),
            ],
            destinations=[_FakeDestination("dst-0", "sensors.**")],
        )
        result = bridge.get_topology_snapshot()
        edges = result["edges"]

        # src-0 → tfm-unpack (raw.egm exact match)
        # tfm-unpack → tfm-viscosity (sensors.egm is parent of sensors.egm.pressure)
        # tfm-unpack → tfm-bead (sensors.egm is parent of sensors.egm.extruder_speed)
        # tfm-unpack → dst-0 (sensors.egm matches sensors.**)
        edge_pairs = [(e["source_id"], e["target_id"]) for e in edges]
        assert ("src-0", "tfm-unpack") in edge_pairs
        assert ("tfm-unpack", "tfm-viscosity") in edge_pairs
        assert ("tfm-unpack", "tfm-bead") in edge_pairs
        assert ("tfm-unpack", "dst-0") in edge_pairs

    def test_parameter_edge_from_param_store(self):
        """A ParamRef consumer subscribes through its store, not input_channels."""
        bridge = _make_bridge()
        tfm = _FakeTransformation("tfm-0", ["sensors.**"], "alerts.high")
        tfm._param_stores = [
            SimpleNamespace(param_name="bounds", ref="params.consignes"),
        ]
        bridge._framework = _FakeFramework(
            sources=[
                _FakeSource("src-0", "sensors.temperature"),
                _FakeSource("src-1", "params.consignes"),
            ],
            transformations=[tfm],
        )
        result = bridge.get_topology_snapshot()

        tfm_node = next(n for n in result["nodes"] if n["component_id"] == "tfm-0")
        assert tfm_node["channels"]["parameters"] == [
            {"param": "bounds", "channel": "params.consignes"}
        ]
        # The parameter channel is not a subscription: it must not show up there.
        assert tfm_node["channels"]["subscribes"] == ["sensors.**"]

        kinds = {(e["source_id"], e["target_id"]): e for e in result["edges"]}
        assert kinds[("src-0", "tfm-0")]["kind"] == "data"
        param_edge = kinds[("src-1", "tfm-0")]
        assert param_edge["kind"] == "parameter"
        assert param_edge["param"] == "bounds"
        assert param_edge["channel"] == "params.consignes"

    def test_no_param_stores_no_parameter_edge(self):
        bridge = _make_bridge()
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "sensors.temperature")],
            transformations=[_FakeTransformation("tfm-0", ["sensors.**"], "alerts.high")],
        )
        result = bridge.get_topology_snapshot()
        assert all(e["kind"] == "data" for e in result["edges"])
        assert result["nodes"][0]["channels"]["parameters"] == []

    def test_no_match_no_edge(self):
        bridge = _make_bridge()
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "sensors.temperature")],
            destinations=[_FakeDestination("dst-0", "alerts.**")],
        )
        result = bridge.get_topology_snapshot()
        edges = result["edges"]
        assert len(edges) == 0


class TestCreateObservatory:
    """Tests for the create_observatory factory."""

    def test_create_with_defaults(self):
        from cod3s_data.observatory import create_observatory

        bridge = create_observatory()
        assert isinstance(bridge, ObservatoryBridge)
        assert bridge._server is not None

    def test_create_with_config(self):
        from cod3s_data.observatory import create_observatory
        from cod3s_data.observatory.config import ObservatoryConfig

        config = ObservatoryConfig(port=9000, buffer_size=500)
        bridge = create_observatory(config=config)
        assert isinstance(bridge, ObservatoryBridge)
        assert bridge._buffer.max_size == 500

    def test_create_injects_stores(self):
        from cod3s_data.observatory import create_observatory

        bridge = create_observatory()
        assert bridge._message_store is not None
        assert bridge._journey_store is not None


class TestMessageInspectorHooks:
    """Tests for the new message inspector hooks."""

    @pytest.mark.asyncio
    async def test_on_message_published_stores_detail(self):
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)
        msg = _make_message()
        await bridge.on_message_published("sensors.temp", msg, 2)

        msg_id = str(msg.id)
        detail = ms.get(msg_id)
        assert detail is not None
        assert detail["channel"] == "sensors.temp"
        assert detail["subscriber_count"] == 2
        assert detail["key"] == "temperature"
        assert detail["trace_id"] == msg_id

    @pytest.mark.asyncio
    async def test_on_message_published_records_journey_step(self):
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)
        msg = _make_message()
        await bridge.on_message_published("sensors.temp", msg, 1)

        trace_id = str(msg.id)
        journey = js.get_journey(trace_id)
        assert journey is not None
        assert len(journey) == 1
        assert journey[0]["stage"] == "PUBLISHED"
        assert journey[0]["channel"] == "sensors.temp"

    @pytest.mark.asyncio
    async def test_on_message_published_includes_message_id(self):
        buf = EventBuffer()
        bridge = _make_bridge(buffer=buf)
        msg = _make_message()
        await bridge.on_message_published("ch", msg, 1)
        events = buf.get_recent(1, EventType.MESSAGE)
        assert events[0]["data"]["message_id"] == str(msg.id)

    @pytest.mark.asyncio
    async def test_on_message_received_records_received(self):
        js = JourneyStore()
        bridge = _make_bridge(journey_store=js)
        msg = _make_message()
        # Seed the trace_id
        bridge._set_trace_id(str(msg.id), "trace-abc")
        await bridge.on_message_received("tfm-0", "transformation", msg)

        journey = js.get_journey("trace-abc")
        assert journey is not None
        assert len(journey) == 1
        assert journey[0]["stage"] == "RECEIVED"
        assert journey[0]["component_id"] == "tfm-0"

    @pytest.mark.asyncio
    async def test_on_message_received_records_delivered_for_destination(self):
        js = JourneyStore()
        bridge = _make_bridge(journey_store=js)
        msg = _make_message()
        bridge._set_trace_id(str(msg.id), "trace-xyz")
        await bridge.on_message_received("dst-0", "destination", msg)

        journey = js.get_journey("trace-xyz")
        assert journey[0]["stage"] == "DELIVERED"

    @pytest.mark.asyncio
    async def test_on_message_received_noop_without_journey_store(self):
        bridge = _make_bridge()  # No journey_store
        msg = _make_message()
        await bridge.on_message_received("tfm-0", "transformation", msg)
        # Should not raise

    @pytest.mark.asyncio
    async def test_on_message_processed_records_step_and_links_outputs(self):
        js = JourneyStore()
        bridge = _make_bridge(journey_store=js)
        input_msg = _make_message(key="input")
        output_msg = _make_message(key="output")

        input_id = str(input_msg.id)
        output_id = str(output_msg.id)
        bridge._set_trace_id(input_id, "trace-main")

        await bridge.on_message_processed(
            "tfm-0", "transformation", input_msg, [output_msg], "alerts.high"
        )

        # Check journey step
        journey = js.get_journey("trace-main")
        assert journey is not None
        assert len(journey) == 1
        assert journey[0]["stage"] == "PROCESSED"
        assert journey[0]["channel"] == "alerts.high"

        # Check output message is linked to same trace
        assert bridge._trace_ids[output_id] == "trace-main"

    @pytest.mark.asyncio
    async def test_get_message_detail_with_journey(self):
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)
        msg = _make_message()
        await bridge.on_message_published("sensors.temp", msg, 3)

        detail = bridge.get_message_detail(str(msg.id))
        assert detail is not None
        assert detail["channel"] == "sensors.temp"
        assert "journey" in detail
        assert len(detail["journey"]) == 1
        assert detail["journey"][0]["stage"] == "PUBLISHED"

    def test_get_message_detail_not_found(self):
        ms = MessageDetailStore()
        bridge = _make_bridge(message_store=ms)
        assert bridge.get_message_detail("nonexistent") is None

    def test_get_message_detail_without_store(self):
        bridge = _make_bridge()
        assert bridge.get_message_detail("any-id") is None

    @pytest.mark.asyncio
    async def test_trace_id_linking_across_chain(self):
        """Test that trace_id propagates: source -> transform -> destination."""
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)

        # Source publishes
        src_msg = _make_message(key="raw")
        await bridge.on_message_published("sensors.raw", src_msg, 1)
        trace_id = str(src_msg.id)

        # Transform receives
        await bridge.on_message_received("tfm-0", "transformation", src_msg)

        # Transform produces output
        out_msg = _make_message(key="processed")
        await bridge.on_message_processed(
            "tfm-0", "transformation", src_msg, [out_msg], "sensors.processed"
        )

        # Output published
        await bridge.on_message_published("sensors.processed", out_msg, 1)

        # Destination receives
        await bridge.on_message_received("dst-0", "destination", out_msg)

        # Full journey via original trace_id
        journey = js.get_journey(trace_id)
        assert journey is not None
        stages = [s["stage"] for s in journey]
        assert stages == ["PUBLISHED", "RECEIVED", "PROCESSED", "PUBLISHED", "DELIVERED"]

    @pytest.mark.asyncio
    async def test_journey_labels_with_framework(self):
        """Journey steps should include component labels when framework is connected."""
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "sensors.raw", label="Temp Sensor")],
            transformations=[
                _FakeTransformation("tfm-0", ["sensors.**"], "alerts.high", label="Alert Filter")
            ],
            destinations=[_FakeDestination("dst-0", "alerts.**", label="Alert Logger")],
        )

        msg = _make_message(key="raw")
        await bridge.on_message_published("sensors.raw", msg, 1)
        trace_id = str(msg.id)

        await bridge.on_message_received("tfm-0", "transformation", msg)

        journey = js.get_journey(trace_id)
        assert journey is not None
        # PUBLISHED step should resolve the source
        assert journey[0]["component_id"] == "src-0"
        assert journey[0]["component_type"] == "source"
        assert journey[0]["label"] == "Temp Sensor"
        # RECEIVED step should have the transformation label
        assert journey[1]["component_id"] == "tfm-0"
        assert journey[1]["label"] == "Alert Filter"

    @pytest.mark.asyncio
    async def test_journey_message_ids_linear(self):
        """Each journey step should carry message_id and parent_message_id."""
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)

        src_msg = _make_message(key="raw")
        src_id = str(src_msg.id)
        await bridge.on_message_published("ch", src_msg, 1)

        journey = js.get_journey(src_id)
        # Root message: message_id set, parent_message_id empty
        assert journey[0]["message_id"] == src_id
        assert journey[0]["parent_message_id"] == ""

    @pytest.mark.asyncio
    async def test_journey_fan_out_tree(self):
        """Fan-out: one message received by two transforms, each producing output."""
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)

        # Source publishes msg-A on sensors.raw
        msg_a = _make_message(key="raw")
        msg_a_id = str(msg_a.id)
        await bridge.on_message_published("sensors.raw", msg_a, 2)
        trace_id = msg_a_id

        # Two transforms receive msg-A
        await bridge.on_message_received("tfm-0", "transformation", msg_a)
        await bridge.on_message_received("tfm-1", "transformation", msg_a)

        # tfm-0 produces msg-B
        msg_b = _make_message(key="alerts")
        msg_b_id = str(msg_b.id)
        await bridge.on_message_processed("tfm-0", "transformation", msg_a, [msg_b], "alerts.high")

        # tfm-1 produces msg-C
        msg_c = _make_message(key="logs")
        msg_c_id = str(msg_c.id)
        await bridge.on_message_processed("tfm-1", "transformation", msg_a, [msg_c], "logs.raw")

        # msg-B and msg-C are published
        await bridge.on_message_published("alerts.high", msg_b, 1)
        await bridge.on_message_published("logs.raw", msg_c, 1)

        # Destinations receive
        await bridge.on_message_received("dst-0", "destination", msg_b)
        await bridge.on_message_received("dst-1", "destination", msg_c)

        # All steps are on the same trace
        journey = js.get_journey(trace_id)
        assert journey is not None

        # Verify parent_message_id linking
        # msg-A steps: no parent
        a_steps = [s for s in journey if s["message_id"] == msg_a_id]
        for step in a_steps:
            assert step["parent_message_id"] == ""

        # msg-B steps: parent is msg-A
        b_steps = [s for s in journey if s["message_id"] == msg_b_id]
        assert len(b_steps) >= 1
        for step in b_steps:
            assert step["parent_message_id"] == msg_a_id

        # msg-C steps: parent is msg-A
        c_steps = [s for s in journey if s["message_id"] == msg_c_id]
        assert len(c_steps) >= 1
        for step in c_steps:
            assert step["parent_message_id"] == msg_a_id

        # Verify we have the full set of stages
        stages = [s["stage"] for s in journey]
        assert stages.count("PUBLISHED") == 3  # msg-A, msg-B, msg-C
        assert stages.count("RECEIVED") == 2  # tfm-0, tfm-1
        assert stages.count("PROCESSED") == 2  # tfm-0, tfm-1
        assert stages.count("DELIVERED") == 2  # dst-0, dst-1

    @pytest.mark.asyncio
    async def test_receive_channel_resolved_via_topology(self):
        """RECEIVED/DELIVERED steps should carry the channel they received on,
        resolved via the framework topology (subscription patterns).

        This is the real-world case where with_value() preserves the message UUID,
        so all steps have the same message_id. Without channel info, the frontend
        cannot build the correct branching tree.
        """
        ms = MessageDetailStore()
        js = JourneyStore()
        bridge = _make_bridge(message_store=ms, journey_store=js)
        bridge._framework = _FakeFramework(
            sources=[
                _FakeSource("src-0", "sensors.temperature.room1", label="Capteur Température")
            ],
            transformations=[
                _FakeTransformation(
                    "tfm-0",
                    ["sensors.temperature.**"],
                    "alerts.high_temp",
                    label="Alerte haute temp",
                ),
                _FakeTransformation(
                    "tfm-1",
                    ["sensors.temperature.**"],
                    "stats.temperature.avg",
                    label="Moyenne Température",
                ),
            ],
            destinations=[
                _FakeDestination("dst-0", "sensors.**", label="Log Capteurs"),
                _FakeDestination("dst-1", "alerts.**", label="Log Alertes"),
                _FakeDestination("dst-2", "stats.**", label="Log Statistiques"),
            ],
        )

        # Source publishes a message (same UUID used throughout via with_value)
        msg = _make_message(key="random_value")
        msg_id = str(msg.id)
        trace_id = msg_id

        # 1. Source publishes on sensors.temperature.room1
        await bridge.on_message_published("sensors.temperature.room1", msg, 3)

        # 2. dst-0 receives (subscriber of sensors.**)
        await bridge.on_message_received("dst-0", "destination", msg)
        # 3. tfm-0 receives (subscriber of sensors.temperature.**)
        await bridge.on_message_received("tfm-0", "transformation", msg)
        # 4. tfm-0 processes and produces output (same msg id via with_value)
        await bridge.on_message_processed("tfm-0", "transformation", msg, [msg], "alerts.high_temp")
        # 5. tfm-0's output published on alerts.high_temp
        await bridge.on_message_published("alerts.high_temp", msg, 1)
        # 6. tfm-1 receives (subscriber of sensors.temperature.**)
        await bridge.on_message_received("tfm-1", "transformation", msg)
        # 7. dst-1 receives (subscriber of alerts.**)
        await bridge.on_message_received("dst-1", "destination", msg)

        journey = js.get_journey(trace_id)
        assert journey is not None
        assert len(journey) == 7

        # Verify channel resolution
        # Step 0: PUBLISHED on sensors.temperature.room1
        assert journey[0]["stage"] == "PUBLISHED"
        assert journey[0]["channel"] == "sensors.temperature.room1"

        # Step 1: DELIVERED dst-0 should be on sensors.temperature.room1
        assert journey[1]["stage"] == "DELIVERED"
        assert journey[1]["component_id"] == "dst-0"
        assert journey[1]["channel"] == "sensors.temperature.room1"

        # Step 2: RECEIVED tfm-0 should be on sensors.temperature.room1
        assert journey[2]["stage"] == "RECEIVED"
        assert journey[2]["component_id"] == "tfm-0"
        assert journey[2]["channel"] == "sensors.temperature.room1"

        # Step 3: PROCESSED tfm-0 (output channel)
        assert journey[3]["stage"] == "PROCESSED"
        assert journey[3]["channel"] == "alerts.high_temp"

        # Step 4: PUBLISHED on alerts.high_temp
        assert journey[4]["stage"] == "PUBLISHED"
        assert journey[4]["channel"] == "alerts.high_temp"

        # Step 5: RECEIVED tfm-1 should be on sensors.temperature.room1
        assert journey[5]["stage"] == "RECEIVED"
        assert journey[5]["component_id"] == "tfm-1"
        assert journey[5]["channel"] == "sensors.temperature.room1"

        # Step 6: DELIVERED dst-1 should be on alerts.high_temp
        assert journey[6]["stage"] == "DELIVERED"
        assert journey[6]["component_id"] == "dst-1"
        assert journey[6]["channel"] == "alerts.high_temp"


class TestParamEventsDoNotCorruptTopology:
    """A ParamRef rebind must not erase the component's node.

    on_param_updated used to push its event as EventType.COMPONENT_STATE, but
    its payload has no component_type or new_state. /api/topology keeps the
    latest COMPONENT_STATE event per component id, so every component holding a
    ParamRef came back as unknown/unknown.
    """

    async def test_param_update_is_not_a_component_state_event(self):
        buffer = EventBuffer(max_size=100)
        bridge = _make_bridge(buffer=buffer)

        await bridge.on_component_state_change("tfm-0", "transformation", "created", "running")
        await bridge.on_param_updated(
            "tfm-0", "setpoint", 200.0, 215.0, channel="params.extruder.setpoint"
        )

        states = buffer.get_recent(50, EventType.COMPONENT_STATE)
        assert len(states) == 1
        assert states[0]["data"]["component_type"] == "transformation"
        assert states[0]["data"]["new_state"] == "running"

        params = buffer.get_recent(50, EventType.PARAM)
        assert len(params) == 1
        assert params[0]["data"]["param_name"] == "setpoint"
        assert params[0]["data"]["new_value"] == 215.0

    async def test_topology_route_keeps_the_component_after_a_param_update(self):
        """Exercise the route function directly: TestClient would need httpx."""
        from types import SimpleNamespace

        from cod3s_data.observatory.routes.topology import get_component, get_topology

        buffer = EventBuffer(max_size=100)
        bridge = _make_bridge(buffer=buffer)

        await bridge.on_component_state_change("tfm-0", "transformation", "created", "running")
        await bridge.on_param_updated("tfm-0", "setpoint", 200.0, 215.0)

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(buffer=buffer)))

        topology = await get_topology(request)
        assert topology["nodes"] == [{"id": "tfm-0", "type": "transformation", "state": "running"}]

        detail = await get_component("tfm-0", request)
        assert detail == {"id": "tfm-0", "type": "transformation", "state": "running"}


class TestReceiveChannelPerMessage:
    """A component receiving several channels of one trace must not conflate them.

    `_find_receive_channel` used to match the component's subscription patterns
    against the trace's published channels and return the first hit, ignoring
    which message was actually received. An `unpack` that fans one reading out
    into six sensor channels therefore reported all six receptions on the first
    channel — and the Inspector drew the five others as childless publications.
    """

    async def test_six_channels_are_not_conflated(self):
        js = JourneyStore()
        bridge = _make_bridge(journey_store=js)
        keys = [
            "temperature_top",
            "temperature_bottom",
            "temperature_nozzle_1",
            "temperature_nozzle_2",
            "vitesse_extrudeur",
            "pressure",
        ]
        channels = [f"sensors.egm.{key}" for key in keys]
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "raw.egm")],
            transformations=[
                _FakeTransformation("tfm-unpack", ["raw.egm"], "sensors.egm"),
                _FakeTransformation("tfm-avg", channels, "sensors.smoothed"),
            ],
        )

        # The source message fans out into one message per sensor, all sharing
        # the trace of the reading they came from.
        root = _make_message(key="egm_reading")
        await bridge.on_message_published("raw.egm", root, 1)
        await bridge.on_message_received("tfm-unpack", "transformation", root)
        unpacked = [_make_message(key=key) for key in keys]
        await bridge.on_message_processed(
            "tfm-unpack", "transformation", root, unpacked, "sensors.egm"
        )
        for channel, message in zip(channels, unpacked, strict=True):
            await bridge.on_message_published(channel, message, 1)
        for message in unpacked:
            await bridge.on_message_received("tfm-avg", "transformation", message)

        journey = js.get_journey(str(root.id))
        assert journey is not None
        received = [
            s for s in journey if s["stage"] == "RECEIVED" and s["component_id"] == "tfm-avg"
        ]
        assert len(received) == 6
        # Each reception reports the channel its own message was published on.
        assert [s["channel"] for s in received] == channels
        # And every step still names the message it is about, so the Inspector
        # can rebuild the tree from parentage rather than from channels.
        assert [s["message_id"] for s in received] == [str(m.id) for m in unpacked]
        assert {s["parent_message_id"] for s in received} == {str(root.id)}


class TestObservedAt:
    """The detail carries the pipeline's clock alongside the source's.

    The table and the Timeline plot when the Observatory saw a message; the
    Summary tab used to show the source's timestamp instead. On a live pipeline
    the two agree and nothing showed; replaying a recorded session with its
    original timestamps put months between the row and the panel it opened.
    """

    async def test_detail_carries_both_clocks(self):
        store = MessageDetailStore()
        bridge = _make_bridge(message_store=store, journey_store=JourneyStore())
        recorded = datetime(2026, 2, 26, 13, 54, 30, tzinfo=UTC)
        message = _make_message(timestamp=recorded)

        await bridge.on_message_published("sensors.temperature", message, 1)

        detail = bridge.get_message_detail(str(message.id))
        assert detail is not None
        # The source's own time is untouched — Grafana indexes on it.
        assert detail["timestamp"].startswith("2026-02-26T13:54:30")
        # And the publication is stamped with the Observatory's clock, not it.
        assert detail["observed_at"]
        assert not detail["observed_at"].startswith("2026-02-26T13:54:30")


class TestSamplingIsCoherent:
    """A skipped publication skips its receptions too.

    Only `on_message_published` consulted the sampler. Receptions and processing
    steps were recorded whatever it decided, so a sampled run cost the same work
    on the hooks that matter most and produced journeys holding receptions whose
    publication was missing — the Inspector then had to invent a parent.
    """

    async def test_unsampled_message_records_no_journey(self):
        js = JourneyStore()
        # `every_nth` at 2: the first publication is skipped, the second kept.
        bridge = _make_bridge(
            sampler=MessageSampler(strategy="every_nth", rate=2), journey_store=js
        )
        bridge._framework = _FakeFramework(
            sources=[_FakeSource("src-0", "sensors.temperature")],
            transformations=[_FakeTransformation("tfm-0", ["sensors.**"], "alerts.high")],
        )

        skipped = _make_message()
        await bridge.on_message_published("sensors.temperature", skipped, 1)
        await bridge.on_message_received("tfm-0", "transformation", skipped)
        assert js.get_journey(str(skipped.id)) is None

        kept = _make_message()
        await bridge.on_message_published("sensors.temperature", kept, 1)
        await bridge.on_message_received("tfm-0", "transformation", kept)
        journey = js.get_journey(str(kept.id))
        assert journey is not None
        assert [s["stage"] for s in journey] == ["PUBLISHED", "RECEIVED"]
