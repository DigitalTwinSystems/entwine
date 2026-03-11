"""Regression test suite for the simulation engine (#45).

Tests full lifecycle: start → tick → pause → resume → stop.
Validates agent states, event counts, memory, clean shutdown, and edge cases.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from entwine.agents.models import AgentPersona, AgentState
from entwine.config.loader import load_config
from entwine.config.models import EnterpriseConfig, FullConfig, SimulationConfig
from entwine.events.bus import EventBus
from entwine.events.models import SystemEvent
from entwine.llm.models import CompletionResponse, LLMTier
from entwine.simulation.engine import SimulationEngine

_EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "examples" / "entwine.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeLLMRouter:
    """Returns canned responses; tracks call count."""

    def __init__(self, content: str = "ok", cost: float = 0.001) -> None:
        self._content = content
        self._cost = cost
        self.call_count = 0

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        self.call_count += 1
        return CompletionResponse(
            tier=tier,
            model="fake",
            content=self._content,
            input_tokens=10,
            output_tokens=5,
            cost_usd=self._cost,
        )


def _minimal_config(
    *,
    max_ticks: int | None = 5,
    tick_interval: float = 0.01,
    num_agents: int = 2,
    global_budget: float | None = None,
    per_agent_budget: float | None = None,
) -> FullConfig:
    agents = [
        AgentPersona(
            name=f"agent_{i}",
            role=f"Role {i}",
            goal="Test",
            backstory="Test agent",
            llm_tier="standard",
            tools=[],
            rag_access=[],
        )
        for i in range(num_agents)
    ]
    return FullConfig(
        simulation=SimulationConfig(
            name="regression_test",
            tick_interval_seconds=tick_interval,
            max_ticks=max_ticks,
            global_budget_usd=global_budget,
            per_agent_budget_usd=per_agent_budget,
        ),
        enterprise=EnterpriseConfig(name="TestCorp"),
        agents=agents,
    )


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_tick_stop() -> None:
    """Engine starts, ticks, and stops cleanly."""
    config = _minimal_config(max_ticks=3, tick_interval=0.02)
    router = FakeLLMRouter()
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    assert engine.is_running

    # Wait for ticks to complete.
    await asyncio.sleep(0.3)

    await engine.stop()
    assert not engine.is_running

    for agent in engine._agents:
        assert agent.state == AgentState.STOPPED


@pytest.mark.asyncio
async def test_pause_resume_cycle() -> None:
    """Pause suspends agents; resume restores them."""
    config = _minimal_config(max_ticks=None, tick_interval=0.02)
    engine = SimulationEngine(config, llm_router=FakeLLMRouter())  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.1)

    # Pause.
    await engine.pause()
    assert not engine.is_running
    for agent in engine._agents:
        assert agent.state == AgentState.PAUSED

    # Resume.
    await engine.resume()
    assert engine.is_running
    for agent in engine._agents:
        assert agent.state == AgentState.RUNNING

    await engine.stop()


@pytest.mark.asyncio
async def test_agent_states_after_lifecycle() -> None:
    """All agents transition through READY → RUNNING → STOPPED."""
    config = _minimal_config(max_ticks=2, tick_interval=0.01, num_agents=3)
    engine = SimulationEngine(config, llm_router=FakeLLMRouter())  # type: ignore[arg-type]

    # Before start: all READY.
    for agent in engine._agents:
        assert agent.state == AgentState.READY

    await engine.start()
    await asyncio.sleep(0.1)

    for agent in engine._agents:
        assert agent.state == AgentState.RUNNING

    await engine.stop()

    for agent in engine._agents:
        assert agent.state == AgentState.STOPPED


@pytest.mark.asyncio
async def test_event_counts_accumulate() -> None:
    """Events are published and agents accumulate short-term memory."""
    config = _minimal_config(max_ticks=3, tick_interval=0.02, num_agents=1)
    router = FakeLLMRouter()
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.3)
    await engine.stop()

    agent = engine._agents[0]
    # Agent should have processed at least the initial task + some tick events.
    assert len(agent.short_term_memory) >= 1
    # LLM should have been called at least once.
    assert router.call_count >= 1


@pytest.mark.asyncio
async def test_memory_accumulation() -> None:
    """Short-term memory accumulates across ticks."""
    config = _minimal_config(max_ticks=5, tick_interval=0.02, num_agents=1)
    router = FakeLLMRouter()
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.4)
    await engine.stop()

    agent = engine._agents[0]
    # Each processed event adds one entry to short-term memory.
    assert len(agent.short_term_memory) >= 2
    # Each entry has the standard structure.
    for entry in agent.short_term_memory:
        assert "event" in entry
        assert "llm_response" in entry
        assert "tool_results" in entry


@pytest.mark.asyncio
async def test_clean_shutdown_no_leaked_tasks() -> None:
    """After stop, no agent tasks remain running."""
    config = _minimal_config(max_ticks=None, tick_interval=0.02, num_agents=3)
    engine = SimulationEngine(config, llm_router=FakeLLMRouter())  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.1)
    await engine.stop()

    for agent in engine._agents:
        assert agent.is_task_done or agent.state == AgentState.STOPPED
        assert agent.task_exception is None


@pytest.mark.asyncio
async def test_double_stop_is_safe() -> None:
    """Calling stop() twice should not raise."""
    config = _minimal_config(max_ticks=2, tick_interval=0.01)
    engine = SimulationEngine(config, llm_router=FakeLLMRouter())  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.1)
    await engine.stop()
    await engine.stop()  # Should not raise.


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_handles_rapid_publishes() -> None:
    """Event bus handles many events without backpressure failure."""
    bus = EventBus()
    await bus.start()

    received: list[Any] = []
    bus.subscribe_all(lambda event: received.append(event))

    # Publish many events rapidly.
    for i in range(50):
        await bus.publish(
            SystemEvent(
                source_agent="test",
                payload={"tick": i},
            )
        )

    await asyncio.sleep(0.3)
    await bus.stop()

    # All events should have been dispatched.
    assert len(received) == 50


@pytest.mark.asyncio
async def test_engine_with_example_config() -> None:
    """Engine starts correctly with the full example config."""
    config = load_config(_EXAMPLE_CONFIG)
    engine = SimulationEngine(config)

    assert engine.agent_count == len(config.agents)
    await engine.start()
    assert engine.is_running

    await asyncio.sleep(0.2)
    await engine.stop()
    assert not engine.is_running


# ---------------------------------------------------------------------------
# Cost tracking in engine context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_tracking_in_engine() -> None:
    """Engine tracks costs from LLM calls across agents."""
    config = _minimal_config(max_ticks=3, tick_interval=0.02, num_agents=2)
    router = FakeLLMRouter(cost=0.005)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.3)
    await engine.stop()

    snap = engine.cost_tracker.snapshot()
    # At least some costs should have been recorded.
    assert snap["global_cost_usd"] > 0
    assert len(snap["agents"]) >= 1


@pytest.mark.asyncio
async def test_budget_enforcement_pauses_engine() -> None:
    """Engine pauses when global budget is exceeded."""
    config = _minimal_config(
        max_ticks=None,
        tick_interval=0.02,
        num_agents=1,
        global_budget=0.001,
    )
    router = FakeLLMRouter(cost=0.002)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    # Wait for budget to be exceeded and engine to pause.
    await asyncio.sleep(0.5)

    assert engine.cost_tracker.budget_exceeded
    await engine.stop()


@pytest.mark.asyncio
async def test_status_includes_costs() -> None:
    """get_status() includes cost breakdown."""
    config = _minimal_config(max_ticks=2, tick_interval=0.01)
    engine = SimulationEngine(config, llm_router=FakeLLMRouter())  # type: ignore[arg-type]

    status = engine.get_status()
    assert "costs" in status
    assert "global_cost_usd" in status["costs"]
    assert "agents" in status["costs"]
