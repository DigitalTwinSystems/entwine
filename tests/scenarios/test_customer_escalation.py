"""Scenario: customer escalation cross-agent (#42).

Support agent (tariq) receives a customer issue → escalates to engineering
(ben) via tool call → ben creates a GitHub issue → reports back.
Tests cross-agent delegation and tool dispatch.
"""

from __future__ import annotations

import asyncio

import pytest

from entwine.simulation.engine import SimulationEngine

from .helpers import ScriptedLLMRouter, make_config, make_persona

# ---------------------------------------------------------------------------
# Scenario setup
# ---------------------------------------------------------------------------

_AGENTS = [
    make_persona(
        "tariq",
        "Support Lead",
        tools=["delegate_task"],
    ),
    make_persona(
        "ben",
        "Engineering Lead",
        tools=["delegate_task", "query_knowledge"],
    ),
]

_SCRIPTS: dict[str, list[str]] = {
    "tariq": [
        # Tariq escalates via tool call.
        "I need to escalate this to engineering. "
        '<tool_call>{"name": "delegate_task", "arguments": '
        '{"recipient": "ben", "task_description": "Customer reports payment processing failure", '
        '"priority": "high"}}</tool_call>',
    ],
    "ben": [
        "I'll investigate the payment processing issue and create a tracking issue.",
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalation_triggers_tool_call() -> None:
    """Tariq's escalation generates a delegate_task tool call."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    # Tariq should have invoked delegate_task via tool_call XML.
    tariq = next(a for a in engine._agents if a.name == "tariq")
    tool_ticks = [
        entry
        for entry in tariq.short_term_memory
        if entry.get("tool_results") and len(entry["tool_results"]) > 0
    ]
    assert len(tool_ticks) >= 1, "Tariq should have dispatched at least one tool call"
    assert tool_ticks[0]["tool_results"][0].name == "delegate_task"


@pytest.mark.asyncio
async def test_both_agents_process_events() -> None:
    """Both tariq and ben process events during escalation."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    for agent in engine._agents:
        assert len(agent.short_term_memory) >= 1, (
            f"Agent {agent.name} should have processed at least one event"
        )


@pytest.mark.asyncio
async def test_escalation_event_reaches_ben() -> None:
    """Ben receives events (seed task + any delegated events)."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    # Track events ben receives.

    await engine.start()

    ben = next(a for a in engine._agents if a.name == "ben")
    # Ben should have been seeded with at least the initial task.
    await asyncio.sleep(0.5)
    await engine.stop()

    assert len(ben.short_term_memory) >= 1
    # Check that ben made an LLM call.
    ben_calls = [c for c in router.calls if c["agent"] == "ben"]
    assert len(ben_calls) >= 1
