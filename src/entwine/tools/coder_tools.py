"""Coder agent tools: file I/O, shell execution, and git operations via sandbox."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from entwine.sandbox.manager import SandboxManager
    from entwine.tools.dispatcher import ToolDispatcher

log = structlog.get_logger(__name__)

DEFAULT_MAX_OUTPUT_SIZE = 10_000


def _truncate(output: str, max_size: int) -> str:
    """Truncate output if it exceeds max_size, appending a warning."""
    if len(output) > max_size:
        total = len(output)
        return output[:max_size] + f"\n[output truncated: {total} chars, showing first {max_size}]"
    return output


# ---------------------------------------------------------------------------
# Tool implementations (closures bound to a SandboxManager instance)
# ---------------------------------------------------------------------------


def _make_read_file(sandbox: SandboxManager):  # type: ignore[type-arg]
    """Create a read_file tool bound to the given sandbox."""

    async def read_file(path: str) -> str:
        """Read a file from the sandbox filesystem."""
        try:
            content = await sandbox.read_file(path)
            return content
        except Exception as exc:
            return f"[error] Failed to read {path}: {exc}"

    return read_file


def _make_write_file(sandbox: SandboxManager):  # type: ignore[type-arg]
    """Create a write_file tool bound to the given sandbox."""

    async def write_file(path: str, content: str) -> str:
        """Write a file to the sandbox filesystem."""
        try:
            await sandbox.write_file(path, content)
            return f"File written: {path}"
        except Exception as exc:
            return f"[error] Failed to write {path}: {exc}"

    return write_file


def _make_run_command(sandbox: SandboxManager, max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE):  # type: ignore[type-arg]
    """Create a run_command tool bound to the given sandbox."""

    async def run_command(command: str) -> str:
        """Execute a shell command in the sandbox."""
        try:
            result = await sandbox.run_command(command)
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.exit_code != 0:
                output += f"\n[exit code: {result.exit_code}]"

            return _truncate(output, max_output_size)
        except Exception as exc:
            return f"[error] Command failed: {exc}"

    return run_command


def _make_search_code(sandbox: SandboxManager, max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE):  # type: ignore[type-arg]
    """Create a search_code tool bound to the given sandbox."""

    async def search_code(pattern: str, path: str = ".") -> str:
        """Search for a pattern in source code files."""
        safe_pattern = shlex.quote(pattern)
        safe_path = shlex.quote(path)
        try:
            result = await sandbox.run_command(f"grep -rn {safe_pattern} {safe_path}")
            output = result.stdout
            if not output and result.exit_code == 1:
                return f"No matches found for pattern: {pattern}"
            if result.exit_code not in (0, 1):
                return f"[error] grep failed (exit {result.exit_code}): {result.stderr}"

            return _truncate(output, max_output_size)
        except Exception as exc:
            return f"[error] Search failed: {exc}"

    return search_code


def _make_git_commit(sandbox: SandboxManager, max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE):  # type: ignore[type-arg]
    """Create a git_commit tool bound to the given sandbox."""

    async def git_commit(message: str) -> str:
        """Stage all changes and commit with the given message."""
        safe_msg = shlex.quote(message)
        try:
            result = await sandbox.run_command(f"git add -A && git commit -m {safe_msg}")
            if result.exit_code != 0:
                return f"[error] git commit failed (exit {result.exit_code}): {result.stderr}"
            return _truncate(result.stdout, max_output_size)
        except Exception as exc:
            return f"[error] git commit failed: {exc}"

    return git_commit


def _make_git_push(sandbox: SandboxManager, max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE):  # type: ignore[type-arg]
    """Create a git_push tool bound to the given sandbox."""

    async def git_push(branch: str = "") -> str:
        """Push the current branch to the remote repository."""
        cmd = "git push"
        if branch:
            safe_branch = shlex.quote(branch)
            cmd = f"git push origin {safe_branch}"
        try:
            result = await sandbox.run_command(cmd)
            if result.exit_code != 0:
                return f"[error] git push failed (exit {result.exit_code}): {result.stderr}"
            output = result.stdout
            if result.stderr:
                output += f"\n{result.stderr}"
            return _truncate(output or "Push completed successfully.", max_output_size)
        except Exception as exc:
            return f"[error] git push failed: {exc}"

    return git_push


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_coder_tools(
    dispatcher: ToolDispatcher,
    sandbox: SandboxManager,
    *,
    max_output_size: int = DEFAULT_MAX_OUTPUT_SIZE,
) -> None:
    """Register all coder agent tools with the given dispatcher."""
    dispatcher.register(
        name="read_file",
        handler=_make_read_file(sandbox),
        description="Read a file from the sandbox filesystem.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path to read"}},
            "required": ["path"],
        },
    )

    dispatcher.register(
        name="write_file",
        handler=_make_write_file(sandbox),
        description="Write content to a file in the sandbox filesystem.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["path", "content"],
        },
    )

    dispatcher.register(
        name="run_command",
        handler=_make_run_command(sandbox, max_output_size),
        description="Execute a shell command in the sandbox.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
    )

    dispatcher.register(
        name="search_code",
        handler=_make_search_code(sandbox, max_output_size),
        description="Search for a pattern in source code files using grep.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Directory to search", "default": "."},
            },
            "required": ["pattern"],
        },
    )

    dispatcher.register(
        name="git_commit",
        handler=_make_git_commit(sandbox, max_output_size),
        description="Stage all changes and create a git commit.",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
            },
            "required": ["message"],
        },
    )

    dispatcher.register(
        name="git_push",
        handler=_make_git_push(sandbox, max_output_size),
        description="Push the current branch to the remote repository.",
        parameters={
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Branch name to push (default: current branch)",
                    "default": "",
                },
            },
            "required": [],
        },
    )

    log.info("coder_tools.registered", count=6)
