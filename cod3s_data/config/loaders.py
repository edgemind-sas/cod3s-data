"""Configuration loaders for COD3S Data Framework."""

import os
from pathlib import Path
from typing import Any

import yaml

from cod3s_data.config.models import PipelineConfig


def load_yaml(path: str | Path) -> PipelineConfig:
    """Load configuration from YAML file.

    Args:
        path: Path to YAML configuration file

    Returns:
        PipelineConfig object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid or validation fails
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Empty configuration file: {path}")

    # Apply environment variable overrides
    data = _apply_env_overrides(data)

    return PipelineConfig.model_validate(data)


def load_dict(config_dict: dict[str, Any]) -> PipelineConfig:
    """Load configuration from dictionary.

    Args:
        config_dict: Configuration dictionary

    Returns:
        PipelineConfig object

    Raises:
        ValueError: If validation fails
    """
    # Apply environment variable overrides
    config_dict = _apply_env_overrides(config_dict)
    return PipelineConfig.model_validate(config_dict)


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to configuration.

    Environment variables follow the pattern: COD3S_<SECTION>_<KEY>
    Example: COD3S_BROKER_ENABLE_METRICS=false

    Args:
        config: Configuration dictionary

    Returns:
        Configuration with environment overrides applied
    """
    # Broker overrides
    if "broker" not in config:
        config["broker"] = {}

    if os.getenv("COD3S_BROKER_ENABLE_METRICS") is not None:
        config["broker"]["enable_metrics"] = (
            os.getenv("COD3S_BROKER_ENABLE_METRICS", "true").lower() == "true"
        )

    if os.getenv("COD3S_BROKER_HISTORY_SIZE") is not None:
        try:
            config["broker"]["history_size"] = int(os.getenv("COD3S_BROKER_HISTORY_SIZE", "100"))
        except ValueError:
            pass

    # Pipeline name override
    if os.getenv("COD3S_PIPELINE_NAME") is not None:
        config["name"] = os.getenv("COD3S_PIPELINE_NAME")

    return config
