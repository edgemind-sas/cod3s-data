"""Structured logging for COD3S Data Framework.

Uses structlog for structured, machine-parsable logs with context binding.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import FilteringBoundLogger, Processor


def configure_logging(
    *,
    level: str = "INFO",
    format: str = "console",  # "console" or "json"
    enable_colors: bool = True,
) -> None:
    """Configure structured logging for the framework.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format ("console" for development, "json" for production)
        enable_colors: Enable colored output (only for console format)

    Examples:
        >>> configure_logging(level="DEBUG", format="console")
        >>> configure_logging(level="INFO", format="json")  # Production
    """
    # Convert level string to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Shared processors for both formats
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Format-specific processors
    if format == "json":
        # JSON format for production
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Console format for development
        renderer = structlog.dev.ConsoleRenderer(colors=enable_colors)

    # Configure structlog
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the formatter for the handler
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Apply to root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)


def get_logger(name: str, **initial_context: Any) -> FilteringBoundLogger:
    """Get a logger with optional initial context.

    Args:
        name: Logger name (typically __name__ of the module)
        **initial_context: Initial context to bind to the logger

    Returns:
        Bound logger with context

    Examples:
        >>> logger = get_logger(__name__)
        >>> logger.info("starting", component="source")

        >>> logger = get_logger(__name__, component="broker", node_id="node-1")
        >>> logger.info("message_published", channel="sensors.temp", count=1)
    """
    logger: FilteringBoundLogger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


# Default configuration on import (can be overridden)
configure_logging()
