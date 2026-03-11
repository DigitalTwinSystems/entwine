"""Scenario: full 12-agent enterprise morning standup (#61).

CEO publishes standup prompt → all 12 agents respond with status updates →
CEO summarizes. Validates participation, event flow, and agent health.
"""

from __future__ import annotations

import asyncio

import pytest

from entwine.agents.base import AgentState
from entwine.config.models import DepartmentConfig, ReportingLine
from entwine.events.models import Event, TaskAssigned
from entwine.simulation.engine import SimulationEngine

from .helpers import ScriptedLLMRouter, make_config, make_persona

# ---------------------------------------------------------------------------
# 12-agent personas
# ---------------------------------------------------------------------------

_AGENTS = [
    # Executive
    make_persona(
        "Alice Chen",
        "CEO",
        llm_tier="complex",
        department="Executive",
        tools=[
            "draft_email",
            "schedule_meeting",
            "read_company_metrics",
            "query_knowledge",
            "delegate_task",
        ],
    ),
    make_persona(
        "Rachel Kim",
        "Head of Operations & HR",
        department="Executive",
        tools=["draft_email", "schedule_meeting", "query_knowledge"],
    ),
    # Engineering
    make_persona(
        "David Park",
        "CTO",
        llm_tier="complex",
        department="Engineering",
        tools=[
            "draft_email",
            "create_github_issue",
            "post_to_slack",
            "query_knowledge",
            "delegate_task",
        ],
    ),
    make_persona(
        "Ben Müller",
        "Senior Software Engineer",
        department="Engineering",
        tools=["draft_email", "create_github_issue", "post_to_slack"],
    ),
    make_persona(
        "Priya Sharma",
        "Software Engineer",
        department="Engineering",
        tools=["draft_email", "create_github_issue", "post_to_slack"],
    ),
    make_persona(
        "Liam O'Brien",
        "DevOps Engineer",
        department="Engineering",
        tools=["draft_email", "create_github_issue", "post_to_slack"],
    ),
    make_persona(
        "Omar Fahd",
        "Data Analyst",
        department="Engineering",
        tools=["draft_email", "read_company_metrics", "post_to_slack"],
    ),
    # Marketing
    make_persona(
        "Sofia Reyes",
        "Head of Marketing",
        department="Marketing",
        tools=["draft_email", "post_to_linkedin", "post_to_x"],
    ),
    make_persona(
        "Nina Petrov",
        "Marketing Specialist",
        department="Marketing",
        llm_tier="routine",
        tools=["draft_email", "post_to_linkedin", "post_to_x"],
    ),
    # Sales
    make_persona(
        "James Rodriguez",
        "Sales Representative",
        department="Sales",
        tools=["draft_email", "read_crm", "update_crm_ticket"],
    ),
    # Product
    make_persona(
        "Mei Wong",
        "Product Manager",
        department="Product",
        tools=["draft_email", "create_github_issue", "schedule_meeting"],
    ),
    # Support
    make_persona(
        "Tariq Hassan",
        "Customer Support Engineer",
        department="Support",
        llm_tier="routine",
        tools=["draft_email", "create_github_issue", "update_crm_ticket"],
    ),
]

_DEPARTMENTS = [
    DepartmentConfig(name="Executive", head="Alice Chen", members=["Alice Chen", "Rachel Kim"]),
    DepartmentConfig(
        name="Engineering",
        head="David Park",
        members=["David Park", "Ben Müller", "Priya Sharma", "Liam O'Brien", "Omar Fahd"],
    ),
    DepartmentConfig(name="Marketing", head="Sofia Reyes", members=["Sofia Reyes", "Nina Petrov"]),
    DepartmentConfig(name="Sales", head="James Rodriguez", members=["James Rodriguez"]),
    DepartmentConfig(name="Product", head="Mei Wong", members=["Mei Wong"]),
    DepartmentConfig(name="Support", head="Tariq Hassan", members=["Tariq Hassan"]),
]

