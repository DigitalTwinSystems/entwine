"""Unit tests for the entsim CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import entsim
from entsim.cli.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONFIG = """\
simulation:
  name: "Test Sim"
  tick_interval_seconds: 30.0

enterprise:
  name: "Acme Corp"
  departments:
    - name: "Engineering"
    - name: "Marketing"

agents:
  - name: cto
    role: "Chief Technology Officer"
    department: "Engineering"
    goal: "Drive technical strategy"
  - name: cmo
    role: "Chief Marketing Officer"
    department: "Marketing"
    goal: "Grow the brand"
"""

INVALID_CONFIG = """\
# Missing required 'simulation' and 'enterprise' keys
agents: []
"""


@pytest.fixture()
def valid_config_file(tmp_path: Path) -> Path:
    """Write a valid config YAML to a temp file."""
    config_file = tmp_path / "entsim.yaml"
    config_file.write_text(VALID_CONFIG)
    return config_file


@pytest.fixture()
def invalid_config_file(tmp_path: Path) -> Path:
    """Write an invalid config YAML to a temp file."""
    config_file = tmp_path / "bad.yaml"
    config_file.write_text(INVALID_CONFIG)
    return config_file


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------


def test_version_output() -> None:
    """version command prints 'entsim <version>'."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"entsim {entsim.__version__}" in result.output


def test_version_short_flag() -> None:
    """version --short prints only the version string."""
    result = runner.invoke(app, ["version", "--short"])
    assert result.exit_code == 0
    assert result.output.strip() == entsim.__version__


# ---------------------------------------------------------------------------
# validate command — valid config
# ---------------------------------------------------------------------------


def test_validate_valid_config(valid_config_file: Path) -> None:
    """validate with a valid config file exits 0 and prints summary."""
    result = runner.invoke(app, ["validate", "--config", str(valid_config_file)])
    assert result.exit_code == 0, result.output
    assert "Simulation: Test Sim" in result.output
    assert "Enterprise: Acme Corp" in result.output
    assert "Departments: 2" in result.output
    assert "Agents: 2" in result.output
    assert "Config is valid." in result.output


# ---------------------------------------------------------------------------
# validate command — invalid / missing config
# ---------------------------------------------------------------------------


def test_validate_missing_config(tmp_path: Path) -> None:
    """validate with a non-existent config file exits non-zero with error."""
    missing = tmp_path / "does_not_exist.yaml"
    result = runner.invoke(app, ["validate", "--config", str(missing)])
    assert result.exit_code != 0
    assert "Error" in result.output


def test_validate_invalid_config(invalid_config_file: Path) -> None:
    """validate with an invalid config file exits non-zero with an error message."""
    result = runner.invoke(app, ["validate", "--config", str(invalid_config_file)])
    assert result.exit_code != 0
    assert "Error" in result.output
