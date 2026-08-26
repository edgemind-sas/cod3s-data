"""Fixtures for the Observatory HTTP and WebSocket surface.

The app is built over a real pipeline created by the real `ComponentFactory`,
because that is what the routes report on: component ids, labels and
`ParamRef`-declared parameters all come from the factory, not from the config
file. A hand-rolled stand-in would have agreed with any assertion made here.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cod3s_data.config.models import (
    DestinationConfig,
    PipelineConfig,
    SourceConfig,
    TransformConfig,
)
from cod3s_data.core.message import Message
from cod3s_data.framework import Framework
from cod3s_data.observatory.app import create_app
from cod3s_data.observatory.bridge import ObservatoryBridge
from cod3s_data.observatory.buffer import EventBuffer
from cod3s_data.observatory.config import ObservatoryConfig
from cod3s_data.observatory.debug import DebugController
from cod3s_data.observatory.message_store import JourneyStore, MessageDetailStore
from cod3s_data.observatory.sampler import MessageSampler
from cod3s_data.observatory.websocket_manager import WebSocketManager

PARAM_CHANNEL = "params.alarm.extruder"


def make_message(key: str = "extruder", value: Any = 42.0) -> Message:
    """Build a message with the current timestamp."""
    return Message(key=key, timestamp=datetime.now(UTC), value=value, tags={})


def make_pipeline_config() -> PipelineConfig:
    """A three-component pipeline whose transform declares a ParamRef."""
    return PipelineConfig(
        name="observatory-surface",
        display_name="Observatory surface",
        subtitle="fixture pipeline",
        sources=[
            SourceConfig(
                type="sequence",
                label="Extruder probe",
                channel="sensors.temperature",
                params={"start_value": 195, "end_value": 205, "rate": 100.0},
            )
        ],
        transformations=[
            TransformConfig(
                type="relative_alarm",
                label="Extruder alarm",
                input_channels="sensors.temperature",
                output_channel="alarms.temperature",
                params={
                    "setpoint": {"ref": PARAM_CHANNEL, "default": 200.0},
                    "tolerance_abs": 5.0,
                },
            )
        ],
        destinations=[
            DestinationConfig(type="collect", label="Alarm sink", channel_pattern="alarms.**")
        ],
    )


@pytest.fixture
def framework() -> Framework:
    """A framework with components created through the real factory, not started."""
    fw = Framework(make_pipeline_config(), observatory=False)
    fw._create_components()
    return fw


@pytest.fixture
def buffer() -> EventBuffer:
    return EventBuffer(max_size=100)


@pytest.fixture
def message_store() -> MessageDetailStore:
    return MessageDetailStore()


@pytest.fixture
def journey_store() -> JourneyStore:
    return JourneyStore()


@pytest.fixture
def bridge(
    framework: Framework,
    buffer: EventBuffer,
    message_store: MessageDetailStore,
    journey_store: JourneyStore,
) -> ObservatoryBridge:
    """A bridge wired to the fixture framework, as Framework.__init__ wires it."""
    br = ObservatoryBridge(
        event_buffer=buffer,
        sampler=MessageSampler(),
        websocket_manager=WebSocketManager(),
        message_store=message_store,
        journey_store=journey_store,
    )
    br._framework = framework
    for component in (*framework.sources, *framework.transformations, *framework.destinations):
        component._bridge = br
    return br


@pytest.fixture
def debug_controller() -> DebugController:
    return DebugController(enabled=True)


def build_client(
    bridge: ObservatoryBridge,
    buffer: EventBuffer,
    debug_controller: DebugController | None,
) -> TestClient:
    """Build a TestClient over the Observatory app."""
    app = create_app(
        bridge=bridge,
        event_buffer=buffer,
        ws_manager=bridge._ws,
        config=ObservatoryConfig(),
        debug_controller=debug_controller,
    )
    return TestClient(app)


@pytest.fixture
def client(bridge: ObservatoryBridge, buffer: EventBuffer) -> Iterator[TestClient]:
    """Client for an Observatory with debug disabled — the default deployment."""
    with build_client(bridge, buffer, None) as test_client:
        yield test_client


@pytest.fixture
def debug_client(
    bridge: ObservatoryBridge,
    buffer: EventBuffer,
    debug_controller: DebugController,
) -> Iterator[TestClient]:
    """Client for an Observatory started with --debug."""
    with build_client(bridge, buffer, debug_controller) as test_client:
        yield test_client
