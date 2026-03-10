"""Unit tests for entwine.config — models, loader, and settings."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from entwine.agents.models import WorkingHours
from entwine.config.loader import load_config
from entwine.config.models import (
    AgentPersona,
    EnterpriseConfig,
    FullConfig,
    SimulationConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_YAML = textwrap.dedent("""\
    simulation:
      name: "Test Sim"
    enterprise:
      name: "Test Corp"
    agents: []
""")

_FULL_YAML = textwrap.dedent("""\
    simulation:
      name: "Full Sim"
      tick_interval_seconds: 15
      max_ticks: 100
      log_level: "DEBUG"
    enterprise:
      name: "Acme"
      description: "Test enterprise"
      departments:
        - name: "Engineering"
          description: "Dev team"
    agents:
      - name: "Alice"
        role: "CEO"
        department: "Executive"
        goal: "Grow the company"
        backstory: "Veteran entrepreneur"
        llm_tier: "premium"
        tools:
          - draft_email
          - schedule_meeting
        rag_access:
          - company-wide
        working_hours:
          start: "07:00"
          end: "20:00"
""")

_MINIMAL_TOML = textwrap.dedent("""\
    [simulation]
    name = "TOML Sim"

    [enterprise]
    name = "TOML Corp"
""")

_FULL_TOML = textwrap.dedent("""\
    [simulation]
    name = "TOML Full"
    tick_interval_seconds = 45.0
    max_ticks = 500
    log_level = "WARNING"

    [enterprise]
    name = "TOML Enterprises"
    description = "A TOML-configured enterprise"

    [[enterprise.departments]]
    name = "Marketing"
    description = "Growth team"

    [[agents]]
    name = "Bob"
    role = "Developer"
    department = "Engineering"
    goal = "Ship features"
    llm_tier = "fast"
    tools = ["post_to_slack"]
    rag_access = ["engineering"]

    [agents.working_hours]
    start = "08:00"
    end = "16:00"
""")


# ---------------------------------------------------------------------------
# YAML loading tests
# ---------------------------------------------------------------------------


def test_load_yaml_minimal(tmp_path: Path) -> None:
    """Minimal YAML with only required fields should load successfully."""
    cfg_file = tmp_path / "entwine.yaml"
    cfg_file.write_text(_MINIMAL_YAML, encoding="utf-8")

    config = load_config(cfg_file)

    assert isinstance(config, FullConfig)
    assert config.simulation.name == "Test Sim"
    assert config.enterprise.name == "Test Corp"
    assert config.agents == []


def test_load_yaml_full(tmp_path: Path) -> None:
    """Full YAML with all optional fields should load and validate correctly."""
    cfg_file = tmp_path / "entwine.yaml"
    cfg_file.write_text(_FULL_YAML, encoding="utf-8")

    config = load_config(cfg_file)

    assert config.simulation.tick_interval_seconds == 15.0
    assert config.simulation.max_ticks == 100
    assert config.simulation.log_level == "DEBUG"

    assert len(config.enterprise.departments) == 1
    assert config.enterprise.departments[0].name == "Engineering"

    assert len(config.agents) == 1
    agent = config.agents[0]
    assert agent.name == "Alice"
    assert agent.role == "CEO"
    assert agent.llm_tier == "premium"
    assert "draft_email" in agent.tools
    assert agent.working_hours.start == "07:00"
    assert agent.working_hours.end == "20:00"


def test_load_yaml_yml_extension(tmp_path: Path) -> None:
    """.yml extension should be treated the same as .yaml."""
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text(_MINIMAL_YAML, encoding="utf-8")

    config = load_config(cfg_file)
    assert config.simulation.name == "Test Sim"


# ---------------------------------------------------------------------------
# TOML loading tests
# ---------------------------------------------------------------------------


def test_load_toml_minimal(tmp_path: Path) -> None:
    """Minimal TOML with only required fields should load successfully."""
    cfg_file = tmp_path / "entwine.toml"
    cfg_file.write_text(_MINIMAL_TOML, encoding="utf-8")

    config = load_config(cfg_file)

    assert isinstance(config, FullConfig)
    assert config.simulation.name == "TOML Sim"
    assert config.enterprise.name == "TOML Corp"


def test_load_toml_full(tmp_path: Path) -> None:
    """Full TOML config should load all nested structures correctly."""
    cfg_file = tmp_path / "entwine.toml"
    cfg_file.write_text(_FULL_TOML, encoding="utf-8")

    config = load_config(cfg_file)

    assert config.simulation.tick_interval_seconds == 45.0
    assert config.simulation.max_ticks == 500
    assert config.simulation.log_level == "WARNING"

    assert len(config.enterprise.departments) == 1
    assert config.enterprise.departments[0].name == "Marketing"

    assert len(config.agents) == 1
    agent = config.agents[0]
    assert agent.name == "Bob"
    assert agent.llm_tier == "fast"
    assert agent.working_hours.start == "08:00"
    assert agent.working_hours.end == "16:00"


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


def test_missing_simulation_name_raises(tmp_path: Path) -> None:
    """Omitting `simulation.name` should raise a ValidationError."""
    bad_yaml = textwrap.dedent("""\
        simulation:
          tick_interval_seconds: 10
        enterprise:
          name: "Corp"
    """)
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text(bad_yaml, encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        load_config(cfg_file)

    errors = exc_info.value.errors()
    fields = [e["loc"] for e in errors]
    assert any("name" in loc for loc in fields)


def test_missing_enterprise_name_raises(tmp_path: Path) -> None:
    """Omitting `enterprise.name` should raise a ValidationError."""
    bad_yaml = textwrap.dedent("""\
        simulation:
          name: "Sim"
        enterprise:
          description: "No name here"
    """)
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text(bad_yaml, encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        load_config(cfg_file)

    errors = exc_info.value.errors()
    fields = [e["loc"] for e in errors]
    assert any("name" in loc for loc in fields)


def test_missing_agent_required_fields_raises(tmp_path: Path) -> None:
    """An agent missing `role`, `department`, or `goal` should raise a ValidationError."""
    bad_yaml = textwrap.dedent("""\
        simulation:
          name: "Sim"
        enterprise:
          name: "Corp"
        agents:
          - name: "Incomplete Agent"
            # role, department, goal are missing
    """)
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text(bad_yaml, encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(cfg_file)


def test_yaml_non_dict_top_level_raises(tmp_path: Path) -> None:
    """A YAML file whose top-level is not a mapping should raise ValueError."""
    cfg_file = tmp_path / "list.yaml"
    cfg_file.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a YAML mapping"):
        load_config(cfg_file)


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    """A file with an unsupported extension should raise a ValueError."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported config file format"):
        load_config(cfg_file)


