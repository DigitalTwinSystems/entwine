"""Integration test: full simulation lifecycle using the example config."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from entsim.agents.models import AgentState
from entsim.config.loader import load_config
from entsim.simulation.engine import SimulationEngine

_EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "examples" / "entsim.yaml"


@pytest.mark.asyncio
async def test_full_simulation_lifecycle() -> None:
    """Load the example config, start the engine, verify agents are running, then stop."""
    config = load_config(_EXAMPLE_CONFIG)
    engine = SimulationEngine(config)

    assert engine.agent_count == len(config.agents)

    await engine.start()
    assert engine.is_running is True

    # Allow agents to enter RUNNING state.
    await asyncio.sleep(0.5)

    # All agents should be running.
    for agent in engine._agents:
        assert agent.state == AgentState.RUNNING, (
            f"Agent {agent.name} in unexpected state {agent.state}"
        )

    await engine.stop()
    assert engine.is_running is False

    # All agents should have cleanly stopped.
    for agent in engine._agents:
        assert agent.state == AgentState.STOPPED, (
            f"Agent {agent.name} did not stop cleanly: {agent.state}"
        )
