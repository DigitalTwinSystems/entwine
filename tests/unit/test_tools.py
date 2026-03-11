"""Unit tests for the tool dispatcher, models, and built-in tools."""

from __future__ import annotations

import pytest

from entwine.tools import ToolCall, ToolDispatcher, ToolResult
from entwine.tools.builtin import (
    create_github_issue,
    create_pr,
    delegate_task,
    draft_email,
    post_to_linkedin,
    post_to_slack,
    post_to_x,
    query_knowledge,
    read_company_metrics,
    read_crm,
    schedule_meeting,
    update_crm_ticket,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dispatcher_with_sync_tool() -> ToolDispatcher:
    """Create a dispatcher with a simple sync tool registered."""
    dispatcher = ToolDispatcher()

    def add(a: int, b: int) -> str:
        return str(a + b)

    dispatcher.register(
        name="add",
        handler=add,
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    )
    return dispatcher


def _make_dispatcher_with_async_tool() -> ToolDispatcher:
    """Create a dispatcher with a simple async tool registered."""
    dispatcher = ToolDispatcher()

    async def greet(name: str) -> str:
        return f"Hello, {name}!"

    dispatcher.register(
        name="greet",
        handler=greet,
        description="Greet someone",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    )
    return dispatcher


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestToolModels:
    def test_tool_call_fields(self) -> None:
        tc = ToolCall(name="foo", arguments={"x": 1}, call_id="c1")
        assert tc.name == "foo"
        assert tc.arguments == {"x": 1}
        assert tc.call_id == "c1"

    def test_tool_result_defaults_error_to_none(self) -> None:
        tr = ToolResult(call_id="c1", name="foo", output="ok")
        assert tr.error is None

    def test_tool_result_with_error(self) -> None:
        tr = ToolResult(call_id="c1", name="foo", output="", error="boom")
        assert tr.error == "boom"


# ---------------------------------------------------------------------------
# Dispatcher tests — sync handler
# ---------------------------------------------------------------------------


class TestDispatchSyncHandler:
    @pytest.mark.asyncio
    async def test_dispatch_sync_handler(self) -> None:
        dispatcher = _make_dispatcher_with_sync_tool()
        call = ToolCall(name="add", arguments={"a": 2, "b": 3}, call_id="c1")
        result = await dispatcher.dispatch(call)
        assert result.call_id == "c1"
        assert result.name == "add"
        assert result.output == "5"
        assert result.error is None


# ---------------------------------------------------------------------------
# Dispatcher tests — async handler
# ---------------------------------------------------------------------------


class TestDispatchAsyncHandler:
    @pytest.mark.asyncio
    async def test_dispatch_async_handler(self) -> None:
        dispatcher = _make_dispatcher_with_async_tool()
        call = ToolCall(name="greet", arguments={"name": "Alice"}, call_id="c2")
        result = await dispatcher.dispatch(call)
        assert result.call_id == "c2"
        assert result.name == "greet"
        assert result.output == "Hello, Alice!"
        assert result.error is None


# ---------------------------------------------------------------------------
# Dispatcher tests — error handling
# ---------------------------------------------------------------------------


class TestDispatchErrors:
    @pytest.mark.asyncio
    async def test_dispatch_handler_raises(self) -> None:
        dispatcher = ToolDispatcher()

        def fail() -> str:
            msg = "intentional failure"
            raise RuntimeError(msg)

        dispatcher.register(
            name="fail",
            handler=fail,
            description="Always fails",
            parameters={"type": "object", "properties": {}},
        )

        call = ToolCall(name="fail", arguments={}, call_id="c3")
        result = await dispatcher.dispatch(call)
        assert result.call_id == "c3"
        assert result.output == ""
        assert result.error is not None
        assert "intentional failure" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self) -> None:
        dispatcher = ToolDispatcher()
        call = ToolCall(name="nonexistent", arguments={}, call_id="c4")
        result = await dispatcher.dispatch(call)
        assert result.call_id == "c4"
        assert result.error is not None
        assert "Unknown tool" in result.error


# ---------------------------------------------------------------------------
# dispatch_many
# ---------------------------------------------------------------------------


