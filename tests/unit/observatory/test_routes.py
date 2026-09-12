"""Tests for the Observatory REST surface.

This is what the frontend and any third-party script consume, so the
assertions are about the response bodies rather than about internal calls.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cod3s_data.framework import Framework
from cod3s_data.observatory.bridge import ObservatoryBridge

from .conftest import PARAM_CHANNEL, make_message


async def _seed_topology(bridge: ObservatoryBridge) -> None:
    """Record the component states and subscriptions a running pipeline emits."""
    await bridge.on_component_state_change("src-0", "source", "idle", "running")
    await bridge.on_component_state_change("tfm-0", "transformation", "idle", "running")
    await bridge.on_component_state_change("dst-0", "destination", "idle", "running")
    await bridge.on_subscription_change("sensors.*", "subscribe", "tfm-0")
    await bridge.on_subscription_change("retired.*", "unsubscribe", "tfm-0")


class TestHealth:
    async def test_reports_buffer_and_client_counts(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        await bridge.on_message_published("sensors.temperature", make_message(), 1)

        body = client.get("/api/health").json()

        assert body["status"] == "ok"
        assert body["buffer_size"] == 1
        assert body["connected_clients"] == 0
        assert body["pipeline_state"] == "idle"

    async def test_pipeline_state_follows_the_framework(
        self, client: TestClient, framework: Framework
    ) -> None:
        from cod3s_data.framework import PipelineState

        framework._pipeline_state = PipelineState.RUNNING

        assert client.get("/api/health").json()["pipeline_state"] == "running"


class TestTopology:
    """The endpoint describes the pipeline, refreshed by what the buffer holds.

    It used to be built from buffered events alone. A component announces its
    state and its subscriptions once, at startup, into the same ring buffer the
    messages flow through: on a busy pipeline they are evicted within seconds,
    and the endpoint then reported an empty pipeline. What the framework
    declares does not expire, so it is the floor.
    """

    async def test_nodes_and_edges(self, client: TestClient, bridge: ObservatoryBridge) -> None:
        await _seed_topology(bridge)

        body = client.get("/api/topology").json()

        # The seeded ids, plus the fixture pipeline's own components.
        assert {"src-0", "tfm-0", "dst-0"} <= {n["id"] for n in body["nodes"]}
        # Only subscriptions, never the unsubscribes, become edges.
        assert {"pattern": "sensors.*", "subscriber_id": "tfm-0"} in body["edges"]
        assert not any(e["pattern"] == "retired.*" for e in body["edges"])

    async def test_latest_state_per_component_wins(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        await bridge.on_component_state_change("src-0", "source", "idle", "running")
        await bridge.on_component_state_change("src-0", "source", "running", "stopped")

        nodes = client.get("/api/topology").json()["nodes"]

        assert {"id": "src-0", "type": "source", "state": "stopped"} in nodes

    async def test_reports_the_pipeline_before_any_event(self, client: TestClient) -> None:
        # Nothing has been observed yet, but the pipeline is already known.
        body = client.get("/api/topology").json()
        assert [n["type"] for n in body["nodes"]] == ["source", "transformation", "destination"]

    async def test_survives_a_buffer_full_of_messages(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        """The startup events scroll out; the topology must not go with them."""
        await _seed_topology(bridge)
        for _ in range(600):
            await bridge.on_message_published("sensors.temperature", make_message(), 1)

        body = client.get("/api/topology").json()

        assert body["nodes"], "the pipeline is still declared, whatever the buffer holds"
        assert body["edges"]

    async def test_component_detail(self, client: TestClient, bridge: ObservatoryBridge) -> None:
        await _seed_topology(bridge)

        body = client.get("/api/components/tfm-0").json()

        assert body == {"id": "tfm-0", "type": "transformation", "state": "running"}

    async def test_unknown_component_is_404(self, client: TestClient) -> None:
        response = client.get("/api/components/nope")

        assert response.status_code == 404
        assert "nope" in response.json()["detail"]


class TestChannelHistory:
    async def test_returns_only_that_channel(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        await bridge.on_message_published("sensors.temperature", make_message(value=198.0), 1)
        await bridge.on_message_published("alarms.temperature", make_message(value=220.0), 1)

        body = client.get("/api/channels/sensors.temperature/history").json()

        assert body["channel"] == "sensors.temperature"
        assert body["count"] == 1
        assert body["messages"][0]["data"]["channel"] == "sensors.temperature"

    async def test_limit_keeps_the_most_recent(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        for value in range(5):
            await bridge.on_message_published("sensors.temperature", make_message(value=value), 1)

        body = client.get("/api/channels/sensors.temperature/history?limit=2").json()

        assert body["count"] == 2
        assert [m["data"]["value_preview"] for m in body["messages"]] == ["3", "4"]

    async def test_unknown_channel_is_empty_not_404(self, client: TestClient) -> None:
        body = client.get("/api/channels/never.published/history").json()

        assert body == {"channel": "never.published", "messages": [], "count": 0}

    @pytest.mark.parametrize("limit", [0, 1001])
    async def test_limit_out_of_range_is_rejected(self, client: TestClient, limit: int) -> None:
        assert client.get(f"/api/channels/x/history?limit={limit}").status_code == 422


class TestParams:
    async def test_lists_the_param_declared_by_the_transform(self, client: TestClient) -> None:
        body = client.get("/api/params").json()

        assert body["count"] == 1
        param = body["params"][0]
        assert param["component_id"] == "tfm-0"
        assert param["component_label"] == "Extruder alarm"
        assert param["param_name"] == "setpoint"
        assert param["channel"] == PARAM_CHANNEL
        assert param["default"] == 200.0

    async def test_update_publishes_on_the_channel(
        self, client: TestClient, framework: Framework
    ) -> None:
        transform = framework.transformations[0]
        store = transform._param_stores[0]
        await framework.broker.start()
        await store.start()

        response = client.post(f"/api/params/{PARAM_CHANNEL}", json={"value": 220.0})

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert transform.setpoint == 220.0

    async def test_update_without_value_is_400(self, client: TestClient) -> None:
        response = client.post(f"/api/params/{PARAM_CHANNEL}", json={"key": "extruder"})

        assert response.status_code == 400
        assert response.json()["detail"] == "Body must contain 'value'"

    async def test_update_without_a_framework_is_500(
        self, client: TestClient, bridge: ObservatoryBridge
    ) -> None:
        bridge._framework = None

        response = client.post(f"/api/params/{PARAM_CHANNEL}", json={"value": 1.0})

        assert response.status_code == 500
        assert response.json()["detail"] == "No framework connected"

    async def test_a_param_update_does_not_erase_the_topology(
        self, client: TestClient, bridge: ObservatoryBridge, framework: Framework
    ) -> None:
        """Regression guard for the defect that motivated testing this surface.

        A parameter update used to take the component out of /api/topology.
        """
        await _seed_topology(bridge)
        await framework.broker.start()

        client.post(f"/api/params/{PARAM_CHANNEL}", json={"value": 220.0})

        assert {n["id"] for n in client.get("/api/topology").json()["nodes"]} == {
            "src-0",
            "tfm-0",
            "dst-0",
        }


class TestDebugRoutes:
    """The router is mounted whether or not debug is enabled."""

    async def test_state(self, debug_client: TestClient) -> None:
        body = debug_client.get("/api/debug/state").json()

        assert body["state"] == "running"
        assert body["granularity"] == "message"

    async def test_breakpoint_lifecycle(self, debug_client: TestClient) -> None:
        created = debug_client.post(
            "/api/debug/breakpoints",
            json={"channel_pattern": "sensors.*", "condition": "value > 100"},
        )
        assert created.status_code == 201
        bp_id = created.json()["breakpoint_id"]

        listed = debug_client.get("/api/debug/breakpoints").json()
        assert [bp["id"] for bp in listed] == [bp_id]
        assert listed[0]["channel_pattern"] == "sensors.*"

        assert debug_client.delete(f"/api/debug/breakpoints/{bp_id}").status_code == 204
        assert debug_client.get("/api/debug/breakpoints").json() == []

    async def test_invalid_condition_is_400(self, debug_client: TestClient) -> None:
        response = debug_client.post(
            "/api/debug/breakpoints",
            json={"channel_pattern": "sensors.*", "condition": "__import__('os')"},
        )

        assert response.status_code == 400

    async def test_deleting_an_unknown_breakpoint_is_404(self, debug_client: TestClient) -> None:
        assert debug_client.delete("/api/debug/breakpoints/bp-nope").status_code == 404

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/debug/state"),
            ("get", "/api/debug/breakpoints"),
            ("post", "/api/debug/breakpoints"),
            ("delete", "/api/debug/breakpoints/bp-1"),
        ],
    )
    async def test_refused_when_debug_is_off(
        self, client: TestClient, method: str, path: str
    ) -> None:
        """Without a controller these answered 500 with an AttributeError."""
        kwargs = {"json": {"channel_pattern": "sensors.*"}} if method == "post" else {}

        response = getattr(client, method)(path, **kwargs)

        assert response.status_code == 404
        assert response.json()["detail"] == "Debug mode is not enabled"


class TestSpaDeepLinks:
    """A route typed or refreshed must load, not 404.

    The router runs in HTML5 history mode: `/topology` is a path the browser
    asks the server for on a fresh load. There is no such file, and the plain
    static handler answered 404 — the pages only ever worked when reached by
    clicking from an already-loaded one.
    """

    def test_a_route_serves_the_app(self, client: TestClient) -> None:
        for path in ("/topology", "/timeline", "/messages", "/parameters", "/debug"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers["content-type"].startswith("text/html"), path

    def test_a_missing_bundle_still_says_so(self, client: TestClient) -> None:
        # Answering HTML for a missing script would fail to parse, and hide why.
        assert client.get("/assets/does-not-exist.js").status_code == 404

    def test_the_api_is_untouched(self, client: TestClient) -> None:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/components/nope").status_code == 404
