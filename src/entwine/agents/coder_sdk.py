"""CoderSDKSession: Claude Agent SDK wrapper for autonomous coding loops."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from entwine.agents.coder_models import CodingTaskResult
from entwine.events.models import SessionBudgetExceeded

if TYPE_CHECKING:
    from entwine.events.bus import EventBus
    from entwine.observability.cost_tracker import CostTracker
    from entwine.sandbox.manager import SandboxManager

log = structlog.get_logger(__name__)

# Conditional import — claude-agent-sdk is an optional dependency.
try:
    from claude_agent_sdk import (  # type: ignore[import-untyped]
        ClaudeAgentOptions,
        HookMatcher,
        query,
    )

    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Concurrency limiter
# ---------------------------------------------------------------------------


class CoderSemaphore:
    """Wraps asyncio.Semaphore to limit concurrent coder agent sessions."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent

    async def acquire(self) -> None:
        await self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()

    async def __aenter__(self) -> CoderSemaphore:
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: type | None, exc: Exception | None, tb: Any) -> None:
        self.release()

    @property
    def max_concurrent(self) -> int:
        return self._max


# ---------------------------------------------------------------------------
# PreToolUse hooks for sandbox routing
# ---------------------------------------------------------------------------


def _make_bash_sandbox_hook(
    sandbox: SandboxManager,
) -> Any:
    """Create a PreToolUse hook that routes Bash commands to the E2B sandbox."""

    async def _bash_hook(
        input_data: dict[str, Any], tool_use_id: str, context: Any
    ) -> dict[str, Any]:
        command = input_data.get("tool_input", {}).get("command", "")
        log.info("coder_sdk.bash_hook", command=command[:100])

        try:
            result = await sandbox.run_command(command)
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.exit_code != 0:
                output += f"\n[exit code: {result.exit_code}]"
        except Exception as exc:
            output = f"[sandbox error] {exc}"

        return {
            "systemMessage": f"Command executed in sandbox. Output:\n{output}",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Routed to E2B sandbox",
            },
        }

    return _bash_hook


def _make_write_sandbox_hook(
    sandbox: SandboxManager,
    files_changed: list[str] | None = None,
) -> Any:
    """Create a PreToolUse hook that routes Write/Edit to the E2B sandbox."""

    async def _write_hook(
        input_data: dict[str, Any], tool_use_id: str, context: Any
    ) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        file_path = tool_input.get("file_path", "")

        if not file_path:
            return {}

        log.info("coder_sdk.write_hook", tool=tool_name, path=file_path[:80])

        try:
            if tool_name == "Edit":
                # Edit uses old_string/new_string — read-modify-write in sandbox
                old_string = tool_input.get("old_string", "")
                new_string = tool_input.get("new_string", "")
                current = await sandbox.read_file(file_path)
                if old_string not in current:
                    return {
                        "systemMessage": f"[sandbox error] old_string not found in {file_path}",
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": "Edit target not found",
                        },
                    }
                updated = current.replace(old_string, new_string, 1)
                await sandbox.write_file(file_path, updated)
            else:
                # Write tool — direct content write
                content = tool_input.get("content", "")
                await sandbox.write_file(file_path, content)

            if files_changed is not None and file_path not in files_changed:
                files_changed.append(file_path)
        except Exception as exc:
            return {
                "systemMessage": f"[sandbox error] Failed to {tool_name.lower()} {file_path}: {exc}",
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Sandbox {tool_name.lower()} error: {exc}",
                },
            }

        action = "edited" if tool_name == "Edit" else "written"
        return {
            "systemMessage": f"File {action} in sandbox: {file_path}",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Routed to E2B sandbox",
            },
        }

    return _write_hook


def _make_read_sandbox_hook(
    sandbox: SandboxManager,
) -> Any:
    """Create a PreToolUse hook that routes Read to the E2B sandbox."""

    async def _read_hook(
        input_data: dict[str, Any], tool_use_id: str, context: Any
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")

        if not file_path:
            return {}

        log.info("coder_sdk.read_hook", path=file_path[:80])

        try:
            content = await sandbox.read_file(file_path)
        except Exception as exc:
            return {
                "systemMessage": f"[sandbox error] Failed to read {file_path}: {exc}",
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Sandbox read error: {exc}",
                },
            }

        return {
            "systemMessage": f"File content from sandbox ({file_path}):\n{content}",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Routed to E2B sandbox",
            },
        }

    return _read_hook


