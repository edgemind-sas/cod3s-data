"""Configuration models for COD3S Data Framework."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParamRef(BaseModel):
    """Reference to a broker channel that supplies a parameter value.

    A component param declared as a ``ParamRef`` is hydrated from messages
    published on ``ref``. The factory replaces the ref with ``default`` at
    construction time and wires a ``ParameterStore`` that rebinds the
    attribute on every new message. This is the mechanism behind "variable"
    pipeline parameters (setpoints, tolerances, etc.) editable at runtime.

    YAML example::

        params:
          setpoint:
            ref: params.alarm.extruder
            default: 200.0
          # extract value['extruder'] from messages on the ref channel
          tolerance:
            ref: params.alarm
            key: extruder_tolerance
            default: 5.0
    """

    model_config = ConfigDict(frozen=True)

    ref: str = Field(..., description="Broker channel publishing this parameter's value")
    default: Any = Field(default=None, description="Value used until the first message arrives")
    key: str | None = Field(
        default=None,
        description="If the channel publishes dict-valued messages, extract this key",
    )


def is_param_ref(value: Any) -> bool:
    """Return True if ``value`` looks like a ``ParamRef`` payload (dict with 'ref' key)."""
    return isinstance(value, dict) and "ref" in value and isinstance(value["ref"], str)


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
    params: dict[str, Any] = Field(
        default_factory=dict, description="Transform-specific parameters"
    )


class DestinationConfig(BaseModel):
    """Configuration for a destination component."""

    type: str = Field(..., description="Destination type (e.g., 'console', 'file', 'inmemory')")
    label: str | None = Field(default=None, description="Human-readable label for display")
    description: str | None = Field(default=None, description="Detailed description shown on hover")
    channel_pattern: str = Field(..., description="Channel pattern to subscribe to")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Destination-specific parameters"
    )


class BrokerConfig(BaseModel):
    """Configuration for the broker."""

    enable_metrics: bool = Field(default=True, description="Enable metrics emission")
    history_size: int = Field(default=100, description="Default history size per channel")


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration."""

    name: str = Field(default="cod3s_pipeline", description="Pipeline name")
    display_name: str | None = Field(default=None, description="Display name for Observatory UI")
    subtitle: str | None = Field(default=None, description="Subtitle shown in Observatory UI")
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
