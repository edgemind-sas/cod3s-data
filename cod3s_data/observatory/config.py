"""Configuration models for COD3S Observatory."""

from pydantic import BaseModel, Field, field_validator


class SamplingConfig(BaseModel):
    """Sampling configuration for high-throughput pipelines."""

    strategy: str = Field(default="none", pattern="^(none|every_nth|time_based)$")
    rate: int = Field(default=1, ge=1, le=10000)
    interval_ms: int = Field(default=100, ge=10, le=10000)


class DebugConfig(BaseModel):
    """Debug mode configuration."""

    enabled: bool = False
    granularity: str = Field(default="message", pattern="^(message|stage|breakpoint)$")
    auto_pause: bool = False


class ObservatoryConfig(BaseModel):
    """Observatory module configuration.

    Can be created from:
    - Python: ObservatoryConfig(port=9000)
    - YAML: observatory: section in pipeline config
    - Environment: COD3S_OBSERVATORY_* variables
    """

    enabled: bool = True
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8765, ge=1024, le=65535)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    # How many messages the Observatory remembers. One knob, because the three
    # stores it feeds have to agree: a row listed in the UI whose details or
    # journey have already been evicted is a row that answers "no longer
    # available" when clicked. They used to be set separately — 1000 listed
    # against 500 inspectable — so half the table was clickable and dead.
    history_size: int = Field(default=500, ge=50, le=100000)
    # Explicit overrides, for a pipeline that wants to list far more than it can
    # inspect. Left unset, both follow `history_size`; read them through
    # `retained_events` and `retained_details`, never directly.
    buffer_size: int | None = Field(default=None, ge=100, le=100000)
    message_detail_cache_size: int | None = Field(default=None, ge=50, le=5000)
    memory_limit_mb: int = Field(default=50, ge=10, le=500)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    interactive: bool = False

    @property
    def retained_events(self) -> int:
        """Ring buffer capacity, in events."""
        return self.buffer_size if self.buffer_size is not None else self.history_size

    @property
    def retained_details(self) -> int:
        """Inspectable messages, and traces kept for their journeys."""
        if self.message_detail_cache_size is not None:
            return self.message_detail_cache_size
        return self.history_size

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v not in ("127.0.0.1", "localhost"):
            raise ValueError("V1 only supports localhost (127.0.0.1 or localhost)")
        return v
