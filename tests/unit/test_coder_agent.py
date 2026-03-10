"""Unit tests for CoderAgent with fake dependencies."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from entwine.agents.coder import CoderAgent
from entwine.agents.coder_models import CodingTaskResult, SandboxSession
from entwine.agents.models import AgentPersona, AgentState

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _persona(**overrides: Any) -> AgentPersona:
    defaults: dict[str, Any] = {
        "name": "coder_agent",
        "role": "Developer",
        "goal": "Write and test code",
        "backstory": "Autonomous coding agent.",
        "llm_tier": "complex",
        "tools": [],
        "rag_access": [],
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


def _bus() -> asyncio.Queue[Any]:
    return asyncio.Queue()


class FakeCommandResult:
    """Minimal command result matching the CommandResult protocol."""

    def __init__(
        self,
        stdout: str = "ok",
        stderr: str = "",
        exit_code: int = 0,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


class FakeSandbox:
    """Fake sandbox that records commands and stores files in-memory."""

    def __init__(self) -> None:
        self.commands_run: list[str] = []
        self.files: dict[str, str] = {}
        self.killed: bool = False
        self._command_result = FakeCommandResult()

    def set_command_result(self, result: FakeCommandResult) -> None:
        self._command_result = result

    async def run_command(self, cmd: str) -> FakeCommandResult:
        self.commands_run.append(cmd)
        return self._command_result

    async def write_file(self, path: str, content: str) -> None:
        self.files[path] = content

    async def read_file(self, path: str) -> str:
        return self.files.get(path, "")

    async def kill(self) -> None:
        self.killed = True


class FakeSandboxProvider:
    """Fake provider that returns a pre-configured FakeSandbox."""

    def __init__(self) -> None:
        self.sandbox = FakeSandbox()

    async def create(self) -> FakeSandbox:
        return self.sandbox


class FakeSDKSession:
    """Fake SDK session that yields pre-configured chunks."""

    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self._chunks = chunks or [{"content": "print('hello')", "tokens": 50}]

    async def query(self, prompt: str) -> AsyncIterator[dict[str, Any]]:
        for chunk in self._chunks:
            yield chunk


def _sdk_factory(
    chunks: list[dict[str, Any]] | None = None,
) -> Any:
    """Return a factory callable that produces FakeSDKSession instances."""
    session = FakeSDKSession(chunks)

    def factory() -> FakeSDKSession:
        return session

    return factory


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_no_deps(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        assert agent.state == AgentState.READY
        assert not agent.has_sandbox
        assert not agent.has_sdk
        assert agent.session_tokens_used == 0

    def test_with_all_deps(self) -> None:
        provider = FakeSandboxProvider()
        factory = _sdk_factory()
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            sandbox_provider=provider,  # type: ignore[arg-type]
            agent_sdk_factory=factory,
            repo_url="https://github.com/example/repo",
            max_tokens_per_session=50_000,
        )
        assert agent.has_sandbox
        assert agent.has_sdk
        assert agent._repo_url == "https://github.com/example/repo"
        assert agent._max_tokens_per_session == 50_000


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_has_sandbox_false_when_none(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        assert agent.has_sandbox is False

    def test_has_sandbox_true_when_provided(self) -> None:
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            sandbox_provider=FakeSandboxProvider(),  # type: ignore[arg-type]
        )
        assert agent.has_sandbox is True

    def test_has_sdk_false_when_none(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        assert agent.has_sdk is False

    def test_has_sdk_true_when_provided(self) -> None:
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            agent_sdk_factory=_sdk_factory(),
        )
        assert agent.has_sdk is True


# ---------------------------------------------------------------------------
# _execute_in_sandbox
# ---------------------------------------------------------------------------


class TestExecuteInSandbox:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_sandbox(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        result = await agent._execute_in_sandbox("echo hello")
        assert "[error]" in result
        assert "No sandbox provider" in result

    @pytest.mark.asyncio
    async def test_runs_command_in_sandbox(self) -> None:
        provider = FakeSandboxProvider()
        provider.sandbox.set_command_result(
            FakeCommandResult(stdout="hello world", stderr="", exit_code=0)
        )
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            sandbox_provider=provider,  # type: ignore[arg-type]
        )
        result = await agent._execute_in_sandbox("echo hello")
        assert result == "hello world"
        assert provider.sandbox.commands_run == ["echo hello"]

    @pytest.mark.asyncio
    async def test_returns_stderr_on_failure(self) -> None:
        provider = FakeSandboxProvider()
        provider.sandbox.set_command_result(
            FakeCommandResult(stdout="", stderr="command not found", exit_code=127)
        )
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            sandbox_provider=provider,  # type: ignore[arg-type]
        )
        result = await agent._execute_in_sandbox("bad_command")
        assert "[exit 127]" in result
        assert "command not found" in result

    @pytest.mark.asyncio
    async def test_reuses_sandbox_instance(self) -> None:
        provider = FakeSandboxProvider()
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            sandbox_provider=provider,  # type: ignore[arg-type]
        )
        await agent._execute_in_sandbox("cmd1")
        await agent._execute_in_sandbox("cmd2")
        assert provider.sandbox.commands_run == ["cmd1", "cmd2"]


# ---------------------------------------------------------------------------
# _call_llm (SDK integration)
# ---------------------------------------------------------------------------


class TestCallLlm:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_sdk(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        result = await agent._call_llm({"type": "test"}, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_content_from_sdk(self) -> None:
        chunks = [
            {"content": "line1\n", "tokens": 20},
            {"content": "line2\n", "tokens": 30},
        ]
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            agent_sdk_factory=_sdk_factory(chunks),
        )
        result = await agent._call_llm({"type": "task"}, [])
        assert result == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_tracks_token_usage(self) -> None:
        chunks = [
            {"content": "a", "tokens": 30},
            {"content": "b", "tokens": 20},
        ]
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            agent_sdk_factory=_sdk_factory(chunks),
        )
        await agent._call_llm({"type": "task"}, [])
        assert agent.session_tokens_used == 50


# ---------------------------------------------------------------------------
# Token budget enforcement
# ---------------------------------------------------------------------------


class TestTokenBudget:
    @pytest.mark.asyncio
    async def test_stops_when_budget_exceeded_before_call(self) -> None:
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            agent_sdk_factory=_sdk_factory(),
            max_tokens_per_session=10,
        )
        # Manually set tokens to exceed budget.
        agent._session_tokens_used = 10
        result = await agent._call_llm({"type": "task"}, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_stops_mid_stream_when_budget_hit(self) -> None:
        chunks = [
            {"content": "a", "tokens": 60},
            {"content": "b", "tokens": 60},
            {"content": "c", "tokens": 60},
        ]
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            agent_sdk_factory=_sdk_factory(chunks),
            max_tokens_per_session=100,
        )
        result = await agent._call_llm({"type": "task"}, [])
        # Should have stopped after consuming >= 100 tokens.
        assert agent.session_tokens_used >= 100
        # Should not have consumed all 180 tokens (stopped mid-stream).
        assert agent.session_tokens_used < 180
        # Should still return partial content.
        assert result is not None


# ---------------------------------------------------------------------------
# _handle_task_assigned
# ---------------------------------------------------------------------------


class TestHandleTaskAssigned:
    @pytest.mark.asyncio
    async def test_produces_coding_task_result_with_sdk_and_sandbox(self) -> None:
        provider = FakeSandboxProvider()
        provider.sandbox.set_command_result(
            FakeCommandResult(stdout="src/main.py\nsrc/utils.py", exit_code=0)
        )
        chunks = [{"content": "echo done", "tokens": 10}]
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
            sandbox_provider=provider,  # type: ignore[arg-type]
            agent_sdk_factory=_sdk_factory(chunks),
        )

        event = {"type": "task_assigned", "payload": {"description": "Fix bug #42"}}
        result = await agent._handle_task_assigned(event)

        assert isinstance(result, CodingTaskResult)
        assert result.success is True
        assert "src/main.py" in result.files_changed
        assert "src/utils.py" in result.files_changed

    @pytest.mark.asyncio
    async def test_produces_error_result_when_no_sdk(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        event = {"type": "task_assigned", "payload": {"description": "Fix bug"}}
        result = await agent._handle_task_assigned(event)

        assert isinstance(result, CodingTaskResult)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_emits_event_on_completion(self) -> None:
        bus: asyncio.Queue[Any] = _bus()
        chunks = [{"content": "done", "tokens": 5}]
        agent = CoderAgent(
            persona=_persona(),
            event_bus=bus,
            agent_sdk_factory=_sdk_factory(chunks),
        )

        event = {"type": "task_assigned", "payload": {"description": "Task X"}}
        await agent._handle_task_assigned(event)

        # Should have emitted a coding_task_completed event on the bus.
        found = False
        while not bus.empty():
            msg = bus.get_nowait()
            if isinstance(msg, dict) and msg.get("type") == "coding_task_completed":
                found = True
                assert msg["source"] == "coder_agent"
                assert msg["result"]["success"] is True
        assert found


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_lifecycle_start_process_stop() -> None:
    """Start the agent, push a task event, verify processing, then stop."""
    bus: asyncio.Queue[Any] = _bus()
    chunks = [{"content": "result code", "tokens": 15}]
    agent = CoderAgent(
        persona=_persona(),
        event_bus=bus,
        agent_sdk_factory=_sdk_factory(chunks),
    )

    agent.start()
    await asyncio.sleep(0)

    # Push a task event.
    await bus.put({"type": "task_assigned", "payload": "implement feature"})

    # Let the agent process the event.
    await asyncio.sleep(0.3)

    # The agent should have processed at least one tick.
    assert len(agent.short_term_memory) >= 1

    await agent.stop()
    assert agent.state == AgentState.STOPPED


@pytest.mark.asyncio
async def test_stop_cleans_up_sandbox() -> None:
    """Verify that stopping the agent kills the active sandbox."""
    provider = FakeSandboxProvider()
    agent = CoderAgent(
        persona=_persona(),
        event_bus=_bus(),
        sandbox_provider=provider,  # type: ignore[arg-type]
    )

    # Trigger sandbox creation by executing a command.
    await agent._execute_in_sandbox("echo init")
    assert agent._active_sandbox is not None

    await agent.stop()
    assert provider.sandbox.killed is True
    assert agent._active_sandbox is None


# ---------------------------------------------------------------------------
# _call_llm — SDK error branch (lines 142-144)
# ---------------------------------------------------------------------------


class _ErrorSDKSession:
    """Fake SDK session that raises during query."""

    async def query(self, prompt: str) -> AsyncIterator[dict[str, Any]]:
        raise ConnectionError("SDK connection lost")
        yield  # type: ignore[misc]


@pytest.mark.asyncio
async def test_call_llm_returns_none_on_sdk_error() -> None:
    agent = CoderAgent(
        persona=_persona(),
        event_bus=_bus(),
        agent_sdk_factory=lambda: _ErrorSDKSession(),
    )
    result = await agent._call_llm({"type": "task"}, [])
    assert result is None


# ---------------------------------------------------------------------------
# _execute_in_sandbox — exception branch (lines 190-192)
# ---------------------------------------------------------------------------


class _ExplodingSandbox:
    """Sandbox that raises on run_command."""

    async def run_command(self, cmd: str) -> Any:
        raise OSError("disk full")

    async def write_file(self, path: str, content: str) -> None:
        pass

    async def read_file(self, path: str) -> str:
        return ""

    async def kill(self) -> None:
        pass


class _ExplodingSandboxProvider:
    async def create(self) -> _ExplodingSandbox:
        return _ExplodingSandbox()


@pytest.mark.asyncio
async def test_execute_in_sandbox_returns_error_on_exception() -> None:
    agent = CoderAgent(
        persona=_persona(),
        event_bus=_bus(),
        sandbox_provider=_ExplodingSandboxProvider(),  # type: ignore[arg-type]
    )
    result = await agent._execute_in_sandbox("echo hello")
    assert result.startswith("[error]")
    assert "disk full" in result


# ---------------------------------------------------------------------------
# _handle_task_assigned — sandbox error output branch (line 230)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_task_assigned_sandbox_error_output() -> None:
    """When sandbox output starts with [error], the task result should indicate failure."""
    # Use the exploding sandbox provider so _execute_in_sandbox returns "[error] ..."
    chunks = [{"content": "run test", "tokens": 10}]
    agent = CoderAgent(
        persona=_persona(),
        event_bus=_bus(),
        sandbox_provider=_ExplodingSandboxProvider(),  # type: ignore[arg-type]
        agent_sdk_factory=_sdk_factory(chunks),
    )
    event = {"type": "task_assigned", "payload": {"description": "Run tests"}}
    result = await agent._handle_task_assigned(event)
    assert isinstance(result, CodingTaskResult)
    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("[error]")


# ---------------------------------------------------------------------------
# stop() — sandbox cleanup error branch (lines 271-272)
# ---------------------------------------------------------------------------


class _FailKillSandbox:
    async def run_command(self, cmd: str) -> FakeCommandResult:
        return FakeCommandResult()

    async def write_file(self, path: str, content: str) -> None:
        pass

    async def read_file(self, path: str) -> str:
        return ""

    async def kill(self) -> None:
        raise RuntimeError("cleanup failed")


@pytest.mark.asyncio
async def test_stop_handles_sandbox_cleanup_error() -> None:
    agent = CoderAgent(
        persona=_persona(),
        event_bus=_bus(),
    )
    # Manually set the sandbox so kill() will be called.
    agent._active_sandbox = _FailKillSandbox()  # type: ignore[assignment]
    # Should not raise despite cleanup error.
    await agent.stop()
    assert agent._active_sandbox is None
    assert agent.state == AgentState.STOPPED


# ---------------------------------------------------------------------------
# _build_prompt — rag_results and repo_url branches (lines 288, 291-293)
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_includes_repo_url(self) -> None:
        agent = CoderAgent(
            persona=_persona(backstory="Expert dev"),
            event_bus=_bus(),
            repo_url="https://github.com/org/repo",
        )
        prompt = agent._build_prompt("fix bug", [])
        assert "https://github.com/org/repo" in prompt
        assert "Expert dev" in prompt

    def test_includes_rag_results(self) -> None:
        agent = CoderAgent(
            persona=_persona(),
            event_bus=_bus(),
        )
        prompt = agent._build_prompt("fix bug", ["doc_snippet_1", "doc_snippet_2"])
        assert "doc_snippet_1" in prompt
        assert "doc_snippet_2" in prompt
        assert "Relevant knowledge" in prompt

    def test_converts_non_string_event(self) -> None:
        agent = CoderAgent(persona=_persona(), event_bus=_bus())
        prompt = agent._build_prompt({"type": "task"}, [])
        assert "Task:" in prompt


# ---------------------------------------------------------------------------
# coder_models._utc_now — line 11 (exercised via SandboxSession default)
# ---------------------------------------------------------------------------


class TestCoderModels:
    def test_sandbox_session_default_created_at(self) -> None:
        """SandboxSession.created_at should use _utc_now as default factory."""
        from datetime import UTC, datetime

        before = datetime.now(UTC)
        session = SandboxSession(sandbox_id="s1")
        after = datetime.now(UTC)
        assert before <= session.created_at <= after
        assert session.is_active is True
