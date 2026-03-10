"""CoderAgent: autonomous coding agent with sandbox execution and SDK integration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol, runtime_checkable

import structlog

from entwine.agents.base import BaseAgent
from entwine.agents.coder_models import CodingTaskResult, CommandResult
from entwine.agents.models import AgentPersona

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol interfaces for external dependencies
# ---------------------------------------------------------------------------


@runtime_checkable
class SandboxProtocol(Protocol):
    """Protocol for a sandboxed execution environment (e.g. E2B)."""

    async def run_command(self, cmd: str) -> CommandResult: ...

    async def write_file(self, path: str, content: str) -> None: ...

    async def read_file(self, path: str) -> str: ...

    async def kill(self) -> None: ...


@runtime_checkable
class SandboxProvider(Protocol):
    """Factory that creates sandbox instances."""

    async def create(self) -> SandboxProtocol: ...


@runtime_checkable
class AgentSDKSession(Protocol):
    """Protocol for an LLM agent SDK session (e.g. Claude Agent SDK)."""

    async def query(self, prompt: str) -> AsyncIterator[dict[str, Any]]: ...


# Type alias for the SDK factory callable.
AgentSDKFactory = Callable[[], AgentSDKSession]


# ---------------------------------------------------------------------------
# CoderAgent
# ---------------------------------------------------------------------------


class CoderAgent(BaseAgent):
    """Coding agent that delegates execution to a sandbox and LLM queries to an SDK.

    All external dependencies are injected via constructor arguments and defined
    as protocols, so tests can use lightweight fakes without importing real
    libraries (claude-agent-sdk, e2b, etc.).
    """

    def __init__(
        self,
        persona: AgentPersona,
        event_bus: asyncio.Queue[Any],
        *,
        sandbox_provider: SandboxProvider | None = None,
        agent_sdk_factory: AgentSDKFactory | None = None,
        repo_url: str = "",
        max_tokens_per_session: int = 100_000,
        tick_interval: float = 0.05,
    ) -> None:
        super().__init__(persona, event_bus, tick_interval=tick_interval)
        self._sandbox_provider = sandbox_provider
        self._agent_sdk_factory = agent_sdk_factory
        self._repo_url = repo_url
        self._max_tokens_per_session = max_tokens_per_session
        self._session_tokens_used: int = 0
        self._active_sandbox: SandboxProtocol | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def session_tokens_used(self) -> int:
        """Return the number of tokens consumed in the current session."""
        return self._session_tokens_used

    @property
    def has_sandbox(self) -> bool:
        """Return True if a sandbox provider is configured."""
        return self._sandbox_provider is not None

    @property
    def has_sdk(self) -> bool:
        """Return True if an agent SDK factory is configured."""
        return self._agent_sdk_factory is not None

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    async def _call_llm(self, event: Any, rag_results: list[Any]) -> Any:
        """Query the agent SDK if available; otherwise return None."""
        if self._agent_sdk_factory is None:
            return None

        if self._session_tokens_used >= self._max_tokens_per_session:
            log.warning(
                "coder_agent.token_budget_exceeded",
                agent=self.name,
                used=self._session_tokens_used,
                max=self._max_tokens_per_session,
            )
            return None

        prompt = self._build_prompt(event, rag_results)
        session = self._agent_sdk_factory()

        collected_content: list[str] = []
        try:
            async for chunk in session.query(prompt):
                content = chunk.get("content", "")
                tokens = chunk.get("tokens", 0)
                self._session_tokens_used += tokens
                if content:
                    collected_content.append(content)

                if self._session_tokens_used >= self._max_tokens_per_session:
                    log.warning(
                        "coder_agent.token_budget_hit_mid_stream",
                        agent=self.name,
                        used=self._session_tokens_used,
                    )
                    break
        except Exception as exc:
            log.error("coder_agent.sdk_error", agent=self.name, error=str(exc))
            return None

        return "".join(collected_content) if collected_content else None

    async def _emit_events(self, llm_response: Any, tool_results: list[Any]) -> None:
        """Emit an agent_message event if the LLM produced content."""
        if llm_response is None or not llm_response:
            return

        await self._event_bus.put(
            {
                "type": "agent_message",
                "source": self.name,
                "content": llm_response,
            }
        )

    # ------------------------------------------------------------------
    # Sandbox execution
    # ------------------------------------------------------------------

    async def _execute_in_sandbox(self, code: str) -> str:
        """Run a command in the sandbox and return stdout.

        Returns an error description string if no sandbox is available.
        """
        if self._sandbox_provider is None:
            return "[error] No sandbox provider configured."

        try:
            if self._active_sandbox is None:
                self._active_sandbox = await self._sandbox_provider.create()
                log.info("coder_agent.sandbox_created", agent=self.name)

            result = await self._active_sandbox.run_command(code)

            if result.exit_code != 0:
                log.warning(
                    "coder_agent.sandbox_command_failed",
                    agent=self.name,
                    exit_code=result.exit_code,
                    stderr=result.stderr[:200],
                )
                return f"[exit {result.exit_code}] {result.stderr}"

            return result.stdout
        except Exception as exc:
            log.error("coder_agent.sandbox_error", agent=self.name, error=str(exc))
            return f"[error] {exc}"

    # ------------------------------------------------------------------
    # Task handling
    # ------------------------------------------------------------------

    async def _handle_task_assigned(self, event: Any) -> CodingTaskResult:
        """Process a task_assigned event through the coding workflow.

        Steps:
        1. Extract task description from the event payload.
        2. Query the SDK for a coding plan.
        3. Execute commands in the sandbox (if available).
        4. Return the coding task result.
        """
        payload = event if isinstance(event, dict) else {}
        task_description = payload.get("payload", {}).get(
            "description", payload.get("description", str(event))
        )

        log.info(
            "coder_agent.task_started",
            agent=self.name,
            task=task_description[:100],
        )

        # Query SDK for a plan / code.
        llm_response = await self._call_llm(event, [])

        files_changed: list[str] = []
        pr_url: str | None = None
        error: str | None = None

        if llm_response:
            # Execute in sandbox if available.
            if self.has_sandbox:
                sandbox_output = await self._execute_in_sandbox(llm_response)
                if sandbox_output.startswith("[error]"):
                    error = sandbox_output
                else:
                    files_changed = _extract_files(sandbox_output)
        else:
            error = "No LLM response received."

        result = CodingTaskResult(
            task_description=task_description,
            files_changed=files_changed,
            pr_url=pr_url,
            success=error is None,
            error=error,
        )

        # Emit result as an event.
        await self._event_bus.put(
            {
                "type": "coding_task_completed",
                "source": self.name,
                "result": result.model_dump(),
            }
        )

        log.info(
            "coder_agent.task_completed",
            agent=self.name,
            success=result.success,
            files_changed=len(files_changed),
        )

        return result

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Stop the agent and clean up sandbox resources."""
        if self._active_sandbox is not None:
            try:
                await self._active_sandbox.kill()
            except Exception as exc:
                log.warning("coder_agent.sandbox_cleanup_error", error=str(exc))
            self._active_sandbox = None
        await super().stop()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, event: Any, rag_results: list[Any]) -> str:
        """Assemble a prompt from the event and RAG context."""
        parts: list[str] = []

        if self._persona.backstory:
            parts.append(f"Context: {self._persona.backstory}")

        if self._repo_url:
            parts.append(f"Repository: {self._repo_url}")

        if rag_results:
            parts.append("Relevant knowledge:")
            for r in rag_results:
                parts.append(f"  - {r}")

        event_str = str(event) if not isinstance(event, str) else event
        parts.append(f"Task: {event_str}")

        return "\n".join(parts)


def _extract_files(sandbox_output: str) -> list[str]:
    """Extract file paths from sandbox output.

    A simple heuristic: lines that look like file paths (contain '/' or '.').
    """
    files: list[str] = []
    for line in sandbox_output.strip().splitlines():
        line = line.strip()
        if line and ("/" in line or "." in line) and " " not in line:
            files.append(line)
    return files
