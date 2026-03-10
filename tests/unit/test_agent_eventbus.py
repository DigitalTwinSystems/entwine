"""Unit tests for BaseAgent integration with the typed EventBus."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from entwine.agents.base import BaseAgent
from entwine.agents.models import AgentPersona, AgentState
from entwine.events.bus import EventBus
from entwine.events.models import Event, TaskAssigned, TaskCompleted

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persona(name: str = "bus_agent") -> AgentPersona:
    return AgentPersona(
        name=name,
        role="Tester",
        goal="Verify EventBus integration",
        backstory="A synthetic agent used in unit tests.",
    )


def _make_agent_with_typed_bus(
    name: str = "bus_agent",
) -> tuple[BaseAgent, EventBus, asyncio.Queue[Any]]:
    """Create a BaseAgent wired to a typed EventBus."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    bus = EventBus()
    agent = BaseAgent(persona=_persona(name), event_bus=queue, typed_bus=bus)
    return agent, bus, queue


def _make_agent_plain(
    name: str = "plain_agent",
) -> tuple[BaseAgent, asyncio.Queue[Any]]:
    """Create a BaseAgent with only a plain asyncio.Queue (backward compat)."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    agent = BaseAgent(persona=_persona(name), event_bus=queue)
    return agent, queue


# ---------------------------------------------------------------------------
# Property: has_typed_bus
# ---------------------------------------------------------------------------


class TestHasTypedBus:
    def test_true_when_typed_bus_provided(self) -> None:
        agent, _bus, _q = _make_agent_with_typed_bus()
        assert agent.has_typed_bus is True

    def test_false_when_no_typed_bus(self) -> None:
        agent, _q = _make_agent_plain()
        assert agent.has_typed_bus is False


# ---------------------------------------------------------------------------
# Subscribing
# ---------------------------------------------------------------------------


class TestSubscribe:
    def test_subscribe_raises_without_typed_bus(self) -> None:
        agent, _q = _make_agent_plain()
        with pytest.raises(RuntimeError, match="No typed EventBus"):
            agent.subscribe("task_assigned")

    def test_subscribe_all_raises_without_typed_bus(self) -> None:
        agent, _q = _make_agent_plain()
        with pytest.raises(RuntimeError, match="No typed EventBus"):
            agent.subscribe_all()


# ---------------------------------------------------------------------------
# Receiving events through the typed EventBus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_receives_events_via_typed_bus() -> None:
    agent, bus, _q = _make_agent_with_typed_bus()
    agent.subscribe("task_assigned")

    await bus.start()
    agent.start()
    await asyncio.sleep(0)

    event = TaskAssigned(source_agent="ceo", payload={"task": "write report"})
    await bus.publish(event)

    # Allow dispatch loop and agent loop to process.
    await asyncio.sleep(0.2)

    assert len(agent.short_term_memory) >= 1
    recorded = agent.short_term_memory[0]
    assert recorded["event"].id == event.id

    await agent.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_agent_subscribe_all_receives_all_events() -> None:
    agent, bus, _q = _make_agent_with_typed_bus()
    agent.subscribe_all()

    await bus.start()
    agent.start()
    await asyncio.sleep(0)

    e1 = TaskAssigned(source_agent="ceo")
    e2 = TaskCompleted(source_agent="dev1")
    await bus.publish(e1)
    await bus.publish(e2)

    await asyncio.sleep(0.2)

    assert len(agent.short_term_memory) >= 2
    received_ids = {m["event"].id for m in agent.short_term_memory}
    assert e1.id in received_ids
    assert e2.id in received_ids

    await agent.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_agent_subscribe_filters_event_type() -> None:
    agent, bus, _q = _make_agent_with_typed_bus()
    agent.subscribe("task_assigned")

    await bus.start()
    agent.start()
    await asyncio.sleep(0)

    await bus.publish(TaskCompleted(source_agent="dev1"))
    await asyncio.sleep(0.2)

    # The agent subscribed only to task_assigned, so task_completed should not arrive.
    assert len(agent.short_term_memory) == 0

    await agent.stop()
    await bus.stop()


# ---------------------------------------------------------------------------
# Publishing from the agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_publish_goes_through_typed_bus() -> None:
    agent, bus, _q = _make_agent_with_typed_bus()

    received: list[Event] = []
    bus.subscribe_all(lambda e: received.append(e))

    await bus.start()

    event = TaskAssigned(source_agent=agent.name, payload={"task": "do stuff"})
    await agent.publish(event)

    await bus.stop()

    assert len(received) == 1
    assert received[0].id == event.id


@pytest.mark.asyncio
async def test_agent_publish_falls_back_to_plain_queue() -> None:
    agent, queue = _make_agent_plain()

    event = TaskAssigned(source_agent=agent.name, payload={"task": "do stuff"})
    await agent.publish(event)

    assert not queue.empty()
    assert queue.get_nowait().id == event.id


# ---------------------------------------------------------------------------
# Full lifecycle with typed EventBus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_typed_bus_lifecycle() -> None:
    agent, bus, _q = _make_agent_with_typed_bus("lifecycle_agent")
    agent.subscribe_all()

    await bus.start()
    agent.start()
    await asyncio.sleep(0)
    assert agent.state == AgentState.RUNNING

    event = TaskAssigned(source_agent="ceo", payload={"task": "test lifecycle"})
    await bus.publish(event)
    await asyncio.sleep(0.2)

    assert len(agent.short_term_memory) >= 1

    await agent.stop()
    assert agent.state == AgentState.STOPPED

    await bus.stop()


# ---------------------------------------------------------------------------
# Backward compatibility: plain Queue still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backward_compat_plain_queue() -> None:
    agent, queue = _make_agent_plain()
    agent.start()
    await asyncio.sleep(0)

    await queue.put({"type": "legacy_event", "data": 42})
    await asyncio.sleep(0.2)

    assert len(agent.short_term_memory) >= 1
    assert agent.short_term_memory[0]["event"] == {"type": "legacy_event", "data": 42}

    await agent.stop()
