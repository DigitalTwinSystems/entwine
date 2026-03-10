"""Agent data models: lifecycle states and persona configuration."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AgentState(StrEnum):
    """Lifecycle states for a BaseAgent instance."""

    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class WorkingHours(BaseModel):
    """Working hours window for an agent."""

    start: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="17:00", pattern=r"^\d{2}:\d{2}$")


class AgentPersona(BaseModel):
    """Immutable persona configuration loaded from YAML.

    This is the single canonical persona model used by both
    config loading and the agent runtime.
    """

    name: str = Field(..., description="Unique agent identifier (e.g. 'cmo').")
    role: str = Field(
        ..., description="Human-readable role title (e.g. 'Chief Marketing Officer')."
    )
    department: str = Field(default="", description="Department the agent belongs to.")
    goal: str = Field(..., description="Primary objective for this agent.")
    backstory: str = Field(default="", description="Background context that shapes LLM behaviour.")
    llm_tier: str = Field(
        default="standard",
        description="LiteLLM Router tier key (e.g. 'routine', 'standard', 'complex').",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Registered tool names available to this agent.",
    )
    rag_access: list[str] = Field(
        default_factory=list,
        description="RAG collection names this agent may query.",
    )
    working_hours: WorkingHours = Field(
        default_factory=WorkingHours,
        description="Working hours window for this agent.",
    )
