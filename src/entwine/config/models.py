"""Pydantic models for entwine configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from entwine.agents.models import AgentPersona


class SimulationConfig(BaseModel):
    """Top-level simulation parameters."""

    name: str
    tick_interval_seconds: float = Field(default=60.0, gt=0)
    max_ticks: int | None = Field(default=None, gt=0)
    log_level: str = Field(default="INFO")
    global_budget_usd: float | None = Field(default=None, description="Max total LLM cost (USD).")
    per_agent_budget_usd: float | None = Field(
        default=None, description="Max LLM cost per agent (USD)."
    )


class DepartmentConfig(BaseModel):
    """A department within the enterprise."""

    name: str
    description: str = ""


class EnterpriseConfig(BaseModel):
    """Enterprise structure definition."""

    name: str
    description: str = ""
    departments: list[DepartmentConfig] = Field(default_factory=list)


class FullConfig(BaseModel):
    """Root configuration object combining all sections."""

    simulation: SimulationConfig
    enterprise: EnterpriseConfig
    agents: list[AgentPersona] = Field(default_factory=list)
