"""SandboxManager: wraps E2B AsyncSandbox for isolated code execution."""

from __future__ import annotations

import os
import time
from types import TracebackType
from typing import Any

import structlog

from entwine.agents.coder_models import CommandResult

log = structlog.get_logger(__name__)

# Conditional import — e2b is an optional dependency.
try:
    from e2b import AsyncSandbox  # type: ignore[import-untyped]

    E2B_AVAILABLE = True
except ImportError:
    AsyncSandbox = None  # type: ignore[assignment, misc]
    E2B_AVAILABLE = False


class SandboxTimeout(Exception):
    """Raised when the sandbox session exceeds its configured timeout."""


class SandboxManager:
    """Manages an E2B Firecracker microVM sandbox lifecycle.

    Implements the SandboxProtocol and SandboxProvider interfaces defined
    in ``entwine.agents.coder``.
    """

    def __init__(self, *, timeout: float = 300.0, api_key: str | None = None) -> None:
        self._timeout = timeout
        self._api_key = api_key
        self._sandbox: Any | None = None
        self._created_at: float | None = None

    # ------------------------------------------------------------------
    # SandboxProvider protocol: create()
    # ------------------------------------------------------------------

    async def create(self) -> SandboxManager:
        """Provision a new E2B sandbox. Returns self to satisfy SandboxProvider."""
        await self.create_sandbox()
        return self

    # ------------------------------------------------------------------
    # Sandbox lifecycle
    # ------------------------------------------------------------------

    async def create_sandbox(self) -> None:
        """Provision a new E2B Firecracker microVM."""
        if not E2B_AVAILABLE:
            raise RuntimeError(
                "e2b package is not installed. Install with: uv add e2b "
                "or pip install entwine[coder]"
            )

        kwargs: dict[str, Any] = {"timeout": int(self._timeout)}
        if self._api_key:
            kwargs["api_key"] = self._api_key

        self._sandbox = await AsyncSandbox.create(**kwargs)
        self._created_at = time.monotonic()
        log.info("sandbox.created", timeout=self._timeout)

    async def destroy_sandbox(self) -> None:
        """Tear down the sandbox and release all resources."""
        if self._sandbox is not None:
            try:
                await self._sandbox.kill()
            except Exception as exc:
                log.warning("sandbox.cleanup_error", error=str(exc))
            self._sandbox = None
            self._created_at = None
            log.info("sandbox.destroyed")

    @property
    def is_active(self) -> bool:
        """Return True if a sandbox is currently running."""
        return self._sandbox is not None

    # ------------------------------------------------------------------
    # SandboxProtocol: run_command, read_file, write_file, kill
    # ------------------------------------------------------------------

    async def run_command(self, cmd: str) -> CommandResult:
        """Execute a command inside the sandbox VM."""
        self._ensure_active()
        self._check_timeout()

        try:
            result = await self._sandbox.commands.run(cmd)
        except Exception as exc:
            log.error("sandbox.command_error", cmd=cmd[:100], error=str(exc))
            raise

        self._check_timeout()

        return CommandResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_code,
        )

    async def read_file(self, path: str) -> str:
        """Read a file from the sandbox filesystem."""
        self._ensure_active()
        self._check_timeout()
        content: str = await self._sandbox.files.read(path)
        return content

    async def write_file(self, path: str, content: str) -> None:
        """Write a file to the sandbox filesystem."""
        self._ensure_active()
        self._check_timeout()
        await self._sandbox.files.write(path, content)

    async def kill(self) -> None:
        """Destroy the sandbox. Alias for destroy_sandbox()."""
        await self.destroy_sandbox()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> SandboxManager:
        await self.create_sandbox()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.destroy_sandbox()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_active(self) -> None:
        if self._sandbox is None:
            raise RuntimeError("No active sandbox. Call create_sandbox() first.")

    def _check_timeout(self) -> None:
        if self._created_at is not None:
            wall_elapsed = time.monotonic() - self._created_at
            if wall_elapsed >= self._timeout:
                log.warning(
                    "sandbox.timeout_exceeded",
                    elapsed=wall_elapsed,
                    timeout=self._timeout,
                )
                # Schedule cleanup — we can't await here if called from sync context,
                # but destroy_sandbox will be called by the caller or context manager.
                raise SandboxTimeout(
                    f"Sandbox timeout exceeded: {wall_elapsed:.1f}s >= {self._timeout}s"
                )


def create_sandbox_manager(
    *, timeout: float = 300.0, api_key: str | None = None
) -> SandboxManager | None:
    """Factory: returns a SandboxManager if E2B is available and configured, else None."""
    if not E2B_AVAILABLE:
        log.info("sandbox.e2b_not_installed", msg="e2b package not available; sandbox disabled")
        return None

    resolved_key = api_key or os.environ.get("E2B_API_KEY")
    if not resolved_key:
        log.info("sandbox.no_api_key", msg="E2B_API_KEY not set; sandbox disabled")
        return None

    return SandboxManager(timeout=timeout, api_key=resolved_key)
