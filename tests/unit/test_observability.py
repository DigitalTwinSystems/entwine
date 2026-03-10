"""Unit tests for the observability module (hooks + metrics)."""

from __future__ import annotations

import pytest

from entwine.observability.hooks import HookRegistry
from entwine.observability.metrics import MetricsCollector

# ---------------------------------------------------------------------------
# HookRegistry tests
# ---------------------------------------------------------------------------


class TestHookRegistrySyncCallback:
    """Test registering and emitting with synchronous callbacks."""

    @pytest.mark.asyncio
    async def test_sync_callback_is_called(self) -> None:
        registry = HookRegistry()
        received: list[dict] = []

        def on_start(**kwargs):
            received.append(kwargs)

        registry.register("agent_start", on_start)
        await registry.emit("agent_start", agent="alice")

        assert len(received) == 1
        assert received[0]["agent"] == "alice"


class TestHookRegistryAsyncCallback:
    """Test registering and emitting with async callbacks."""

    @pytest.mark.asyncio
    async def test_async_callback_is_awaited(self) -> None:
        registry = HookRegistry()
        received: list[dict] = []

        async def on_stop(**kwargs):
            received.append(kwargs)

        registry.register("agent_stop", on_stop)
        await registry.emit("agent_stop", agent="bob")

        assert len(received) == 1
        assert received[0]["agent"] == "bob"


class TestHookRegistryUnknownHookType:
    """Emitting an unknown hook type should be a no-op (no error)."""

    @pytest.mark.asyncio
    async def test_unknown_hook_type_is_noop(self) -> None:
        registry = HookRegistry()
        # Should not raise.
        await registry.emit("totally_unknown", foo="bar")


class TestHookRegistryMultipleCallbacks:
    """Multiple callbacks for the same hook type should all fire."""

    @pytest.mark.asyncio
    async def test_multiple_callbacks(self) -> None:
        registry = HookRegistry()
        calls: list[str] = []

        def cb_a(**kwargs):
            calls.append("a")

        async def cb_b(**kwargs):
            calls.append("b")

        registry.register("llm_start", cb_a)
        registry.register("llm_start", cb_b)
        await registry.emit("llm_start")

        assert calls == ["a", "b"]


# ---------------------------------------------------------------------------
# MetricsCollector tests
# ---------------------------------------------------------------------------


class TestMetricsCollectorLLMCall:
    """Test record_llm_call increments counters correctly."""

    def test_record_llm_call(self) -> None:
        mc = MetricsCollector()
        mc.record_llm_call(tier="standard", input_tokens=100, output_tokens=50, cost_usd=0.01)

        assert mc.total_llm_calls == 1
        assert mc.total_input_tokens == 100
        assert mc.total_output_tokens == 50
        assert mc.total_cost_usd == pytest.approx(0.01)
        assert mc.llm_calls_by_tier["standard"] == 1

    def test_record_llm_call_accumulates(self) -> None:
        mc = MetricsCollector()
        mc.record_llm_call(tier="routine", input_tokens=10, output_tokens=5, cost_usd=0.001)
        mc.record_llm_call(tier="routine", input_tokens=20, output_tokens=10, cost_usd=0.002)

        assert mc.total_llm_calls == 2
        assert mc.total_input_tokens == 30
        assert mc.total_output_tokens == 15
        assert mc.total_cost_usd == pytest.approx(0.003)
        assert mc.llm_calls_by_tier["routine"] == 2


class TestMetricsCollectorToolInvocation:
    """Test record_tool_invocation."""

    def test_record_tool_invocation(self) -> None:
        mc = MetricsCollector()
        mc.record_tool_invocation("search")
        mc.record_tool_invocation("execute")

        assert mc.total_tool_invocations == 2


class TestMetricsCollectorError:
    """Test record_error."""

    def test_record_error(self) -> None:
        mc = MetricsCollector()
        mc.record_error("agent_a")
        mc.record_error("agent_a")
        mc.record_error("agent_b")

        assert mc.errors_by_agent["agent_a"] == 2
        assert mc.errors_by_agent["agent_b"] == 1


class TestMetricsCollectorSnapshot:
    """Test snapshot returns a dict with all metrics."""

    def test_snapshot_returns_dict(self) -> None:
        mc = MetricsCollector()
        mc.record_llm_call(tier="complex", input_tokens=500, output_tokens=200, cost_usd=0.05)
        mc.record_tool_invocation("lint")
        mc.record_error("coder")

        snap = mc.snapshot()

        assert isinstance(snap, dict)
        assert snap["total_llm_calls"] == 1
        assert snap["total_input_tokens"] == 500
        assert snap["total_output_tokens"] == 200
        assert snap["total_cost_usd"] == pytest.approx(0.05)
        assert snap["total_tool_invocations"] == 1
        assert snap["errors_by_agent"] == {"coder": 1}
        assert snap["llm_calls_by_tier"] == {"complex": 1}


class TestMetricsCollectorReset:
    """Test reset zeros everything."""

    def test_reset(self) -> None:
        mc = MetricsCollector()
        mc.record_llm_call(tier="standard", input_tokens=100, output_tokens=50, cost_usd=0.01)
        mc.record_tool_invocation("search")
        mc.record_error("agent_x")

        mc.reset()

        assert mc.total_llm_calls == 0
        assert mc.total_input_tokens == 0
        assert mc.total_output_tokens == 0
        assert mc.total_cost_usd == 0.0
        assert mc.total_tool_invocations == 0
        assert mc.errors_by_agent == {}
        assert mc.llm_calls_by_tier == {}
