"""Unit tests for the SimulationEngine orchestrator."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from entsim.agents.models import AgentPersona, AgentState
from entsim.agents.standard import StandardAgent
from entsim.config.models import EnterpriseConfig, FullConfig, SimulationConfig
from entsim.simulation.engine import SimulationEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_config(**overrides: Any) -> FullConfig:
    """Build a minimal FullConfig suitable for engine tests."""
    defaults: dict[str, Any] = {
        "simulation": SimulationConfig(name="test-sim", tick_interval_seconds=0.05),
        "enterprise": EnterpriseConfig(name="TestCo"),
        "agents": [],
    }
    defaults.update(overrides)
    return FullConfig(**defaults)


def _persona(**overrides: Any) -> AgentPersona:
    defaults: dict[str, Any] = {
        "name": "agent_a",
        "role": "Tester",
        "goal": "Test things",
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_from_minimal_config(self) -> None:
        config = _minimal_config()
        engine = SimulationEngine(config)
        assert engine.agent_count == 0
        assert engine.elapsed_ticks == 0
        assert engine.is_running is False

    def test_creates_correct_number_of_agents(self) -> None:
        agents = [
            _persona(name="alice", role="CEO", goal="Lead"),
            _persona(name="bob", role="Engineer", goal="Build"),
        ]
        config = _minimal_config(agents=agents)
        engine = SimulationEngine(config)
        assert engine.agent_count == 2

    def test_agents_are_standard_agents(self) -> None:
        agents = [
            _persona(name="alice", role="CEO", goal="Lead"),
            _persona(name="bob", role="Engineer", goal="Build"),
        ]
        config = _minimal_config(agents=agents)
        engine = SimulationEngine(config)
        for agent in engine._agents:
            assert isinstance(agent, StandardAgent)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        config = _minimal_config()
        engine = SimulationEngine(config)

        await engine.start()
        assert engine.is_running is True

        await engine.stop()
        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_start_stop_with_agents(self) -> None:
        agents = [
            _persona(name="alice", role="CEO", goal="Lead"),
            _persona(name="bob", role="Engineer", goal="Build"),
        ]
        config = _minimal_config(agents=agents)
        engine = SimulationEngine(config)

        await engine.start()
        assert engine.is_running is True

        # Give agents a moment to enter RUNNING state.
        await asyncio.sleep(0.05)

        for agent in engine._agents:
            assert agent.state == AgentState.RUNNING

        await engine.stop()
        assert engine.is_running is False

        for agent in engine._agents:
            assert agent.state == AgentState.STOPPED


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    @pytest.mark.asyncio
    async def test_pause_resume(self) -> None:
        config = _minimal_config()
        engine = SimulationEngine(config)

        await engine.start()
        assert engine.is_running is True

        await engine.pause()
        assert engine.is_running is False

        await engine.resume()
        assert engine.is_running is True

        await engine.stop()

    @pytest.mark.asyncio
    async def test_pause_resume_with_agents(self) -> None:
        agents = [_persona(name="alice", role="CEO", goal="Lead")]
        config = _minimal_config(agents=agents)
        engine = SimulationEngine(config)

        await engine.start()
        await asyncio.sleep(0.05)

        await engine.pause()
        for agent in engine._agents:
            assert agent.state == AgentState.PAUSED

        await engine.resume()
        await asyncio.sleep(0.05)
        for agent in engine._agents:
            assert agent.state == AgentState.RUNNING

        await engine.stop()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_get_status_keys(self) -> None:
        config = _minimal_config()
        engine = SimulationEngine(config)

        status = engine.get_status()
        assert "simulation_name" in status
        assert "is_running" in status
        assert "elapsed_ticks" in status
        assert "agent_count" in status
        assert "agents" in status
        assert "clock" in status
        assert "platforms" in status

    def test_status_reflects_config(self) -> None:
        config = _minimal_config()
        engine = SimulationEngine(config)

        status = engine.get_status()
        assert status["simulation_name"] == "test-sim"
        assert status["agent_count"] == 0
        assert status["is_running"] is False


# ---------------------------------------------------------------------------
# World state
# ---------------------------------------------------------------------------


class TestWorldState:
    def test_world_state_accessible(self) -> None:
        config = _minimal_config()
        engine = SimulationEngine(config)

        assert isinstance(engine.world_state, dict)
        engine.world_state["key"] = "value"
        assert engine.world_state["key"] == "value"
