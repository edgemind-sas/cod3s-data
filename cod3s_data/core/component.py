"""Component lifecycle management for COD3S Data Framework."""

from abc import ABC, abstractmethod
from enum import Enum


class ComponentState(Enum):
    """Component lifecycle states."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class Component(ABC):
    """Base class for all lifecycle-managed components."""

    def __init__(self) -> None:
        self._state = ComponentState.CREATED

    @abstractmethod
    async def start(self) -> None:
        """Start the component."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the component."""
        ...

    @property
    def state(self) -> ComponentState:
        """Get current component state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if component is running."""
        return self._state == ComponentState.RUNNING
