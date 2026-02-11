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
    buffer_size: int = Field(default=1000, ge=100, le=100000)
    memory_limit_mb: int = Field(default=50, ge=10, le=500)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    interactive: bool = False

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if v not in ("127.0.0.1", "localhost"):
            raise ValueError("V1 only supports localhost (127.0.0.1 or localhost)")
        return v
