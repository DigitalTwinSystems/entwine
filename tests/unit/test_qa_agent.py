"""Tests for entwine.agents.qa_agent — QA agent PR review."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from entwine.agents.models import AgentPersona, WorkingHours
from entwine.agents.qa_agent import QA_ALLOWED_TOOLS, QAAgent
from entwine.events.models import PROpened

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_persona() -> AgentPersona:
    return AgentPersona(
        name="qa-1",
        role="QA Engineer",
        goal="Review pull requests for quality",
        working_hours=WorkingHours(),
    )


def _make_pr_event(pr_number: int = 42) -> PROpened:
    return PROpened(
        source_agent="coder-1",
        payload={
            "pr_number": pr_number,
            "pr_url": f"https://github.com/acme/repo/pull/{pr_number}",
            "branch": "feat/new-feature",
            "title": "Add new feature",
        },
    )


# ---------------------------------------------------------------------------
# QAAgent construction tests
# ---------------------------------------------------------------------------


class TestQAAgentConstruction:
    def test_creates_without_sandbox(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)
        assert agent.name == "qa-1"

    def test_creates_with_adapter(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        adapter = AsyncMock()
        agent = QAAgent(_make_persona(), bus, platform_adapter=adapter)
        assert agent._adapter is adapter

    def test_no_sandbox_required(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)
        # QA agent should not have sandbox-related attributes
        assert not hasattr(agent, "_sandbox_provider")


class TestReadOnlyTools:
    def test_allowed_tools_are_read_only(self) -> None:
        assert "Read" in QA_ALLOWED_TOOLS
        assert "Glob" in QA_ALLOWED_TOOLS
        assert "Grep" in QA_ALLOWED_TOOLS
        assert "Write" not in QA_ALLOWED_TOOLS
        assert "Edit" not in QA_ALLOWED_TOOLS
        assert "Bash" not in QA_ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# handle_pr_opened tests
# ---------------------------------------------------------------------------


class TestHandlePROpened:
    async def test_processes_pr_event(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        result = await agent.handle_pr_opened(_make_pr_event())

        assert result["pr_number"] == 42
        assert isinstance(result["approved"], bool)
        assert isinstance(result["comments"], list)
        assert len(result["comments"]) > 0

    async def test_returns_approval_decision(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        result = await agent.handle_pr_opened(_make_pr_event())

        # Default _call_llm returns APPROVED
        assert result["approved"] is True


# ---------------------------------------------------------------------------
# Review comments tests
# ---------------------------------------------------------------------------


class TestReviewComments:
    async def test_posts_comments_via_adapter(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        adapter = AsyncMock()
        adapter.send = AsyncMock(return_value={"status": "ok", "comment_id": 1})
        agent = QAAgent(_make_persona(), bus, platform_adapter=adapter)

        await agent.handle_pr_opened(_make_pr_event())

        adapter.send.assert_awaited_once()
        call_args = adapter.send.call_args
        assert call_args[0][0] == "add_comment"
        assert call_args[0][1]["issue_number"] == 42
        assert "QA Review" in call_args[0][1]["body"]

    async def test_skips_comments_without_adapter(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        # Should not raise even without adapter
        result = await agent.handle_pr_opened(_make_pr_event())
        assert result["pr_number"] == 42

    async def test_handles_adapter_error_gracefully(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        adapter = AsyncMock()
        adapter.send = AsyncMock(side_effect=RuntimeError("API error"))
        agent = QAAgent(_make_persona(), bus, platform_adapter=adapter)

        # Should not raise
        result = await agent.handle_pr_opened(_make_pr_event())
        assert result["pr_number"] == 42


# ---------------------------------------------------------------------------
# ReviewComplete event tests
# ---------------------------------------------------------------------------


class TestReviewCompleteEvent:
    async def test_publishes_event_to_queue(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        await agent.handle_pr_opened(_make_pr_event())

        # Event should be in the queue
        assert not bus.empty()
        event = bus.get_nowait()
        assert event["type"] == "review_complete"
        assert event["source"] == "qa-1"
        assert event["pr_number"] == 42
        assert isinstance(event["approved"], bool)

    async def test_publishes_to_typed_bus(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        typed_bus = AsyncMock()
        typed_bus.publish = AsyncMock()
        agent = QAAgent(_make_persona(), queue, typed_bus=typed_bus)

        await agent.handle_pr_opened(_make_pr_event())

        typed_bus.publish.assert_awaited_once()
        event = typed_bus.publish.call_args[0][0]
        assert event.event_type == "review_complete"
        assert event.payload["pr_number"] == 42


# ---------------------------------------------------------------------------
# Review parsing tests
# ---------------------------------------------------------------------------


class TestQAAgentSDKSession:
    async def test_uses_sdk_with_allowed_tools(self) -> None:
        from unittest.mock import MagicMock as MM

        bus: asyncio.Queue = asyncio.Queue()

        mock_result = MM()
        mock_result.success = True
        mock_result.task_description = "CHANGES_REQUESTED\nMissing test for edge case"

        mock_session = MM()
        mock_session.run = AsyncMock(return_value=mock_result)

        factory_calls: list[dict] = []

        def mock_factory(**kwargs: object) -> MM:
            factory_calls.append(kwargs)
            return mock_session

        agent = QAAgent(_make_persona(), bus, sdk_session_factory=mock_factory)
        result = await agent.handle_pr_opened(_make_pr_event())

        # Factory called with read-only tools
        assert len(factory_calls) == 1
        assert factory_calls[0]["allowed_tools"] == ["Read", "Glob", "Grep"]
        # Review should not be approved (CHANGES_REQUESTED)
        assert result["approved"] is False

    async def test_falls_back_when_no_sdk(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)
        result = await agent.handle_pr_opened(_make_pr_event())
        # Default fallback returns APPROVED
        assert result["approved"] is True


class TestReviewParsing:
    def test_parse_approved(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        approved, comments = agent._parse_review("APPROVED\nLooks good.", 42)
        assert approved is True
        assert len(comments) > 0

    def test_parse_changes_requested(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        approved, _comments = agent._parse_review("CHANGES_REQUESTED\nFix the bug on line 42.", 42)
        assert approved is False

    def test_parse_none_response(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        approved, comments = agent._parse_review(None, 42)
        assert approved is True  # Auto-approve on no response
        assert "auto-approved" in comments[0]

    def test_parse_empty_response(self) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = QAAgent(_make_persona(), bus)

        approved, _comments = agent._parse_review("", 42)
        assert approved is True
