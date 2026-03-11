"""Scenario: marketing campaign launch workflow (#43).

Sofia (Marketing) drafts a campaign → gets CEO (Alice) approval via event flow →
posts to LinkedIn and X via platform adapters.
Tests multi-step approval workflow and platform adapter calls.
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
    make_persona("alice", "CEO", llm_tier="complex"),
    make_persona("sofia", "Marketing Director", tools=["delegate_task"]),
]

_SCRIPTS: dict[str, list[str]] = {
    "sofia": [
        # Sofia drafts campaign and requests approval.
        "I've drafted the Q2 product launch campaign. Key messages: "
        "innovation, reliability, growth. Target: LinkedIn and X. "
        '<tool_call>{"name": "delegate_task", "arguments": '
        '{"recipient": "alice", "task_description": '
        '"Please approve Q2 campaign: innovation/reliability/growth messaging", '
        '"priority": "high"}}</tool_call>',
        # After approval, sofia would post (simulated).
        "Campaign approved! Posting to LinkedIn and X now.",
    ],
    "alice": [
        # Alice approves.
        "Campaign looks great, Sofia. Approved! Go ahead and launch.",
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_campaign_approval_flow() -> None:
    """Sofia requests approval, Alice responds, both participate."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    # Both agents should have been called.
    assert len(router.calls) >= 2


@pytest.mark.asyncio
async def test_campaign_tool_delegation() -> None:
    """Sofia delegates to alice via tool call."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    sofia = next(a for a in engine._agents if a.name == "sofia")
    tool_ticks = [
        entry
        for entry in sofia.short_term_memory
        if entry.get("tool_results") and len(entry["tool_results"]) > 0
    ]
    assert len(tool_ticks) >= 1, "Sofia should have dispatched delegate_task"


@pytest.mark.asyncio
async def test_campaign_platform_adapters_available() -> None:
    """Platform adapters (linkedin, x) are registered and usable."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    platforms = engine._platform_registry.list_platforms()
    assert "linkedin" in platforms
    assert "x" in platforms

    # Simulate what posting would look like.
    linkedin = engine._platform_registry.get("linkedin")
    result = await linkedin.send("post_update", {"text": "Q2 campaign launch!"})
    assert result["status"] == "ok"

    x_adapter = engine._platform_registry.get("x")
    result = await x_adapter.send("post_tweet", {"text": "Exciting Q2 launch!"})
    assert result["status"] == "ok"

    await engine.stop()


@pytest.mark.asyncio
async def test_campaign_multi_step_memory() -> None:
    """Agents accumulate multi-step conversation in memory."""
    config = make_config(_AGENTS)
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    for agent in engine._agents:
        assert len(agent.short_term_memory) >= 1, f"Agent {agent.name} missing memory entries"
