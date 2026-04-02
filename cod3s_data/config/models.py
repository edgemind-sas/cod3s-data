"""Configuration models for COD3S Data Framework."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Configuration for a source component."""

    type: str = Field(..., description="Source type (e.g., 'random', 'sequence', 'csv')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    description: str | None = Field(default=None, description="Detailed description shown on hover")
    channel: str = Field(..., description="Channel to publish to")
    params: dict[str, Any] = Field(default_factory=dict, description="Source-specific parameters")


class TransformConfig(BaseModel):
    """Configuration for a transformation component."""

    type: str = Field(..., description="Transform type (e.g., 'filter', 'map', 'aggregate')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    description: str | None = Field(default=None, description="Detailed description shown on hover")
    input_channels: str | list[str] = Field(..., description="Input channel(s)")
    output_channel: str = Field(..., description="Output channel")
    params: dict[str, Any] = Field(default_factory=dict, description="Transform-specific parameters")


class DestinationConfig(BaseModel):
    """Configuration for a destination component."""

    type: str = Field(..., description="Destination type (e.g., 'console', 'file', 'inmemory')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    description: str | None = Field(default=None, description="Detailed description shown on hover")
    channel_pattern: str = Field(..., description="Channel pattern to subscribe to")
    params: dict[str, Any] = Field(default_factory=dict, description="Destination-specific parameters")


class BrokerConfig(BaseModel):
    """Configuration for the broker."""

    enable_metrics: bool = Field(default=True, description="Enable metrics emission")
    history_size: int = Field(default=100, description="Default history size per channel")


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration."""

    name: str = Field(default="cod3s_pipeline", description="Pipeline name")
    plugins: list[str] = Field(
        default_factory=list,
        description="Plugin module paths to load before creating components",
    )
    broker: BrokerConfig = Field(default_factory=BrokerConfig, description="Broker configuration")
    sources: list[SourceConfig] = Field(default_factory=list, description="Source components")
    transformations: list[TransformConfig] = Field(
        default_factory=list, description="Transformation components"
    )
    destinations: list[DestinationConfig] = Field(
        default_factory=list, description="Destination components"
    )
    observatory: dict[str, Any] | None = Field(
        default=None, description="Observatory configuration (optional)"
    )
