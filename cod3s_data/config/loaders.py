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

    # Observatory overrides
    config = _apply_observatory_env_overrides(config)

    return config


def _apply_observatory_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply COD3S_OBSERVATORY_* environment variable overrides."""
    obs_env_map: list[tuple[str, str, str]] = [
        ("COD3S_OBSERVATORY_ENABLED", "enabled", "bool"),
        ("COD3S_OBSERVATORY_HOST", "host", "str"),
        ("COD3S_OBSERVATORY_PORT", "port", "int"),
        ("COD3S_OBSERVATORY_BUFFER_SIZE", "buffer_size", "int"),
        ("COD3S_OBSERVATORY_MEMORY_LIMIT_MB", "memory_limit_mb", "int"),
    ]

    obs_debug_env_map: list[tuple[str, str, str]] = [
        ("COD3S_OBSERVATORY_DEBUG", "enabled", "bool"),
        ("COD3S_OBSERVATORY_DEBUG_GRANULARITY", "granularity", "str"),
        ("COD3S_OBSERVATORY_DEBUG_AUTO_PAUSE", "auto_pause", "bool"),
    ]

    obs_sampling_env_map: list[tuple[str, str, str]] = [
        ("COD3S_OBSERVATORY_SAMPLING_STRATEGY", "strategy", "str"),
        ("COD3S_OBSERVATORY_SAMPLING_RATE", "rate", "float"),
        ("COD3S_OBSERVATORY_SAMPLING_INTERVAL_MS", "interval_ms", "int"),
    ]

    has_any = any(os.getenv(env) is not None for env, _, _ in obs_env_map + obs_debug_env_map + obs_sampling_env_map)
    if not has_any:
        return config

    if "observatory" not in config or config["observatory"] is None:
        config["observatory"] = {}

    obs = config["observatory"]

    for env_var, key, typ in obs_env_map:
        val = os.getenv(env_var)
        if val is not None:
            obs[key] = _parse_env_value(val, typ)

    # Debug sub-section
    has_debug = any(os.getenv(env) is not None for env, _, _ in obs_debug_env_map)
    if has_debug:
        if "debug" not in obs:
            obs["debug"] = {}
        for env_var, key, typ in obs_debug_env_map:
            val = os.getenv(env_var)
            if val is not None:
                obs["debug"][key] = _parse_env_value(val, typ)

    # Sampling sub-section
    has_sampling = any(os.getenv(env) is not None for env, _, _ in obs_sampling_env_map)
    if has_sampling:
        if "sampling" not in obs:
            obs["sampling"] = {}
        for env_var, key, typ in obs_sampling_env_map:
            val = os.getenv(env_var)
            if val is not None:
                obs["sampling"][key] = _parse_env_value(val, typ)

    return config


def _parse_env_value(val: str, typ: str) -> Any:
    """Parse an environment variable value to the expected type."""
    if typ == "bool":
        return val.lower() in ("true", "1", "yes")
    if typ == "int":
        return int(val)
    if typ == "float":
        return float(val)
    return val
