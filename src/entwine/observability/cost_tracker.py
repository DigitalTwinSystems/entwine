"""CostTracker: per-agent and global LLM cost tracking with budget enforcement."""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


class BudgetExceeded(Exception):
    """Raised when a cost budget limit is exceeded."""

    def __init__(self, scope: str, limit: float, actual: float) -> None:
        self.scope = scope
        self.limit = limit
        self.actual = actual
        super().__init__(f"Budget exceeded for {scope}: ${actual:.4f} > ${limit:.4f}")


class CostTracker:
    """Track cumulative LLM costs per agent and enforce budget limits.

    Thread-safety: single-threaded asyncio — no locking needed.
    """

    def __init__(
        self,
        *,
        global_budget: float | None = None,
        per_agent_budget: float | None = None,
    ) -> None:
        self._global_budget = global_budget
        self._per_agent_budget = per_agent_budget
        self._global_cost: float = 0.0
        self._agent_costs: dict[str, float] = {}
        self._agent_calls: dict[str, int] = {}
        self._agent_tokens: dict[str, dict[str, int]] = {}
        self._budget_exceeded: bool = False
        self._budget_exceeded_scope: str | None = None

    @property
    def global_cost(self) -> float:
        return self._global_cost

    @property
    def budget_exceeded(self) -> bool:
        return self._budget_exceeded

    @property
    def budget_exceeded_scope(self) -> str | None:
        return self._budget_exceeded_scope

    def record(
        self,
        agent_name: str,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record an LLM call cost. Raises BudgetExceeded if limit breached."""
        self._global_cost += cost_usd
        self._agent_costs[agent_name] = self._agent_costs.get(agent_name, 0.0) + cost_usd
        self._agent_calls[agent_name] = self._agent_calls.get(agent_name, 0) + 1

        tokens = self._agent_tokens.setdefault(agent_name, {"input": 0, "output": 0})
        tokens["input"] += input_tokens
        tokens["output"] += output_tokens

        log.debug(
            "cost_tracker.record",
            agent=agent_name,
            cost_usd=cost_usd,
            global_total=self._global_cost,
        )

        # Check per-agent budget.
        if self._per_agent_budget is not None:
            agent_total = self._agent_costs[agent_name]
            if agent_total > self._per_agent_budget:
                self._budget_exceeded = True
                self._budget_exceeded_scope = f"agent:{agent_name}"
                raise BudgetExceeded(
                    scope=f"agent:{agent_name}",
                    limit=self._per_agent_budget,
                    actual=agent_total,
                )

        # Check global budget.
        if self._global_budget is not None and self._global_cost > self._global_budget:
            self._budget_exceeded = True
            self._budget_exceeded_scope = "global"
            raise BudgetExceeded(
                scope="global",
                limit=self._global_budget,
                actual=self._global_cost,
            )

    def agent_cost(self, agent_name: str) -> float:
        """Return cumulative cost for a specific agent."""
        return self._agent_costs.get(agent_name, 0.0)

    def snapshot(self) -> dict[str, Any]:
        """Return cost breakdown as a dict for the status endpoint."""
        return {
            "global_cost_usd": round(self._global_cost, 6),
            "global_budget_usd": self._global_budget,
            "per_agent_budget_usd": self._per_agent_budget,
            "budget_exceeded": self._budget_exceeded,
            "budget_exceeded_scope": self._budget_exceeded_scope,
            "agents": {
                name: {
                    "cost_usd": round(cost, 6),
                    "calls": self._agent_calls.get(name, 0),
                    "tokens": self._agent_tokens.get(name, {"input": 0, "output": 0}),
                }
                for name, cost in sorted(self._agent_costs.items())
            },
        }

    def reset(self) -> None:
        """Zero all tracked costs."""
        self._global_cost = 0.0
        self._agent_costs.clear()
        self._agent_calls.clear()
        self._agent_tokens.clear()
        self._budget_exceeded = False
        self._budget_exceeded_scope = None
        log.debug("cost_tracker.reset")
