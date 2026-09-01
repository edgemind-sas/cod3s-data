"""Configuration models for COD3S Observatory."""

from pydantic import BaseModel, Field, field_validator


class SamplingConfig(BaseModel):
    """Sampling configuration for high-throughput pipelines."""

    strategy: str = Field(default="none", pattern="^(none|every_nth|time_based)$")
    rate: int = Field(default=1, ge=1, le=10000)
    interval_ms: int = Field(default=100, ge=10, le=10000)


class ChannelFilterConfig(BaseModel):
    """Which channels the Observatory watches.

    Patterns are the broker's: `sensors.*` for one segment, `alerts.**` for any
    depth. An empty `include` watches everything; `exclude` then removes from it.
    """

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


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
    # How many messages the Observatory remembers. One knob for the two stores
    # counted in messages, because they have to agree: a row listed in the UI
    # whose details have already been evicted is a row that answers "no longer
    # available" when clicked.
    history_size: int = Field(default=5000, ge=50, le=100000)
    # Journeys are counted in TRACES, not messages, and one trace covers a whole
    # fan-out: on a six-sensor unpack it holds some sixty steps and accounts for
    # nineteen published messages. Tying it to `history_size` therefore bought
    # about nineteen times more journey history than message history, at 26 kB a
    # trace — 129 MB at five thousand of them, against 9 MB for the messages
    # themselves. It gets its own budget.
    journey_size: int = Field(default=500, ge=50, le=20000)
    # Explicit overrides, for a pipeline that wants to list far more than it can
    # inspect. Left unset, both follow `history_size`; read them through
    # `retained_events` and `retained_details`, never directly.
    buffer_size: int | None = Field(default=None, ge=100, le=100000)
    message_detail_cache_size: int | None = Field(default=None, ge=50, le=100000)
    memory_limit_mb: int = Field(default=50, ge=10, le=500)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    # Watching fewer channels buys history on the ones that matter: an
    # alarm fires once and is drowned by the routine traffic otherwise.
    channels: ChannelFilterConfig = Field(default_factory=ChannelFilterConfig)
    interactive: bool = False

    @property
    def retained_events(self) -> int:
        """Ring buffer capacity, in events."""
        return self.buffer_size if self.buffer_size is not None else self.history_size

    @property
    def retained_details(self) -> int:
        """Inspectable messages."""
        if self.message_detail_cache_size is not None:
            return self.message_detail_cache_size
        return self.history_size

    @property
    def retained_traces(self) -> int:
        """Journeys kept, counted in traces — see `journey_size`."""
        return self.journey_size

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v not in ("127.0.0.1", "localhost"):
            raise ValueError("V1 only supports localhost (127.0.0.1 or localhost)")
        return v
