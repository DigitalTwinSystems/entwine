"""Unit tests for agent lifecycle, pause/resume, and supervisor."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from entwine.agents.base import BaseAgent
from entwine.agents.models import AgentPersona, AgentState
from entwine.agents.supervisor import Supervisor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_persona(name: str = "test_agent") -> AgentPersona:
    return AgentPersona(
        name=name,
        role="Tester",
        goal="Verify behaviour",
        backstory="A synthetic agent used in unit tests.",
        llm_tier="standard",
        tools=["tool_a"],
        rag_access=["docs"],
    )


def make_bus() -> asyncio.Queue[Any]:
    return asyncio.Queue()


def make_agent(name: str = "test_agent") -> tuple[BaseAgent, asyncio.Queue[Any]]:
    bus: asyncio.Queue[Any] = make_bus()
    agent = BaseAgent(persona=make_persona(name), event_bus=bus)
    return agent, bus


# ---------------------------------------------------------------------------
# AgentPersona model
# ---------------------------------------------------------------------------


class TestAgentPersona:
    def test_defaults(self) -> None:
        p = AgentPersona(name="cmo", role="CMO", goal="grow", backstory="veteran")
        assert p.llm_tier == "standard"
        assert p.tools == []
        assert p.rag_access == []

    def test_custom_fields(self) -> None:
        p = make_persona("cmo")
        assert p.name == "cmo"
        assert "tool_a" in p.tools
        assert "docs" in p.rag_access


# ---------------------------------------------------------------------------
# AgentState enum
# ---------------------------------------------------------------------------


class TestAgentState:
    def test_all_states_exist(self) -> None:
        expected = {"CREATED", "READY", "RUNNING", "PAUSED", "STOPPED", "ERROR"}
        actual = {s.value for s in AgentState}
        assert expected == actual

    def test_str_value(self) -> None:
        assert AgentState.RUNNING == "RUNNING"


# ---------------------------------------------------------------------------
# BaseAgent construction
# ---------------------------------------------------------------------------


class TestBaseAgentConstruction:
    def test_initial_state_is_ready(self) -> None:
        agent, _ = make_agent()
        assert agent.state == AgentState.READY

    def test_working_memory_empty(self) -> None:
        agent, _ = make_agent()
        assert agent.working_memory == {}

    def test_short_term_memory_empty(self) -> None:
        agent, _ = make_agent()
        assert len(agent.short_term_memory) == 0

    def test_name_from_persona(self) -> None:
        agent, _ = make_agent("alice")
        assert agent.name == "alice"

    def test_persona_property(self) -> None:
        agent, _ = make_agent()
        assert isinstance(agent.persona, AgentPersona)


# ---------------------------------------------------------------------------
# Lifecycle state transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_transitions_to_running() -> None:
    agent, _bus = make_agent()
    assert agent.state == AgentState.READY
    agent.start()
    # Give the event loop a tick so _run() can reach RUNNING.
    await asyncio.sleep(0)
    assert agent.state == AgentState.RUNNING
    await agent.stop()


@pytest.mark.asyncio
async def test_start_requires_ready_state() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="expected READY"):
        agent.start()  # Second call — agent is now RUNNING.
    await agent.stop()


@pytest.mark.asyncio
async def test_stop_transitions_to_stopped() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    await agent.stop()
    assert agent.state == AgentState.STOPPED


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    await agent.stop()
    await agent.stop()  # Second call should not raise.
    assert agent.state == AgentState.STOPPED


# ---------------------------------------------------------------------------
# Pause / resume via asyncio.Event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_transitions_to_paused() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    await agent.pause()
    assert agent.state == AgentState.PAUSED


@pytest.mark.asyncio
async def test_resume_transitions_to_running() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    await agent.pause()
    assert agent.state == AgentState.PAUSED
    await agent.resume()
    assert agent.state == AgentState.RUNNING
    await agent.stop()


@pytest.mark.asyncio
async def test_pause_clears_resume_event() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    await agent.pause()
    assert not agent._resume_event.is_set()


@pytest.mark.asyncio
async def test_resume_sets_resume_event() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    await agent.pause()
    await agent.resume()
    assert agent._resume_event.is_set()
    await agent.stop()


@pytest.mark.asyncio
async def test_pause_ignored_when_not_running() -> None:
    agent, _ = make_agent()
    # Agent is READY — pause should be a no-op.
    await agent.pause()
    assert agent.state == AgentState.READY


@pytest.mark.asyncio
async def test_resume_ignored_when_not_paused() -> None:
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    # Agent is RUNNING — resume should be a no-op.
    await agent.resume()
    assert agent.state == AgentState.RUNNING
    await agent.stop()


# ---------------------------------------------------------------------------
# Short-term memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_term_memory_updated_on_event() -> None:
    agent, bus = make_agent()
    agent.start()
    await asyncio.sleep(0)
    # Post an event so the loop processes one tick.
    await bus.put({"type": "test_event"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(agent.short_term_memory) >= 1
    await agent.stop()


# ---------------------------------------------------------------------------
# Supervisor: start / stop all agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_start_all() -> None:
    agents = [make_agent(f"agent_{i}")[0] for i in range(3)]
    supervisor = Supervisor(agents)
    await supervisor.start_all()
    await asyncio.sleep(0)
    for agent in agents:
        assert agent.state == AgentState.RUNNING
    await supervisor.stop_all()


@pytest.mark.asyncio
async def test_supervisor_stop_all() -> None:
    agents = [make_agent(f"agent_{i}")[0] for i in range(3)]
    supervisor = Supervisor(agents)
    await supervisor.start_all()
    await asyncio.sleep(0)
    await supervisor.stop_all()
    for agent in agents:
        assert agent.state == AgentState.STOPPED


@pytest.mark.asyncio
async def test_supervisor_pause_and_resume_agent() -> None:
    agent, _ = make_agent("worker")
    supervisor = Supervisor([agent])
    await supervisor.start_all()
    await asyncio.sleep(0)
    await supervisor.pause_agent("worker")
    assert agent.state == AgentState.PAUSED
    await supervisor.resume_agent("worker")
    assert agent.state == AgentState.RUNNING
    await supervisor.stop_all()


@pytest.mark.asyncio
async def test_supervisor_unknown_agent_raises() -> None:
    supervisor = Supervisor()
    with pytest.raises(KeyError, match="no_such_agent"):
        await supervisor.pause_agent("no_such_agent")


@pytest.mark.asyncio
async def test_supervisor_duplicate_registration_raises() -> None:
    agent, _ = make_agent("dup")
    supervisor = Supervisor([agent])
    agent2, _ = make_agent("dup")
    with pytest.raises(ValueError, match="already registered"):
        supervisor.register(agent2)
    await supervisor.stop_all()


# ---------------------------------------------------------------------------
# Supervisor: error recovery — skip strategy
# ---------------------------------------------------------------------------


class _FailingAgent(BaseAgent):
    """Agent that raises on its first loop iteration."""

    async def _next_event(self) -> Any | None:
        raise RuntimeError("simulated failure")


@pytest.mark.asyncio
async def test_supervisor_skip_strategy_on_error() -> None:
    bus: asyncio.Queue[Any] = make_bus()
    agent = _FailingAgent(persona=make_persona("failing"), event_bus=bus)
    supervisor = Supervisor([agent], default_recovery="skip")
    await supervisor.start_all()
    # Allow the failing task to complete and the watcher to observe it.
    # The watcher polls every 0.1s, so wait enough for at least one poll.
    await asyncio.sleep(0.5)
    assert agent.state == AgentState.ERROR
    await supervisor.stop_all()


# ---------------------------------------------------------------------------
# Supervisor: error recovery — restart strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_restart_strategy_replaces_agent() -> None:
    bus: asyncio.Queue[Any] = make_bus()
    agent = _FailingAgent(persona=make_persona("failing"), event_bus=bus)
    supervisor = Supervisor([agent], default_recovery="restart")
    await supervisor.start_all()
    # Allow the failing task to complete and the watcher to restart it.
    await asyncio.sleep(0.3)
    # The supervisor should have replaced the agent entry with a new instance
    # that preserves the original subclass.
    new_agent = supervisor._agents["failing"]
    assert new_agent is not agent
    assert isinstance(new_agent, _FailingAgent)
    # The restarted _FailingAgent will also fail, so it may be in ERROR state.
    assert new_agent.state in (
        AgentState.READY,
        AgentState.RUNNING,
        AgentState.STOPPED,
        AgentState.ERROR,
    )
    await supervisor.stop_all()


# ---------------------------------------------------------------------------
# BaseAgent.task_exception — line 115 (returns None when no task or cancelled)
# ---------------------------------------------------------------------------


class TestTaskExceptionProperty:
    def test_returns_none_when_no_task(self) -> None:
        agent, _ = make_agent()
        assert agent.task_exception is None

    @pytest.mark.asyncio
    async def test_returns_none_when_task_cancelled(self) -> None:
        agent, _ = make_agent()
        agent.start()
        await asyncio.sleep(0)
        assert agent._task is not None
        agent._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await agent._task
        assert agent.task_exception is None

    @pytest.mark.asyncio
    async def test_returns_exception_when_task_failed(self) -> None:
        bus: asyncio.Queue[Any] = make_bus()
        agent = _FailingAgent(persona=make_persona("fail_exc"), event_bus=bus)
        agent.start()
        await asyncio.sleep(0.15)
        assert agent.is_task_done
        exc = agent.task_exception
        assert exc is not None
        assert isinstance(exc, RuntimeError)


# ---------------------------------------------------------------------------
# BaseAgent.stop — lines 198-199 (timeout / cancel branch)
# ---------------------------------------------------------------------------


class _HangingAgent(BaseAgent):
    """Agent whose _run loop ignores the stop event."""

    async def _run(self) -> None:
        self._transition(AgentState.RUNNING)
        # Never checks stop_event — will only end via cancellation.
        while True:
            await asyncio.sleep(100)


@pytest.mark.asyncio
async def test_stop_cancels_on_timeout() -> None:
    """When the task doesn't finish within the timeout, stop() should cancel it."""
    bus = make_bus()
    agent = _HangingAgent(persona=make_persona("hang"), event_bus=bus)
    agent.start()
    await asyncio.sleep(0)
    assert agent.state == AgentState.RUNNING
    # Call stop() which will time out waiting for _HangingAgent's infinite loop,
    # triggering the except (TimeoutError, asyncio.CancelledError) branch.
    await agent.stop()
    assert agent.state == AgentState.STOPPED