def test_missing_file_raises(tmp_path: Path) -> None:
    """A path that does not exist should raise a FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


def test_negative_tick_interval_raises(tmp_path: Path) -> None:
    """A non-positive tick_interval_seconds should fail validation."""
    bad_yaml = textwrap.dedent("""\
        simulation:
          name: "Sim"
          tick_interval_seconds: -5
        enterprise:
          name: "Corp"
    """)
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text(bad_yaml, encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(cfg_file)


# ---------------------------------------------------------------------------
# AgentPersona default values
# ---------------------------------------------------------------------------


def test_agent_persona_defaults() -> None:
    """AgentPersona should apply correct defaults for all optional fields."""
    persona = AgentPersona(
        name="Carol",
        role="Designer",
        department="Product",
        goal="Create great UX",
    )

    assert persona.backstory == ""
    assert persona.llm_tier == "standard"
    assert persona.tools == []
    assert persona.rag_access == []
    assert isinstance(persona.working_hours, WorkingHours)
    assert persona.working_hours.start == "09:00"
    assert persona.working_hours.end == "17:00"


def test_working_hours_defaults() -> None:
    """WorkingHours should default to 09:00-17:00."""
    wh = WorkingHours()
    assert wh.start == "09:00"
    assert wh.end == "17:00"


def test_simulation_config_defaults() -> None:
    """SimulationConfig optional fields should have sensible defaults."""
    sim = SimulationConfig(name="Demo")
    assert sim.tick_interval_seconds == 60.0
    assert sim.max_ticks is None
    assert sim.log_level == "INFO"


def test_enterprise_config_defaults() -> None:
    """EnterpriseConfig optional fields should default correctly."""
    ent = EnterpriseConfig(name="Corp")
    assert ent.description == ""
    assert ent.departments == []


# ---------------------------------------------------------------------------
# Example config smoke-test
# ---------------------------------------------------------------------------


def test_example_config_loads() -> None:
    """The bundled examples/entwine.yaml should load without errors."""
    example_path = Path(__file__).parent.parent.parent / "examples" / "entwine.yaml"
    if not example_path.exists():
        pytest.skip("examples/entwine.yaml not present")

    config = load_config(example_path)
    assert len(config.agents) >= 3
    assert config.simulation.name
    assert config.enterprise.name
