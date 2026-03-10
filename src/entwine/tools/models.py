"""Pydantic models for tool calls and results."""

from __future__ import annotations

from pydantic import BaseModel


class ToolCall(BaseModel):
    """Represents a single tool invocation request."""

    name: str
    arguments: dict
    call_id: str


class ToolResult(BaseModel):
    """Represents the outcome of a tool invocation."""

    call_id: str
    name: str
    output: str
    error: str | None = None
