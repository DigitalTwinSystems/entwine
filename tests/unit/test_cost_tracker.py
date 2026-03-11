"""Unit tests for CostTracker and budget enforcement (#46)."""

from __future__ import annotations

import pytest

from entwine.observability.cost_tracker import BudgetExceeded, CostTracker


class TestRecordCost:
    def test_record_accumulates_global(self) -> None:
        ct = CostTracker()
        ct.record("agent_a", 0.01, input_tokens=100, output_tokens=50)
        ct.record("agent_b", 0.02, input_tokens=200, output_tokens=100)
        assert ct.global_cost == pytest.approx(0.03)

    def test_record_accumulates_per_agent(self) -> None:
        ct = CostTracker()
        ct.record("agent_a", 0.01)
        ct.record("agent_a", 0.02)
        assert ct.agent_cost("agent_a") == pytest.approx(0.03)
        assert ct.agent_cost("unknown") == 0.0


class TestGlobalBudget:
    def test_raises_when_global_budget_exceeded(self) -> None:
        ct = CostTracker(global_budget=0.05)
        ct.record("agent_a", 0.03)
        with pytest.raises(BudgetExceeded, match="global"):
            ct.record("agent_b", 0.03)
        assert ct.budget_exceeded is True
        assert ct.budget_exceeded_scope == "global"

    def test_no_exception_within_budget(self) -> None:
        ct = CostTracker(global_budget=1.0)
        ct.record("agent_a", 0.5)
        assert ct.budget_exceeded is False


class TestPerAgentBudget:
    def test_raises_when_agent_budget_exceeded(self) -> None:
        ct = CostTracker(per_agent_budget=0.10)
        ct.record("agent_a", 0.08)
        with pytest.raises(BudgetExceeded, match="agent:agent_a"):
            ct.record("agent_a", 0.05)
        assert ct.budget_exceeded is True
        assert ct.budget_exceeded_scope == "agent:agent_a"

    def test_other_agents_unaffected(self) -> None:
        ct = CostTracker(per_agent_budget=0.10)
        ct.record("agent_a", 0.08)
        ct.record("agent_b", 0.08)  # Each under budget individually.
        assert ct.budget_exceeded is False


class TestSnapshot:
    def test_snapshot_structure(self) -> None:
        ct = CostTracker(global_budget=1.0, per_agent_budget=0.5)
        ct.record("alice", 0.02, input_tokens=100, output_tokens=50)
        ct.record("bob", 0.03, input_tokens=200, output_tokens=100)

        snap = ct.snapshot()
        assert snap["global_cost_usd"] == pytest.approx(0.05)
        assert snap["global_budget_usd"] == 1.0
        assert snap["per_agent_budget_usd"] == 0.5
        assert snap["budget_exceeded"] is False
        assert "alice" in snap["agents"]
        assert snap["agents"]["alice"]["cost_usd"] == pytest.approx(0.02)
        assert snap["agents"]["alice"]["calls"] == 1
        assert snap["agents"]["alice"]["tokens"]["input"] == 100
        assert snap["agents"]["alice"]["tokens"]["output"] == 50

    def test_snapshot_empty(self) -> None:
        ct = CostTracker()
        snap = ct.snapshot()
        assert snap["global_cost_usd"] == 0.0
        assert snap["agents"] == {}


class TestReset:
    def test_reset_clears_all(self) -> None:
        ct = CostTracker(global_budget=1.0)
        ct.record("agent_a", 0.5)
        ct.reset()
        assert ct.global_cost == 0.0
        assert ct.agent_cost("agent_a") == 0.0
        assert ct.budget_exceeded is False
        assert ct.snapshot()["agents"] == {}


class TestBudgetExceededException:
    def test_exception_attrs(self) -> None:
        exc = BudgetExceeded(scope="global", limit=1.0, actual=1.5)
        assert exc.scope == "global"
        assert exc.limit == 1.0
        assert exc.actual == 1.5
        assert "global" in str(exc)
