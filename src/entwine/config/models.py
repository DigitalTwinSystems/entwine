"""Pydantic models for entwine configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from entwine.agents.models import AgentPersona
from entwine.rag.settings import RAGSettings


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
    max_coder_agents: int = Field(
        default=2, gt=0, description="Max concurrent coder agent sessions."
    )


class DepartmentConfig(BaseModel):
    """A department within the enterprise."""

    name: str
    description: str = ""
    head: str = ""
    members: list[str] = Field(default_factory=list)


class ReportingLine(BaseModel):
    """A manager-subordinate reporting relationship."""

    subordinate: str
    manager: str


class EnterpriseConfig(BaseModel):
    """Enterprise structure definition."""

    name: str
    description: str = ""
    departments: list[DepartmentConfig] = Field(default_factory=list)
    reporting_lines: list[ReportingLine] = Field(default_factory=list)
    cross_department_channels: list[str] = Field(
        default_factory=lambda: ["email", "slack"],
    )


class FullConfig(BaseModel):
    """Root configuration object combining all sections."""

    simulation: SimulationConfig
    enterprise: EnterpriseConfig
    agents: list[AgentPersona] = Field(default_factory=list)
    rag: RAGSettings | None = Field(default=None)
