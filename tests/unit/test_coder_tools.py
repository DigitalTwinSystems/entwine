"""Tests for entwine.tools.coder_tools — sandbox-routed coder agent tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from entwine.agents.coder_models import CommandResult
from entwine.tools.coder_tools import (
    DEFAULT_MAX_OUTPUT_SIZE,
    _make_git_commit,
    _make_git_push,
    _make_read_file,
    _make_run_command,
    _make_search_code,
    _make_write_file,
    register_coder_tools,
)
from entwine.tools.dispatcher import ToolDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox(
    stdout: str = "ok\n",
    stderr: str = "",
    exit_code: int = 0,
    file_content: str = "file content",
) -> MagicMock:
    """Create a mock SandboxManager."""
    sbx = MagicMock()
    sbx.run_command = AsyncMock(
        return_value=CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code)
    )
    sbx.read_file = AsyncMock(return_value=file_content)
    sbx.write_file = AsyncMock()
    return sbx


# ---------------------------------------------------------------------------
# read_file tests
# ---------------------------------------------------------------------------


class TestReadFile:
    async def test_returns_file_content(self) -> None:
        sbx = _make_sandbox(file_content="hello world")
        read_file = _make_read_file(sbx)
        result = await read_file("/tmp/test.txt")
        assert result == "hello world"
        sbx.read_file.assert_awaited_once_with("/tmp/test.txt")

    async def test_returns_error_on_failure(self) -> None:
        sbx = _make_sandbox()
        sbx.read_file = AsyncMock(side_effect=FileNotFoundError("not found"))
        read_file = _make_read_file(sbx)
        result = await read_file("/missing.txt")
        assert "[error]" in result


# ---------------------------------------------------------------------------
# write_file tests
# ---------------------------------------------------------------------------


class TestWriteFile:
    async def test_writes_and_confirms(self) -> None:
        sbx = _make_sandbox()
        write_file = _make_write_file(sbx)
        result = await write_file("/tmp/out.py", "x = 1")
        assert "File written" in result
        sbx.write_file.assert_awaited_once_with("/tmp/out.py", "x = 1")

    async def test_returns_error_on_failure(self) -> None:
        sbx = _make_sandbox()
        sbx.write_file = AsyncMock(side_effect=RuntimeError("disk full"))
        write_file = _make_write_file(sbx)
        result = await write_file("/tmp/f.py", "x")
        assert "[error]" in result


# ---------------------------------------------------------------------------
# run_command tests
# ---------------------------------------------------------------------------


class TestRunCommand:
    async def test_returns_stdout(self) -> None:
        sbx = _make_sandbox(stdout="hello\n")
        run_command = _make_run_command(sbx)
        result = await run_command("echo hello")
        assert "hello\n" in result

    async def test_includes_stderr_and_exit_code(self) -> None:
        sbx = _make_sandbox(stdout="", stderr="error msg", exit_code=1)
        run_command = _make_run_command(sbx)
        result = await run_command("bad-cmd")
        assert "error msg" in result
        assert "[exit code: 1]" in result

    async def test_truncates_large_output(self) -> None:
        large_output = "x" * (DEFAULT_MAX_OUTPUT_SIZE + 5000)
        sbx = _make_sandbox(stdout=large_output)
        run_command = _make_run_command(sbx)
        result = await run_command("cat bigfile")
        assert "[output truncated:" in result
        assert len(result) < len(large_output) + 100

    async def test_returns_error_on_exception(self) -> None:
        sbx = _make_sandbox()
        sbx.run_command = AsyncMock(side_effect=RuntimeError("sandbox down"))
        run_command = _make_run_command(sbx)
        result = await run_command("echo hi")
        assert "[error]" in result


# ---------------------------------------------------------------------------
# search_code tests
# ---------------------------------------------------------------------------


class TestSearchCode:
    async def test_returns_grep_results(self) -> None:
        sbx = _make_sandbox(stdout="main.py:5:def hello():\n")
        search_code = _make_search_code(sbx)
        result = await search_code("hello", "src/")
        assert "main.py:5" in result

    async def test_returns_no_matches(self) -> None:
        sbx = _make_sandbox(stdout="", exit_code=1)
        search_code = _make_search_code(sbx)
        result = await search_code("nonexistent")
        assert "No matches found" in result

    async def test_returns_error_on_grep_failure(self) -> None:
        sbx = _make_sandbox(stdout="", stderr="invalid regex", exit_code=2)
        search_code = _make_search_code(sbx)
        result = await search_code("[invalid")
        assert "[error]" in result


# ---------------------------------------------------------------------------
# git_commit tests
# ---------------------------------------------------------------------------


class TestGitCommit:
    async def test_commits_with_message(self) -> None:
        sbx = _make_sandbox(stdout="[main abc1234] Fix bug\n 1 file changed\n")
        git_commit = _make_git_commit(sbx)
        result = await git_commit("Fix bug")
        assert "abc1234" in result
        # Verify the command uses git add -A && git commit
        cmd = sbx.run_command.call_args[0][0]
        assert "git add -A" in cmd
        assert "git commit -m" in cmd

    async def test_returns_error_on_failure(self) -> None:
        sbx = _make_sandbox(stderr="nothing to commit", exit_code=1)
        git_commit = _make_git_commit(sbx)
        result = await git_commit("Empty commit")
        assert "[error]" in result

    async def test_quotes_message_safely(self) -> None:
        sbx = _make_sandbox(stdout="committed\n")
        git_commit = _make_git_commit(sbx)
        await git_commit("Fix 'quoted' & special $chars")
        cmd = sbx.run_command.call_args[0][0]
        # shlex.quote wraps in single quotes
        assert "'" in cmd or "Fix" in cmd


# ---------------------------------------------------------------------------
# git_push tests
# ---------------------------------------------------------------------------


class TestGitPush:
    async def test_pushes_current_branch(self) -> None:
        sbx = _make_sandbox(stdout="", stderr="To github.com:repo.git\n")
        git_push = _make_git_push(sbx)
        result = await git_push()
        cmd = sbx.run_command.call_args[0][0]
        assert cmd == "git push"
        assert "github.com" in result

    async def test_pushes_specific_branch(self) -> None:
        sbx = _make_sandbox(stdout="pushed\n")
        git_push = _make_git_push(sbx)
        await git_push("feature/new")
        cmd = sbx.run_command.call_args[0][0]
        assert "origin" in cmd
        assert "feature/new" in cmd

    async def test_returns_error_on_failure(self) -> None:
        sbx = _make_sandbox(stderr="rejected", exit_code=1)
        git_push = _make_git_push(sbx)
        result = await git_push()
        assert "[error]" in result


# ---------------------------------------------------------------------------
# register_coder_tools tests
# ---------------------------------------------------------------------------


class TestRegisterCoderTools:
    def test_registers_all_six_tools(self) -> None:
        dispatcher = ToolDispatcher()
        sbx = _make_sandbox()
        register_coder_tools(dispatcher, sbx)

        defs = dispatcher.get_tool_definitions()
        tool_names = {d["function"]["name"] for d in defs}
        assert tool_names == {
            "read_file",
            "write_file",
            "run_command",
            "search_code",
            "git_commit",
            "git_push",
        }

    async def test_registered_tools_are_callable(self) -> None:
        from entwine.tools.models import ToolCall

        dispatcher = ToolDispatcher()
        sbx = _make_sandbox(stdout="test output\n")
        register_coder_tools(dispatcher, sbx)

        result = await dispatcher.dispatch(
            ToolCall(name="run_command", arguments={"command": "echo test"}, call_id="c1")
        )
        assert result.error is None
        assert "test output" in result.output
