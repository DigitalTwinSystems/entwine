"""End-to-end integration tests for the agent loop, EventBus, tools, clock, and platforms."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from entwine.agents.models import AgentPersona, AgentState, WorkingHours
from entwine.agents.standard import StandardAgent
from entwine.events.bus import EventBus
from entwine.events.models import TaskAssigned
from entwine.llm.models import CompletionResponse, LLMTier
from entwine.platforms.registry import PlatformRegistry
from entwine.platforms.stubs import SlackAdapter, XAdapter
from entwine.simulation.clock import SimulationClock
from entwine.tools.dispatcher import ToolDispatcher

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _persona(**overrides: Any) -> AgentPersona:
    defaults: dict[str, Any] = {
        "name": "test_agent",
        "role": "Tester",
        "goal": "Verify behaviour",
        "backstory": "Synthetic agent for tests.",
        "llm_tier": "standard",
        "tools": [],
        "rag_access": [],
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


class FakeLLMRouter:
    """Returns predefined responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        content = next(self._responses, "")
        return CompletionResponse(
            tier=tier,
            model="fake",
            content=content,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# a) Single agent processes an event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_agent_processes_event() -> None:
    """Start a single agent, push an event, verify memory and bus output."""
    bus: asyncio.Queue[Any] = asyncio.Queue()
    router = FakeLLMRouter(["I'll handle this task"])
    agent = StandardAgent(
        persona=_persona(),
        event_bus=bus,
        llm_router=router,  # type: ignore[arg-type]
    )

    agent.start()
    await asyncio.sleep(0)

    # Push an event for the agent to process.
    await bus.put({"type": "task_assigned", "payload": "do something"})

    # Give the agent time to process.
    await asyncio.sleep(0.2)

    await agent.stop()
    assert agent.state == AgentState.STOPPED

    # Verify short-term memory recorded the tick.
    assert len(agent.short_term_memory) >= 1
    first_tick = agent.short_term_memory[0]
    assert first_tick["llm_response"] is not None
    assert first_tick["llm_response"].content == "I'll handle this task"

    # The agent emitted an agent_message back onto the bus (which the agent
    # itself may have consumed in a subsequent tick).  Verify by checking that
    # at least one memory entry was generated from the LLM call.
    llm_contents = [
        t["llm_response"].content
        for t in agent.short_term_memory
        if t.get("llm_response") is not None and t["llm_response"].content
    ]
    assert "I'll handle this task" in llm_contents


# ---------------------------------------------------------------------------
# b) Two agents communicate via EventBus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_agents_communicate_via_eventbus() -> None:
    """Two agents on the same EventBus: A receives a task, emits a response that B picks up."""
    event_bus = EventBus()

    # BaseAgent accepts typed_bus but StandardAgent does not forward it,
    # so we construct via BaseAgent.__init__ path by using a thin wrapper.
    queue_a: asyncio.Queue[Any] = asyncio.Queue()
    queue_b: asyncio.Queue[Any] = asyncio.Queue()

    agent_a = StandardAgent(
        persona=_persona(name="agent_a"),
        event_bus=queue_a,
        llm_router=FakeLLMRouter(["Task received, responding now"]),  # type: ignore[arg-type]
    )
    # Manually wire up the typed bus (BaseAgent supports it but StandardAgent
    # doesn't expose the kwarg).
    agent_a._typed_bus = event_bus
    agent_a._inbox = asyncio.Queue()

    agent_b = StandardAgent(
        persona=_persona(name="agent_b"),
        event_bus=queue_b,
        llm_router=FakeLLMRouter(["Got agent_a's message"]),  # type: ignore[arg-type]
    )
    agent_b._typed_bus = event_bus
    agent_b._inbox = asyncio.Queue()
    # Agent A subscribes to task_assigned events.
    agent_a.subscribe("task_assigned")
    # Agent B subscribes to all events so it can pick up anything agent A emits.
    agent_b.subscribe_all()

    await event_bus.start()
    agent_a.start()
    agent_b.start()

    # Publish a TaskAssigned event to kick things off.
    await event_bus.publish(
        TaskAssigned(source_agent="orchestrator", payload={"task": "write report"})
    )

    # Allow time for the bus dispatch and both agents to process.
    await asyncio.sleep(0.2)

    # Agent A should have processed the TaskAssigned event.
    assert len(agent_a.short_term_memory) >= 1

    # Agent B should have received at least the TaskAssigned event (it subscribed to all).
    assert len(agent_b.short_term_memory) >= 1

    await agent_a.stop()
    await agent_b.stop()
    await event_bus.stop()


# ---------------------------------------------------------------------------
# c) Agent with tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_with_tools() -> None:
    """Agent receives LLM response containing a tool_call XML block; tool is dispatched."""
    bus: asyncio.Queue[Any] = asyncio.Queue()

    # Register a simple tool on the dispatcher.
    dispatcher = ToolDispatcher()
    dispatcher.register(
        name="greet",
        handler=lambda name: f"Hello, {name}!",
        description="Greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}},
    )

    # LLM returns content with a tool_call XML block.
    tool_call_content = '<tool_call>{"name": "greet", "arguments": {"name": "Alice"}}</tool_call>'
    router = FakeLLMRouter([tool_call_content])

    agent = StandardAgent(
        persona=_persona(tools=["greet"]),
        event_bus=bus,
        llm_router=router,  # type: ignore[arg-type]
        tool_dispatcher=dispatcher,  # type: ignore[arg-type]
    )

    agent.start()
    await asyncio.sleep(0)

    await bus.put({"type": "task_assigned", "payload": "greet Alice"})
    await asyncio.sleep(0.2)

    # Verify the tool was dispatched and result recorded in memory.
    assert len(agent.short_term_memory) >= 1
    first_tick = agent.short_term_memory[0]
    tool_results = first_tick["tool_results"]
    assert len(tool_results) == 1
    assert tool_results[0].name == "greet"
    assert "Hello, Alice!" in tool_results[0].output

    await agent.stop()


# ---------------------------------------------------------------------------
# d) SimulationClock working hours
# ---------------------------------------------------------------------------


def test_simulation_clock_working_hours() -> None:
    """Verify that SimulationClock.is_within_working_hours filters correctly."""
    working_hours = WorkingHours(start="09:00", end="17:00")

    # Clock starting at 09:00 should be within working hours.
    clock = SimulationClock(start_hour=9.0, tick_interval_seconds=3600.0)
    clock.start()
    assert clock.is_within_working_hours(working_hours) is True

    # Advance to 17:00 (8 ticks of 1 hour each).
    for _ in range(8):
        clock.tick()
    assert clock.is_within_working_hours(working_hours) is False

    # Clock starting at 08:00 (before working hours) — still within at 09:00
    # after one tick.
    clock2 = SimulationClock(start_hour=8.0, tick_interval_seconds=3600.0)
    clock2.start()
    assert clock2.is_within_working_hours(working_hours) is False
    clock2.tick()  # now 09:00
    assert clock2.is_within_working_hours(working_hours) is True


# ---------------------------------------------------------------------------
# e) Platform adapter integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_adapter_integration() -> None:
    """Register platform stubs, wire them into ToolDispatcher, dispatch an action."""
    registry = PlatformRegistry()
    x_adapter = XAdapter()
    slack_adapter = SlackAdapter()
    registry.register(x_adapter)
    registry.register(slack_adapter)

    assert "x" in registry.list_platforms()
    assert "slack" in registry.list_platforms()

    # Wire platform send into the ToolDispatcher.
    dispatcher = ToolDispatcher()

    for platform_name in registry.list_platforms():
        adapter = registry.get(platform_name)
        dispatcher.register(
            name=f"{platform_name}_send",
            handler=adapter.send,
            description=f"Send action on {platform_name}",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "payload": {"type": "object"},
                },
            },
        )

    # Dispatch through the tool system.
    from entwine.tools.models import ToolCall

    result = await dispatcher.dispatch(
        ToolCall(
            call_id="tc1",
            name="x_send",
            arguments={"action": "post_tweet", "payload": {"text": "Hello world"}},
        )
    )
    assert result.error is None
    assert "ok" in result.output
    assert "simulated" in result.output

    result_slack = await dispatcher.dispatch(
        ToolCall(
            call_id="tc2",
            name="slack_send",
            arguments={"action": "send_message", "payload": {"text": "Hi team"}},
        )
    )
    assert result_slack.error is None
    assert "ok" in result_slack.output
