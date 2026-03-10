"""Pydantic models for entsim configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from entsim.agents.models import AgentPersona


class SimulationConfig(BaseModel):
    """Top-level simulation parameters."""

    name: str
    tick_interval_seconds: float = Field(default=60.0, gt=0)
    max_ticks: int | None = Field(default=None, gt=0)
    log_level: str = Field(default="INFO")


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
