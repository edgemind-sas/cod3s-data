"""COD3S Data Framework - Lightweight data streaming for real-time sensor processing."""

__version__ = "1.0.0"

from cod3s_data.core.message import Message
from cod3s_data.plugins import PluginError

__all__ = [
    "Message",
    "PluginError",
    "__version__",
]
