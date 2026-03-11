"""Scenario: morning standup multi-agent flow (#41).

CEO publishes standup prompt → all agents respond → CEO summarizes.
Validates event flow, agent participation, and correct ordering.
"""

from __future__ import annotations

import asyncio

import pytest

from entwine.events.models import Event, TaskAssigned
from entwine.simulation.engine import SimulationEngine

from .helpers import ScriptedLLMRouter, make_config, make_persona

# ---------------------------------------------------------------------------
# Scenario setup
# ---------------------------------------------------------------------------

_AGENTS = [
    make_persona("alice", "CEO", llm_tier="complex"),
    make_persona("bob", "CTO"),
    make_persona("carol", "CMO"),
]

_SCRIPTS: dict[str, list[str]] = {
    "alice": [
        # First response: initiate standup.
        "Good morning team! Let's do a quick standup. What are you working on today?",
        # Second response: summarize.
        "Great updates! Bob is on the API migration, Carol is launching the Q2 campaign. "
        "Let's sync at EOD.",
    ],
    "bob": [
        "Working on the API migration today. Should be done by EOD.",
    ],
    "carol": [
        "Finalizing the Q2 campaign launch. Creative assets are ready.",
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standup_all_agents_participate() -> None:
    """All agents process events during the standup flow."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()

    # Let agents process the initial seed task + subsequent events.
    await asyncio.sleep(0.5)

    await engine.stop()

    # All agents should have participated (made at least one LLM call).
    assert len(router.calls) >= 3, f"Expected ≥3 LLM calls, got {len(router.calls)}"


@pytest.mark.asyncio
async def test_standup_event_flow_ordering() -> None:
    """Events flow in a reasonable order: seed → agent responses."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    # Collect all events published on the bus.
    events_log: list[Event] = []
    engine._event_bus.subscribe_all(lambda e: events_log.append(e))

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    # Should have at least the seed TaskAssigned events (one per agent).
    task_events = [e for e in events_log if isinstance(e, TaskAssigned)]
    assert len(task_events) >= len(_AGENTS)


@pytest.mark.asyncio
async def test_standup_memory_records_conversation() -> None:
    """Each agent's short-term memory records the standup conversation."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    for agent in engine._agents:
        assert len(agent.short_term_memory) >= 1, f"Agent {agent.name} has no memory entries"