_REPORTING_LINES = [
    ReportingLine(subordinate="David Park", manager="Alice Chen"),
    ReportingLine(subordinate="Sofia Reyes", manager="Alice Chen"),
    ReportingLine(subordinate="Mei Wong", manager="Alice Chen"),
    ReportingLine(subordinate="Rachel Kim", manager="Alice Chen"),
    ReportingLine(subordinate="James Rodriguez", manager="Alice Chen"),
    ReportingLine(subordinate="Tariq Hassan", manager="Alice Chen"),
    ReportingLine(subordinate="Ben Müller", manager="David Park"),
    ReportingLine(subordinate="Priya Sharma", manager="David Park"),
    ReportingLine(subordinate="Liam O'Brien", manager="David Park"),
    ReportingLine(subordinate="Omar Fahd", manager="David Park"),
    ReportingLine(subordinate="Nina Petrov", manager="Sofia Reyes"),
]

# Scripted responses: CEO initiates + summarizes, others give status.
_SCRIPTS: dict[str, list[str]] = {
    "Alice Chen": [
        "Good morning everyone! Let's do our daily standup. Please share your updates.",
        "Great updates team! Engineering is on track with the API migration, marketing "
        "is pushing the Q2 campaign, sales pipeline looks strong. Let's sync again tomorrow.",
    ],
    "Rachel Kim": [
        "Wrapping up the new onboarding docs and scheduling interviews for the SRE role."
    ],
    "David Park": [
        "Reviewing the architecture RFC for the new event system. Will pair with Ben later."
    ],
    "Ben Müller": ["Finishing the API migration. Tests are green, targeting EOD merge."],
    "Priya Sharma": ["Working on the dashboard redesign. Accessibility audit is next."],
    "Liam O'Brien": ["Deploying the new monitoring stack. Alerts should be live by noon."],
    "Omar Fahd": ["Building the weekly metrics dashboard. MRR data looks promising."],
    "Sofia Reyes": ["Finalizing the Q2 campaign launch. Blog post goes live today."],
    "Nina Petrov": ["Scheduling social posts for the campaign launch across LinkedIn and X."],
    "James Rodriguez": ["Following up on 3 enterprise leads. Demo with Acme scheduled for 2 PM."],
    "Mei Wong": [
        "Updating the roadmap after customer interviews. Prioritizing search improvements."
    ],
    "Tariq Hassan": ["Resolving 4 open tickets. Escalated a recurring auth issue to engineering."],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enterprise_standup_all_12_agents_participate() -> None:
    """All 12 agents make at least one LLM call during the standup."""
    config = make_config(
        _AGENTS,
        departments=_DEPARTMENTS,
        reporting_lines=_REPORTING_LINES,
    )
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.8)
    await engine.stop()

    assert engine.agent_count == 12
    assert len(router.calls) >= 12, f"Expected ≥12 LLM calls, got {len(router.calls)}"


@pytest.mark.asyncio
async def test_enterprise_standup_event_flow() -> None:
    """Event bus receives at least one TaskAssigned per agent."""
    config = make_config(
        _AGENTS,
        departments=_DEPARTMENTS,
        reporting_lines=_REPORTING_LINES,
    )
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    events_log: list[Event] = []
    engine._event_bus.subscribe_all(lambda e: events_log.append(e))

    await engine.start()
    await asyncio.sleep(0.8)
    await engine.stop()

    task_events = [e for e in events_log if isinstance(e, TaskAssigned)]
    assert len(task_events) >= 12


@pytest.mark.asyncio
async def test_enterprise_standup_no_agent_errors() -> None:
    """No agent ends up in ERROR state after the standup."""
    config = make_config(
        _AGENTS,
        departments=_DEPARTMENTS,
        reporting_lines=_REPORTING_LINES,
    )
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.8)
    await engine.stop()

    for agent in engine._agents:
        assert agent.state != AgentState.ERROR, f"Agent {agent.name} ended in ERROR state"


@pytest.mark.asyncio
async def test_enterprise_standup_memory_records() -> None:
    """Each agent records at least one memory entry from the standup."""
    config = make_config(
        _AGENTS,
        departments=_DEPARTMENTS,
        reporting_lines=_REPORTING_LINES,
    )
    router = ScriptedLLMRouter(_SCRIPTS)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.8)
    await engine.stop()

    for agent in engine._agents:
        assert len(agent.short_term_memory) >= 1, f"Agent {agent.name} has no memory entries"