# ---------------------------------------------------------------------------
# BaseAgent._run — line 215 (break after pause/resume when stop is set)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_exits_after_resume_when_stopped() -> None:
    """The _run loop should break after resume_event.wait() if stop is set."""
    agent, _ = make_agent()
    agent.start()
    await asyncio.sleep(0)
    # Pause the agent so the loop blocks on _resume_event.wait().
    await agent.pause()
    assert agent.state == AgentState.PAUSED
    # Give the loop time to reach the await _resume_event.wait() call.
    await asyncio.sleep(0.15)
    # Now set stop while paused, then unblock the resume.
    agent._stop_event.set()
    agent._resume_event.set()
    # Give the loop a chance to observe stop and break.
    await asyncio.sleep(0.15)
    assert agent._task is not None
    assert agent._task.done()


# ---------------------------------------------------------------------------
# Supervisor: start_all skips non-READY agents — line 81
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_start_all_skips_non_ready() -> None:
    agent, _ = make_agent("skip_me")
    supervisor = Supervisor([agent])
    # Force the agent into STOPPED so it's not READY.
    agent._state = AgentState.STOPPED
    await supervisor.start_all()
    # Agent should still be STOPPED (skipped).
    assert agent.state == AgentState.STOPPED
    await supervisor.stop_all()