# ---------------------------------------------------------------------------
# CoderSDKSession
# ---------------------------------------------------------------------------


class CoderSDKSession:
    """Wraps a Claude Agent SDK query session for coder agents.

    Handles sandbox tool routing, token tracking, and cost recording.
    """

    def __init__(
        self,
        *,
        sandbox_manager: SandboxManager | None = None,
        repo_url: str = "",
        max_tokens: int = 100_000,
        cost_tracker: CostTracker | None = None,
        agent_id: str = "",
        cwd: str = "",
        event_bus: EventBus | None = None,
    ) -> None:
        self._sandbox = sandbox_manager
        self._repo_url = repo_url
        self._max_tokens = max_tokens
        self._cost_tracker = cost_tracker
        self._agent_id = agent_id
        self._cwd = cwd
        self._event_bus = event_bus
        self._total_cost: float = 0.0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    async def run(self, prompt: str) -> CodingTaskResult:
        """Execute a coding task via the Claude Agent SDK."""
        if not SDK_AVAILABLE:
            return CodingTaskResult(
                task_description=prompt,
                success=False,
                error="claude-agent-sdk is not installed. Install with: pip install entwine[coder]",
            )

        # Track files changed via closure shared with write hook
        files_changed: list[str] = []
        options = self._build_options(files_changed=files_changed)

        collected_content: list[str] = []
        error: str | None = None

        try:
            async for message in query(prompt=prompt, options=options):
                # Detect ResultMessage by class name (avoids MagicMock false positives)
                if type(message).__name__ == "ResultMessage":
                    self._total_cost = getattr(message, "total_cost_usd", 0.0) or 0.0
                    usage = getattr(message, "usage", None)
                    if isinstance(usage, dict):
                        self._total_input_tokens = usage.get("input_tokens", 0)
                        self._total_output_tokens = usage.get("output_tokens", 0)
                    elif usage is not None:
                        self._total_input_tokens = getattr(usage, "input_tokens", 0)
                        self._total_output_tokens = getattr(usage, "output_tokens", 0)
                else:
                    content = getattr(message, "content", None)
                    if content and isinstance(content, str):
                        collected_content.append(content)
        except Exception as exc:
            log.error("coder_sdk.session_error", agent=self._agent_id, error=str(exc))
            error = str(exc)

        # Record cost
        if self._cost_tracker and self._total_cost > 0:
            self._cost_tracker.record(
                self._agent_id,
                self._total_cost,
                self._total_input_tokens,
                self._total_output_tokens,
            )

        # Check token budget and emit SessionBudgetExceeded if exceeded
        total_tokens = self._total_input_tokens + self._total_output_tokens
        if total_tokens > self._max_tokens:
            log.warning(
                "coder_sdk.budget_exceeded",
                agent=self._agent_id,
                tokens_used=total_tokens,
                max_tokens=self._max_tokens,
            )
            if self._event_bus is not None:
                await self._event_bus.publish(
                    SessionBudgetExceeded(
                        source_agent=self._agent_id,
                        payload={
                            "tokens_used": total_tokens,
                            "max_tokens": self._max_tokens,
                        },
                    )
                )

        return CodingTaskResult(
            task_description=prompt,
            files_changed=files_changed,
            success=error is None,
            error=error,
        )

    def _build_options(self, *, files_changed: list[str] | None = None) -> Any:
        """Build ClaudeAgentOptions with sandbox hooks if available."""
        hooks: dict[str, list[Any]] = {}

        if self._sandbox is not None:
            bash_hook = _make_bash_sandbox_hook(self._sandbox)
            write_hook = _make_write_sandbox_hook(self._sandbox, files_changed=files_changed)
            read_hook = _make_read_sandbox_hook(self._sandbox)
            hooks["PreToolUse"] = [
                HookMatcher(matcher="Bash", hooks=[bash_hook]),
                HookMatcher(matcher="Write|Edit", hooks=[write_hook]),
                HookMatcher(matcher="Read", hooks=[read_hook]),
            ]

        # Estimate max budget from token limit (rough: $0.01 per 1k tokens)
        max_budget = (self._max_tokens / 1000) * 0.01

        return ClaudeAgentOptions(
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            permission_mode="acceptEdits",
            cwd=self._cwd or ".",
            system_prompt=f"You are a developer agent. Repository: {self._repo_url}"
            if self._repo_url
            else "You are a developer agent.",
            max_turns=50,
            max_budget_usd=max_budget,
            hooks=hooks if hooks else None,
        )
