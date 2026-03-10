"""Event models for the entwine event bus."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """Base event model shared by all event types."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utc_now)
    source_agent: str
    event_type: str
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskAssigned(Event):
    """Emitted when a task is assigned to an agent."""

    event_type: str = "task_assigned"


class TaskCompleted(Event):
    """Emitted when an agent completes a task."""

    event_type: str = "task_completed"


class MessageSent(Event):
    """Emitted when an agent sends a message to another agent or broadcasts."""

    event_type: str = "message_sent"


class PlatformAction(Event):
    """Emitted when an agent invokes an external platform tool."""

    event_type: str = "platform_action"


class AgentStateChanged(Event):
    """Emitted when an agent transitions between lifecycle states."""

    event_type: str = "agent_state_changed"


class SystemEvent(Event):
    """Emitted for simulation-level system notifications."""

    event_type: str = "system_event"
