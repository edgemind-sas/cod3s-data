"""Destinations for COD3S Data Framework."""

from cod3s_data.destinations.base import Destination, RetryStrategy
from cod3s_data.destinations.collect import CollectDestination
from cod3s_data.destinations.core import (
    ConsoleDestination,
    FileDestination,
    InMemoryDestination,
)

__all__ = [
    "Destination",
    "RetryStrategy",
    "ConsoleDestination",
    "FileDestination",
    "InMemoryDestination",
    "CollectDestination",
]
