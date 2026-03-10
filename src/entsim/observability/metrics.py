"""MetricsCollector: in-memory counters for LLM calls, tools, and errors."""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


class MetricsCollector:
    """Lightweight in-memory metrics store.

    Designed for single-threaded asyncio use — no locking required.
    """

    def __init__(self) -> None:
        self.total_llm_calls: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.total_tool_invocations: int = 0
        self.errors_by_agent: dict[str, int] = {}
        self.llm_calls_by_tier: dict[str, int] = {}

    def record_llm_call(
        self,
        tier: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Record a single LLM completion call."""
        self.total_llm_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost_usd
        self.llm_calls_by_tier[tier] = self.llm_calls_by_tier.get(tier, 0) + 1
        log.debug(
            "metrics.llm_call",
            tier=tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    def record_tool_invocation(self, tool_name: str) -> None:
        """Record a tool invocation."""
        self.total_tool_invocations += 1
        log.debug("metrics.tool_invocation", tool_name=tool_name)

    def record_error(self, agent_name: str) -> None:
        """Record an error for a specific agent."""
        self.errors_by_agent[agent_name] = self.errors_by_agent.get(agent_name, 0) + 1
        log.debug("metrics.error", agent_name=agent_name)

    def snapshot(self) -> dict[str, Any]:
        """Return current metrics as a plain dictionary."""
        return {
            "total_llm_calls": self.total_llm_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_tool_invocations": self.total_tool_invocations,
            "errors_by_agent": dict(self.errors_by_agent),
            "llm_calls_by_tier": dict(self.llm_calls_by_tier),
        }

    def reset(self) -> None:
        """Zero all counters and clear all dictionaries."""
        self.total_llm_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.total_tool_invocations = 0
        self.errors_by_agent.clear()
        self.llm_calls_by_tier.clear()
        log.debug("metrics.reset")
