"""Config file loader supporting TOML and YAML formats."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml

from entwine.config.models import FullConfig


def _load_raw(config_path: Path) -> dict[str, Any]:
    """Read a TOML or YAML file and return its contents as a plain dict."""
    suffix = config_path.suffix.lower()
    if suffix == ".toml":
        with config_path.open("rb") as fh:
            return tomllib.load(fh)  # type: ignore[return-value]
    if suffix in {".yaml", ".yml"}:
        with config_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise ValueError(
                f"Expected a YAML mapping at the top level of {config_path}, "
                f"got {type(data).__name__}"
            )
        return data  # type: ignore[return-value]
    raise ValueError(f"Unsupported config file format '{suffix}'. Use .toml, .yaml, or .yml.")


def load_config(config_path: Path) -> FullConfig:
    """Load and validate a simulation config file.

    Args:
        config_path: Path to a ``.toml``, ``.yaml``, or ``.yml`` config file.

    Returns:
        A validated :class:`FullConfig` instance.

    Raises:
        FileNotFoundError: If *config_path* does not exist.
        ValueError: If the file format is not supported or YAML is malformed.
        pydantic.ValidationError: If the config fails schema validation.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = _load_raw(config_path)
    return FullConfig.model_validate(raw)
