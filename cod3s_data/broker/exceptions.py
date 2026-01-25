"""Broker-related exceptions."""


class BrokerError(Exception):
    """Base exception for broker errors."""

    pass


class InvalidChannelError(BrokerError):
    """Raised when a channel name is invalid."""

    pass


class InvalidPatternError(BrokerError):
    """Raised when a subscription pattern is invalid."""

    pass


class PublishError(BrokerError):
    """Raised when message publish fails."""

    pass
