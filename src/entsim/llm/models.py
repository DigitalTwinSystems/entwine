"""LLM domain models: tier enum, request and response types."""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class LLMTier(enum.StrEnum):
    """Model tier controlling cost/quality trade-off per request."""

    ROUTINE = "routine"
    STANDARD = "standard"
    COMPLEX = "complex"


class CompletionRequest(BaseModel):
    """Parameters for a single LLM completion call."""

    tier: LLMTier
    messages: list[dict[str, Any]] = Field(..., min_length=1)
    tools: list[dict[str, Any]] | None = None


class CompletionResponse(BaseModel):
    """Parsed result of a single LLM completion call."""

    tier: LLMTier
    model: str
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
