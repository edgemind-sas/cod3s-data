"""Embedded Uvicorn server for Observatory."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()


class EmbeddedServer:
    """Embeds Uvicorn in the framework's asyncio event loop.

    Key: loop="none" tells Uvicorn to use the existing event loop.
    """

    def __init__(self, app: Any, host: str, port: int) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._server: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the Uvicorn server as an asyncio task."""
        import uvicorn

        config = uvicorn.Config(
            app=self._app,
            host=self._host,
            port=self._port,
            loop="none",
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        try:
            self._task = asyncio.create_task(self._server.serve())
            logger.info(
                "Observatory started",
                url=f"http://{self._host}:{self._port}",
            )
        except OSError as e:
            logger.warning(
                "Observatory failed to start (port may be in use)",
                host=self._host,
                port=self._port,
                error=str(e),
            )

    async def stop(self) -> None:
        """Gracefully stop the server."""
        if self._server is not None:
            self._server.should_exit = True
            if self._task is not None:
                try:
                    await asyncio.wait_for(self._task, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass
                except Exception:
                    pass
            logger.info("Observatory stopped")
