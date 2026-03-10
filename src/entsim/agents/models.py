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


class AgentPersona(BaseModel):
    """Immutable persona configuration loaded from YAML."""

    name: str = Field(..., description="Unique agent identifier (e.g. 'cmo').")
    role: str = Field(
        ..., description="Human-readable role title (e.g. 'Chief Marketing Officer')."
    )
    goal: str = Field(..., description="Primary objective for this agent.")
    backstory: str = Field(..., description="Background context that shapes LLM behaviour.")
    llm_tier: str = Field(
        default="standard",
        description="LiteLLM Router tier key (e.g. 'standard', 'premium').",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Registered tool names available to this agent.",
    )
    rag_access: list[str] = Field(
        default_factory=list,
        description="RAG collection names this agent may query.",
    )
