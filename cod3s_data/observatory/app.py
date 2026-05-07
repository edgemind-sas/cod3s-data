"""FastAPI application factory for Observatory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from cod3s_data.observatory.routes import channels, debug, health, params, topology, ws

if TYPE_CHECKING:
    from cod3s_data.observatory.bridge import ObservatoryBridge
    from cod3s_data.observatory.buffer import EventBuffer
    from cod3s_data.observatory.config import ObservatoryConfig
    from cod3s_data.observatory.debug import DebugController
    from cod3s_data.observatory.websocket_manager import WebSocketManager


def create_app(
    bridge: ObservatoryBridge,
    event_buffer: EventBuffer,
    ws_manager: WebSocketManager,
    config: ObservatoryConfig,
    debug_controller: DebugController | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Mounts REST routes, WebSocket endpoint, and static files.
    """
    app = FastAPI(
        title="COD3S Observatory",
        version="1.0.0",
        docs_url="/api/docs" if config.debug.enabled else None,
        redoc_url=None,
    )

    # Store dependencies for route access
    app.state.bridge = bridge
    app.state.buffer = event_buffer
    app.state.ws_manager = ws_manager
    app.state.config = config
    app.state.debug_controller = debug_controller

    # Mount API routes
    app.include_router(health.router, prefix="/api")
    app.include_router(topology.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(params.router, prefix="/api")
    app.include_router(debug.router, prefix="/api/debug")

    # Mount WebSocket
    app.include_router(ws.router)

    # Cache-busting: hashed assets are immutable, but index.html must never be cached
    # so the browser always loads the latest JS/CSS references after a deploy.
    @app.middleware("http")
    async def _cache_control(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path in ("/", "/index.html") or response.headers.get(
            "content-type", ""
        ).startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    # Mount static frontend (must be last - catches all remaining routes)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and any(static_dir.iterdir()):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
