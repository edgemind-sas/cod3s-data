"""COD3S Observatory - Optional web-based observability module.

Usage:
    pip install cod3s-data[observatory]

    from cod3s_data import Framework
    framework = Framework(config, observatory=True)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cod3s_data.observatory.bridge import ObservatoryBridge
    from cod3s_data.observatory.config import ObservatoryConfig


def create_observatory(
    config: ObservatoryConfig | None = None,
) -> ObservatoryBridge:
    """Create and configure the Observatory module.

    Called by Framework.__init__() when observatory is enabled.

    Args:
        config: Optional configuration (defaults used if None)

    Returns:
        Configured ObservatoryBridge instance
    """
    from cod3s_data.observatory.app import create_app
    from cod3s_data.observatory.bridge import ObservatoryBridge
    from cod3s_data.observatory.buffer import EventBuffer
    from cod3s_data.observatory.channel_filter import ChannelFilter
    from cod3s_data.observatory.config import ObservatoryConfig
    from cod3s_data.observatory.debug import DebugController
    from cod3s_data.observatory.message_store import JourneyStore, MessageDetailStore
    from cod3s_data.observatory.sampler import MessageSampler
    from cod3s_data.observatory.server import EmbeddedServer
    from cod3s_data.observatory.websocket_manager import WebSocketManager

    if config is None:
        config = ObservatoryConfig()

    # Create components
    event_buffer = EventBuffer(
        max_size=config.retained_events,
        memory_limit_bytes=config.memory_limit_mb * 1024 * 1024,
    )
    sampler = MessageSampler(
        strategy=config.sampling.strategy,
        rate=config.sampling.rate,
        interval_ms=config.sampling.interval_ms,
    )
    ws_manager = WebSocketManager()
    debug_controller = DebugController(enabled=config.debug.enabled)
    channel_filter = ChannelFilter(include=config.channels.include, exclude=config.channels.exclude)
    message_store = MessageDetailStore(max_entries=config.retained_details)
    journey_store = JourneyStore(max_entries=config.retained_traces)

    # Create bridge
    bridge = ObservatoryBridge(
        event_buffer=event_buffer,
        sampler=sampler,
        websocket_manager=ws_manager,
        message_store=message_store,
        journey_store=journey_store,
        channel_filter=channel_filter,
    )

    # Create FastAPI app
    app = create_app(bridge, event_buffer, ws_manager, config, debug_controller)

    # Create embedded server
    server = EmbeddedServer(app, config.host, config.port)
    bridge._server = server

    return bridge