class TestDispatchMany:
    @pytest.mark.asyncio
    async def test_dispatch_many_returns_ordered_results(self) -> None:
        dispatcher = _make_dispatcher_with_sync_tool()
        calls = [
            ToolCall(name="add", arguments={"a": 1, "b": 2}, call_id="m1"),
            ToolCall(name="add", arguments={"a": 10, "b": 20}, call_id="m2"),
        ]
        results = await dispatcher.dispatch_many(calls)
        assert len(results) == 2
        assert results[0].call_id == "m1"
        assert results[0].output == "3"
        assert results[1].call_id == "m2"
        assert results[1].output == "30"


# ---------------------------------------------------------------------------
# get_tool_definitions
# ---------------------------------------------------------------------------


class TestGetToolDefinitions:
    def test_tool_definitions_format(self) -> None:
        dispatcher = _make_dispatcher_with_sync_tool()
        defs = dispatcher.get_tool_definitions()
        assert len(defs) == 1
        defn = defs[0]
        assert defn["type"] == "function"
        assert defn["function"]["name"] == "add"
        assert defn["function"]["description"] == "Add two numbers"
        assert "properties" in defn["function"]["parameters"]

    def test_empty_dispatcher_returns_empty_list(self) -> None:
        dispatcher = ToolDispatcher()
        assert dispatcher.get_tool_definitions() == []


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------


class TestBuiltinTools:
    @pytest.mark.asyncio
    async def test_delegate_task_returns_string(self) -> None:
        result = await delegate_task(
            recipient="cmo", task_description="write blog post", priority="high"
        )
        assert isinstance(result, str)
        assert "cmo" in result
        assert "high" in result

    @pytest.mark.asyncio
    async def test_query_knowledge_returns_string(self) -> None:
        result = await query_knowledge(query="market trends", role="analyst")
        assert isinstance(result, str)
        assert "analyst" in result

    @pytest.mark.asyncio
    async def test_read_company_metrics_returns_string(self) -> None:
        result = await read_company_metrics()
        assert isinstance(result, str)
        assert "Metrics" in result

    @pytest.mark.asyncio
    async def test_schedule_meeting(self) -> None:
        result = await schedule_meeting(
            attendees="Alice, Bob", time="10:00", agenda="Sprint review"
        )
        assert "10:00" in result
        assert "Alice, Bob" in result

    @pytest.mark.asyncio
    async def test_draft_email(self) -> None:
        result = await draft_email(to="alice@acme.com", subject="Update", body="Here's the update.")
        assert "alice@acme.com" in result
        assert "Update" in result

    @pytest.mark.asyncio
    async def test_post_to_slack(self) -> None:
        result = await post_to_slack(channel="#general", message="Hello team")
        assert "#general" in result

    @pytest.mark.asyncio
    async def test_post_to_linkedin(self) -> None:
        result = await post_to_linkedin(content="Exciting product launch!")
        assert "LinkedIn" in result

    @pytest.mark.asyncio
    async def test_post_to_x(self) -> None:
        result = await post_to_x(content="New release out now!")
        assert "X" in result

    @pytest.mark.asyncio
    async def test_create_github_issue(self) -> None:
        result = await create_github_issue(title="Bug fix", body="Fix the auth bug", labels="bug")
        assert "Bug fix" in result
        assert "bug" in result

    @pytest.mark.asyncio
    async def test_create_pr(self) -> None:
        result = await create_pr(title="Add feature", body="New feature", branch="feat/new")
        assert "feat/new" in result

    @pytest.mark.asyncio
    async def test_read_crm(self) -> None:
        result = await read_crm(query="enterprise deals")
        assert "enterprise deals" in result

    @pytest.mark.asyncio
    async def test_update_crm_ticket(self) -> None:
        result = await update_crm_ticket(ticket_id="T-123", status="resolved", note="Fixed")
        assert "T-123" in result
        assert "resolved" in result

    @pytest.mark.asyncio
    async def test_update_crm_ticket_without_note(self) -> None:
        result = await update_crm_ticket(ticket_id="T-456", status="open")
        assert "T-456" in result
        assert "note" not in result
