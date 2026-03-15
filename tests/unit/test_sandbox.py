"""Tests for entwine.sandbox.manager — SandboxManager with mocked E2B."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from entwine.agents.coder_models import CommandResult
from entwine.sandbox.manager import (
    SandboxManager,
    SandboxTimeout,
    create_sandbox_manager,
)

# ---------------------------------------------------------------------------
# Helpers: mock E2B sandbox
# ---------------------------------------------------------------------------


def _make_mock_sandbox() -> AsyncMock:
    """Create a mock that mimics AsyncSandbox."""
    sbx = AsyncMock()

    cmd_result = MagicMock()
    cmd_result.stdout = "hello\n"
    cmd_result.stderr = ""
    cmd_result.exit_code = 0
    sbx.commands.run = AsyncMock(return_value=cmd_result)

    sbx.files.read = AsyncMock(return_value="file content")
    sbx.files.write = AsyncMock()
    sbx.kill = AsyncMock()

    return sbx


@contextmanager
def _patch_e2b(mock_sbx: Any) -> Generator[MagicMock, None, None]:
    """Patch both E2B_AVAILABLE and AsyncSandbox for unit tests."""
    with (
        patch("entwine.sandbox.manager.E2B_AVAILABLE", True),
        patch("entwine.sandbox.manager.AsyncSandbox") as mock_cls,
    ):
        mock_cls.create = AsyncMock(return_value=mock_sbx)
        yield mock_cls


# ---------------------------------------------------------------------------
# SandboxManager tests
# ---------------------------------------------------------------------------


class TestSandboxManagerCreate:
    async def test_create_sandbox_provisions_vm(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx) as mock_cls:
            mgr = SandboxManager(timeout=120.0)
            await mgr.create_sandbox()

            mock_cls.create.assert_awaited_once_with(timeout=120)
            assert mgr.is_active

    async def test_create_sandbox_with_api_key(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx) as mock_cls:
            mgr = SandboxManager(timeout=60.0, api_key="test-key")
            await mgr.create_sandbox()

            mock_cls.create.assert_awaited_once_with(timeout=60, api_key="test-key")

    async def test_create_raises_if_e2b_not_installed(self) -> None:
        with patch("entwine.sandbox.manager.E2B_AVAILABLE", False):
            mgr = SandboxManager()
            with pytest.raises(RuntimeError, match="e2b package is not installed"):
                await mgr.create_sandbox()


class TestSandboxManagerCommands:
    async def test_run_command_returns_command_result(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()

            result = await mgr.run_command("echo hello")
            assert isinstance(result, CommandResult)
            assert result.stdout == "hello\n"
            assert result.stderr == ""
            assert result.exit_code == 0

    async def test_run_command_with_nonzero_exit(self) -> None:
        mock_sbx = _make_mock_sandbox()
        cmd_result = MagicMock()
        cmd_result.stdout = ""
        cmd_result.stderr = "not found"
        cmd_result.exit_code = 1
        mock_sbx.commands.run = AsyncMock(return_value=cmd_result)

        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()

            result = await mgr.run_command("bad-cmd")
            assert result.exit_code == 1
            assert result.stderr == "not found"

    async def test_run_command_raises_if_no_sandbox(self) -> None:
        mgr = SandboxManager()
        with pytest.raises(RuntimeError, match="No active sandbox"):
            await mgr.run_command("echo hi")


class TestSandboxManagerFiles:
    async def test_read_file_delegates_to_sandbox(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()

            content = await mgr.read_file("/tmp/test.txt")
            assert content == "file content"
            mock_sbx.files.read.assert_awaited_once_with("/tmp/test.txt")

    async def test_write_file_delegates_to_sandbox(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()

            await mgr.write_file("/tmp/test.txt", "new content")
            mock_sbx.files.write.assert_awaited_once_with("/tmp/test.txt", "new content")


class TestSandboxManagerDestroy:
    async def test_destroy_calls_kill_and_clears_state(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()
            assert mgr.is_active

            await mgr.destroy_sandbox()
            mock_sbx.kill.assert_awaited_once()
            assert not mgr.is_active

    async def test_destroy_handles_kill_error_gracefully(self) -> None:
        mock_sbx = _make_mock_sandbox()
        mock_sbx.kill = AsyncMock(side_effect=RuntimeError("kill failed"))
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()

            # Should not raise
            await mgr.destroy_sandbox()
            assert not mgr.is_active

    async def test_destroy_is_idempotent(self) -> None:
        mgr = SandboxManager()
        await mgr.destroy_sandbox()
        assert not mgr.is_active

    async def test_kill_alias(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)
            await mgr.create_sandbox()

            await mgr.kill()
            mock_sbx.kill.assert_awaited_once()
            assert not mgr.is_active


class TestSandboxTimeout:
    async def test_timeout_raises_sandbox_timeout(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=0.0)
            await mgr.create_sandbox()

            with pytest.raises(SandboxTimeout, match="timeout exceeded"):
                await mgr.run_command("echo hello")

    async def test_timeout_check_on_file_read(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=0.0)
            await mgr.create_sandbox()

            with pytest.raises(SandboxTimeout):
                await mgr.read_file("/tmp/f.txt")

    async def test_timeout_check_on_file_write(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=0.0)
            await mgr.create_sandbox()

            with pytest.raises(SandboxTimeout):
                await mgr.write_file("/tmp/f.txt", "x")


class TestContextManager:
    async def test_context_manager_creates_and_destroys(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)

            async with mgr:
                assert mgr.is_active

            assert not mgr.is_active
            mock_sbx.kill.assert_awaited_once()

    async def test_context_manager_cleans_up_on_error(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)

            with pytest.raises(ValueError, match="test error"):
                async with mgr:
                    raise ValueError("test error")

            assert not mgr.is_active
            mock_sbx.kill.assert_awaited_once()


class TestSandboxProviderProtocol:
    async def test_create_returns_self(self) -> None:
        mock_sbx = _make_mock_sandbox()
        with _patch_e2b(mock_sbx):
            mgr = SandboxManager(timeout=300.0)

            result = await mgr.create()
            assert result is mgr
            assert mgr.is_active

    def test_implements_sandbox_protocol(self) -> None:
        from entwine.agents.coder import SandboxProtocol

        mgr = SandboxManager(timeout=300.0)
        assert isinstance(mgr, SandboxProtocol)

    def test_implements_sandbox_provider(self) -> None:
        from entwine.agents.coder import SandboxProvider

        mgr = SandboxManager(timeout=300.0)
        assert isinstance(mgr, SandboxProvider)


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateSandboxManager:
    def test_returns_none_when_e2b_not_installed(self) -> None:
        with patch("entwine.sandbox.manager.E2B_AVAILABLE", False):
            result = create_sandbox_manager()
            assert result is None

    def test_returns_none_when_no_api_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "E2B_API_KEY"}
        with (
            patch("entwine.sandbox.manager.E2B_AVAILABLE", True),
            patch.dict(os.environ, env, clear=True),
        ):
            result = create_sandbox_manager()
            assert result is None

    def test_returns_manager_with_explicit_key(self) -> None:
        with patch("entwine.sandbox.manager.E2B_AVAILABLE", True):
            result = create_sandbox_manager(api_key="test-key-123")
            assert isinstance(result, SandboxManager)

    def test_returns_manager_with_env_key(self) -> None:
        with (
            patch("entwine.sandbox.manager.E2B_AVAILABLE", True),
            patch.dict(os.environ, {"E2B_API_KEY": "env-key-456"}),
        ):
            result = create_sandbox_manager()
            assert isinstance(result, SandboxManager)

    def test_custom_timeout(self) -> None:
        with patch("entwine.sandbox.manager.E2B_AVAILABLE", True):
            result = create_sandbox_manager(timeout=600.0, api_key="test-key")
            assert result is not None
            assert result._timeout == 600.0