# ---------------------------------------------------------------------------
# Supervisor: _recover with "pause" strategy — lines 166-174
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_pause_strategy_on_error() -> None:
    bus: asyncio.Queue[Any] = make_bus()
    agent = _FailingAgent(persona=make_persona("failing_pause"), event_bus=bus)
    supervisor = Supervisor([agent], default_recovery="pause")
    await supervisor.start_all()
    # Wait long enough for the agent to fail and the watcher to observe it.
    await asyncio.sleep(0.5)
    # The agent should be in ERROR state; the "pause" strategy leaves it there.
    assert agent.state == AgentState.ERROR
    await supervisor.stop_all()


# ---------------------------------------------------------------------------
# Supervisor watcher: cancelled task branch (lines 135-136)
# ---------------------------------------------------------------------------


class _NormalAgent(BaseAgent):
    """Agent that completes normally after a short wait."""

    async def _run(self) -> None:
        self._transition(AgentState.RUNNING)
        # Short run then exit normally (no exception).
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_supervisor_watcher_detects_cancelled_task() -> None:
    """Watcher should log and continue when an agent's task is cancelled."""
    agent, _ = make_agent("cancel_me")
    supervisor = Supervisor([agent])
    await supervisor.start_all()
    await asyncio.sleep(0)
    # Cancel the agent's task directly.
    assert agent._task is not None
    agent._task.cancel()
    # Let the watcher detect the cancellation.
    await asyncio.sleep(0.3)
    assert agent.is_task_cancelled
    await supervisor.stop_all()


# ---------------------------------------------------------------------------
# Supervisor watcher: task done without exception (line 139)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_watcher_detects_normal_completion() -> None:
    """Watcher should skip agents whose tasks finished without error."""
    bus = make_bus()
    agent = _NormalAgent(persona=make_persona("normal"), event_bus=bus)
    supervisor = Supervisor([agent])
    await supervisor.start_all()
    # Wait for the agent to complete naturally and the watcher to see it.
    await asyncio.sleep(0.5)
    assert agent.is_task_done
    assert not agent.is_task_cancelled
    assert agent.task_exception is None
    await supervisor.stop_all()
