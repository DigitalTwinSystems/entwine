"""Pydantic models for entsim configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class WorkingHours(BaseModel):
    """Working hours window for an agent."""

    start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")


class AgentPersona(BaseModel):
    """Persona definition for a single simulated agent."""

    name: str
    role: str
    department: str
    goal: str
    backstory: str = ""
    llm_tier: str = Field(default="standard")
    tools: list[str] = Field(default_factory=list)
    rag_access: list[str] = Field(default_factory=list)
    working_hours: WorkingHours = Field(default_factory=WorkingHours)


class FullConfig(BaseModel):
    """Root configuration object combining all sections."""

    simulation: SimulationConfig
    enterprise: EnterpriseConfig
    agents: list[AgentPersona] = Field(default_factory=list)
