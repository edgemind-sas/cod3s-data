"""Tests for Observatory Bridge."""

import pytest

from cod3s_data.observatory.bridge import ObservatoryBridge
from cod3s_data.observatory.buffer import EventBuffer, EventType
from cod3s_data.observatory.sampler import MessageSampler
from cod3s_data.observatory.websocket_manager import WebSocketManager


def _make_bridge(
    buffer: EventBuffer | None = None,
    sampler: MessageSampler | None = None,
    ws_manager: WebSocketManager | None = None,
) -> ObservatoryBridge:
    """Create a bridge with default components for testing."""
    return ObservatoryBridge(
        event_buffer=buffer or EventBuffer(),
        sampler=sampler or MessageSampler(),
        websocket_manager=ws_manager or WebSocketManager(),
    )


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
    def __init__(self, component_id: str, input_channels: list[str], output_channel: str, running: bool = False, label: str = ""):
        self._component_id = component_id
        self.input_channels = input_channels
        self.output_channel = output_channel
        self._running = running
        self._label = label


class _FakeDestination:
    def __init__(self, component_id: str, channel_pattern: str, running: bool = False, label: str = ""):
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
