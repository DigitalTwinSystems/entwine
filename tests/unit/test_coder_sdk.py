"""Tests for entwine.agents.coder_sdk — CoderSDKSession, hooks, and semaphore."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from entwine.agents.coder_models import CodingTaskResult, CommandResult
from entwine.agents.coder_sdk import (
    CoderSDKSession,
    CoderSemaphore,
    _make_bash_sandbox_hook,
    _make_read_sandbox_hook,
    _make_write_sandbox_hook,
)
from entwine.observability.cost_tracker import CostTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_sandbox() -> MagicMock:
    """Create a mock SandboxManager."""
    sbx = MagicMock()
    cmd_result = CommandResult(stdout="output\n", stderr="", exit_code=0)
    sbx.run_command = AsyncMock(return_value=cmd_result)
    sbx.read_file = AsyncMock(return_value="file content")
    sbx.write_file = AsyncMock()
    sbx.kill = AsyncMock()
    return sbx


class ResultMessage:
    """Mock ResultMessage for tests — class name must be 'ResultMessage'."""

    def __init__(
        self,
        cost: float = 0.05,
        input_tokens: int = 1000,
        output_tokens: int = 500,
    ) -> None:
        self.total_cost_usd = cost
        self.usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _make_result_message(
    cost: float = 0.05,
    input_tokens: int = 1000,
    output_tokens: int = 500,
) -> ResultMessage:
    """Create a mock ResultMessage."""
    return ResultMessage(cost, input_tokens, output_tokens)


class _TextMessage:
    """Simple non-ResultMessage for tests (avoids MagicMock attribute leakage)."""

    def __init__(self, content: str = "code output") -> None:
        self.content = content


def _make_text_message(content: str = "code output") -> _TextMessage:
    """Create a mock non-result message."""
    return _TextMessage(content)


@contextmanager
def _patch_sdk(messages: list[Any] | None = None) -> Generator[MagicMock, None, None]:
    """Patch SDK availability and query function."""
    if messages is None:
        messages = [_make_text_message(), _make_result_message()]

    async def mock_query(*args: Any, **kwargs: Any) -> Any:
        for msg in messages:
            yield msg

    with (
        patch("entwine.agents.coder_sdk.SDK_AVAILABLE", True),
        patch("entwine.agents.coder_sdk.query", mock_query, create=True),
        patch("entwine.agents.coder_sdk.ClaudeAgentOptions", MagicMock, create=True),
        patch("entwine.agents.coder_sdk.HookMatcher", MagicMock, create=True),
    ):
        yield MagicMock()


# ---------------------------------------------------------------------------
# CoderSemaphore tests
# ---------------------------------------------------------------------------


class TestCoderSemaphore:
    async def test_semaphore_limits_concurrency(self) -> None:
        sem = CoderSemaphore(max_concurrent=2)
        assert sem.max_concurrent == 2

        # Acquire 2 — should work
        await sem.acquire()
        await sem.acquire()

        # 3rd should block — test with timeout
        acquired = False

        async def try_acquire() -> None:
            nonlocal acquired
            await sem.acquire()
            acquired = True

        task = asyncio.create_task(try_acquire())
        await asyncio.sleep(0.05)
        assert not acquired

        # Release one — should unblock
        sem.release()
        await asyncio.sleep(0.05)
        assert acquired

        # Cleanup
        sem.release()
        sem.release()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_semaphore_context_manager(self) -> None:
        sem = CoderSemaphore(max_concurrent=1)
        async with sem:
            pass  # Should acquire and release


# ---------------------------------------------------------------------------
# Bash sandbox hook tests
# ---------------------------------------------------------------------------


class TestBashSandboxHook:
    async def test_bash_hook_routes_to_sandbox(self) -> None:
        sandbox = _make_mock_sandbox()
        hook = _make_bash_sandbox_hook(sandbox)

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
        }

        result = await hook(input_data, "tool-id-1", None)

        sandbox.run_command.assert_awaited_once_with("echo hello")
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "output\n" in result["systemMessage"]

    async def test_bash_hook_includes_stderr(self) -> None:
        sandbox = _make_mock_sandbox()
        sandbox.run_command = AsyncMock(
            return_value=CommandResult(stdout="", stderr="error msg", exit_code=1)
        )
        hook = _make_bash_sandbox_hook(sandbox)

        input_data = {"tool_name": "Bash", "tool_input": {"command": "bad-cmd"}}
        result = await hook(input_data, "tool-id-2", None)

        assert "error msg" in result["systemMessage"]
        assert "[exit code: 1]" in result["systemMessage"]

    async def test_bash_hook_handles_sandbox_error(self) -> None:
        sandbox = _make_mock_sandbox()
        sandbox.run_command = AsyncMock(side_effect=RuntimeError("sandbox down"))
        hook = _make_bash_sandbox_hook(sandbox)

        input_data = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        result = await hook(input_data, "tool-id-3", None)

        assert "[sandbox error]" in result["systemMessage"]
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# Read/Write sandbox hook tests
# ---------------------------------------------------------------------------


class TestWriteSandboxHook:
    async def test_write_hook_routes_to_sandbox(self) -> None:
        sandbox = _make_mock_sandbox()
        hook = _make_write_sandbox_hook(sandbox)

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/foo.py", "content": "x = 1"},
        }
        result = await hook(input_data, "tid", None)

        sandbox.write_file.assert_awaited_once_with("/tmp/foo.py", "x = 1")
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_edit_hook_reads_modifies_writes(self) -> None:
        sandbox = _make_mock_sandbox()
        sandbox.read_file = AsyncMock(return_value="old line\nkeep this\n")
        files_changed: list[str] = []
        hook = _make_write_sandbox_hook(sandbox, files_changed=files_changed)

        input_data = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/foo.py",
                "old_string": "old line",
                "new_string": "new line",
            },
        }
        result = await hook(input_data, "tid", None)

        sandbox.read_file.assert_awaited_once_with("/tmp/foo.py")
        sandbox.write_file.assert_awaited_once_with("/tmp/foo.py", "new line\nkeep this\n")
        assert "edited" in result["systemMessage"]
        assert "/tmp/foo.py" in files_changed

    async def test_edit_hook_old_string_not_found(self) -> None:
        sandbox = _make_mock_sandbox()
        sandbox.read_file = AsyncMock(return_value="some content\n")
        hook = _make_write_sandbox_hook(sandbox)

        input_data = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/foo.py",
                "old_string": "not found",
                "new_string": "replacement",
            },
        }
        result = await hook(input_data, "tid", None)
        assert "not found" in result["systemMessage"]
        sandbox.write_file.assert_not_awaited()

    async def test_write_hook_tracks_files_changed(self) -> None:
        sandbox = _make_mock_sandbox()
        files_changed: list[str] = []
        hook = _make_write_sandbox_hook(sandbox, files_changed=files_changed)

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/foo.py", "content": "x = 1"},
        }
        await hook(input_data, "tid", None)
        assert "/tmp/foo.py" in files_changed

    async def test_write_hook_no_path_passthrough(self) -> None:
        sandbox = _make_mock_sandbox()
        hook = _make_write_sandbox_hook(sandbox)

        result = await hook({"tool_name": "Write", "tool_input": {}}, "tid", None)
        assert result == {}

    async def test_write_hook_handles_error(self) -> None:
        sandbox = _make_mock_sandbox()
        sandbox.write_file = AsyncMock(side_effect=RuntimeError("disk full"))
        hook = _make_write_sandbox_hook(sandbox)

        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/f.py", "content": "x"},
        }
        result = await hook(input_data, "tid", None)
        assert "disk full" in result["systemMessage"]


class TestReadSandboxHook:
    async def test_read_hook_routes_to_sandbox(self) -> None:
        sandbox = _make_mock_sandbox()
        hook = _make_read_sandbox_hook(sandbox)

        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/foo.py"},
        }
        result = await hook(input_data, "tid", None)

        sandbox.read_file.assert_awaited_once_with("/tmp/foo.py")
        assert "file content" in result["systemMessage"]

    async def test_read_hook_no_path_passthrough(self) -> None:
        sandbox = _make_mock_sandbox()
        hook = _make_read_sandbox_hook(sandbox)

        result = await hook({"tool_name": "Read", "tool_input": {}}, "tid", None)
        assert result == {}

    async def test_read_hook_handles_error(self) -> None:
        sandbox = _make_mock_sandbox()
        sandbox.read_file = AsyncMock(side_effect=FileNotFoundError("no such file"))
        hook = _make_read_sandbox_hook(sandbox)

        input_data = {"tool_name": "Read", "tool_input": {"file_path": "/missing.py"}}
        result = await hook(input_data, "tid", None)
        assert "no such file" in result["systemMessage"]


# ---------------------------------------------------------------------------
# CoderSDKSession tests
# ---------------------------------------------------------------------------


class TestCoderSDKSession:
    async def test_run_returns_coding_task_result(self) -> None:
        with _patch_sdk():
            session = CoderSDKSession(
                agent_id="coder-1",
                max_tokens=100_000,
            )
            result = await session.run("implement the feature")

            assert isinstance(result, CodingTaskResult)
            assert result.success
            assert result.task_description == "implement the feature"

    async def test_run_tracks_cost(self) -> None:
        tracker = CostTracker()
        with _patch_sdk():
            session = CoderSDKSession(
                agent_id="coder-1",
                cost_tracker=tracker,
                max_tokens=100_000,
            )
            await session.run("implement feature")

            assert session.total_cost == 0.05
            assert session.total_input_tokens == 1000
            assert session.total_output_tokens == 500
            assert tracker.agent_cost("coder-1") == 0.05

    async def test_run_returns_error_when_sdk_not_available(self) -> None:
        with patch("entwine.agents.coder_sdk.SDK_AVAILABLE", False):
            session = CoderSDKSession(agent_id="coder-1")
            result = await session.run("implement feature")

            assert not result.success
            assert "not installed" in (result.error or "")

    async def test_run_handles_exception(self) -> None:
        async def error_query(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("SDK crash")
            yield

        with (
            patch("entwine.agents.coder_sdk.SDK_AVAILABLE", True),
            patch("entwine.agents.coder_sdk.query", error_query, create=True),
            patch("entwine.agents.coder_sdk.ClaudeAgentOptions", MagicMock, create=True),
            patch("entwine.agents.coder_sdk.HookMatcher", MagicMock, create=True),
            patch("entwine.agents.coder_sdk.ResultMessage", MagicMock, create=True),
        ):
            session = CoderSDKSession(agent_id="coder-1")
            result = await session.run("implement feature")

            assert not result.success
            assert "SDK crash" in (result.error or "")

    async def test_run_with_sandbox_builds_hooks(self) -> None:
        sandbox = _make_mock_sandbox()
        options_calls: list[Any] = []

        mock_options_cls = MagicMock(side_effect=lambda **kw: options_calls.append(kw))

        with (
            patch("entwine.agents.coder_sdk.SDK_AVAILABLE", True),
            patch("entwine.agents.coder_sdk.ClaudeAgentOptions", mock_options_cls, create=True),
            patch("entwine.agents.coder_sdk.HookMatcher", MagicMock, create=True),
            patch(
                "entwine.agents.coder_sdk.ResultMessage",
                type(_make_result_message()),
                create=True,
            ),
        ):

            async def mock_query(*args: Any, **kwargs: Any) -> Any:
                yield _make_result_message()

            with patch("entwine.agents.coder_sdk.query", mock_query, create=True):
                session = CoderSDKSession(
                    sandbox_manager=sandbox,
                    agent_id="coder-1",
                )
                await session.run("do task")

                assert len(options_calls) == 1
                assert options_calls[0]["hooks"] is not None


# ---------------------------------------------------------------------------
# SessionBudgetExceeded event model test
# ---------------------------------------------------------------------------


class TestSessionBudgetExceededEvent:
    def test_event_model_exists(self) -> None:
        from entwine.events.models import SessionBudgetExceeded

        evt = SessionBudgetExceeded(
            source_agent="coder-1",
            payload={"tokens_used": 150_000, "max_tokens": 100_000},
        )
        assert evt.event_type == "session_budget_exceeded"
        assert evt.source_agent == "coder-1"

    async def test_session_emits_budget_exceeded_event(self) -> None:
        """Verify SessionBudgetExceeded is actually published when tokens exceed limit."""
        from entwine.events.models import SessionBudgetExceeded

        bus = AsyncMock()
        bus.publish = AsyncMock()

        # Result message reports tokens exceeding the limit
        high_token_result = ResultMessage(cost=5.0, input_tokens=80_000, output_tokens=30_000)
        messages = [_make_text_message(), high_token_result]

        with _patch_sdk(messages):
            session = CoderSDKSession(
                agent_id="coder-1",
                max_tokens=50_000,  # Exceeded by 80k + 30k = 110k
                event_bus=bus,
            )
            await session.run("implement feature")

            bus.publish.assert_awaited_once()
            event = bus.publish.call_args[0][0]
            assert isinstance(event, SessionBudgetExceeded)
            assert event.payload["tokens_used"] == 110_000
            assert event.payload["max_tokens"] == 50_000


# ---------------------------------------------------------------------------
# Config model test
# ---------------------------------------------------------------------------


class TestMaxCoderAgentsConfig:
    def test_default_value(self) -> None:
        from entwine.config.models import SimulationConfig

        config = SimulationConfig(name="test")
        assert config.max_coder_agents == 2

    def test_custom_value(self) -> None:
        from entwine.config.models import SimulationConfig

        config = SimulationConfig(name="test", max_coder_agents=4)
        assert config.max_coder_agents == 4
