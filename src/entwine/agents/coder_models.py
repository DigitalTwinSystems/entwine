"""Data models for the CoderAgent: sandbox sessions and coding task results."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CommandResult(BaseModel):
    """Result of executing a command in a sandbox."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class SandboxSession(BaseModel):
    """Tracks an active sandbox session."""

    sandbox_id: str
    repo_url: str = ""
    created_at: datetime = Field(default_factory=_utc_now)
    is_active: bool = True


class CodingTaskResult(BaseModel):
    """Outcome of a coding task processed by the CoderAgent."""

    task_description: str
    files_changed: list[str] = Field(default_factory=list)
    pr_url: str | None = None
    success: bool = True
    error: str | None = None
