"""Unit tests for StandardAgent with mocked dependencies."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from entsim.agents.models import AgentPersona, AgentState
from entsim.agents.standard import StandardAgent, _parse_tool_calls
from entsim.llm.models import CompletionResponse, LLMTier
from entsim.rag.models import Document, SearchResult
from entsim.tools.models import ToolCall, ToolResult

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _persona(**overrides: Any) -> AgentPersona:
    defaults: dict[str, Any] = {
        "name": "test_agent",
        "role": "Tester",
        "goal": "Verify behaviour",
        "backstory": "Synthetic agent for tests.",
        "llm_tier": "standard",
        "tools": ["tool_a"],
        "rag_access": ["docs"],
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


def _bus() -> asyncio.Queue[Any]:
    return asyncio.Queue()


def _completion(content: str = "Hello from LLM") -> CompletionResponse:
    return CompletionResponse(
        tier=LLMTier.STANDARD,
        model="test-model",
        content=content,
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.0,
    )


class FakeLLMRouter:
    """Minimal fake that records calls and returns a canned response."""

    def __init__(self, response: CompletionResponse | None = None) -> None:
        self.response = response or _completion()
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        self.calls.append({"tier": tier, "messages": messages, "tools": tools})
        return self.response


class FakeKnowledgeStore:
    """Minimal fake returning canned search results."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.calls: list[dict[str, Any]] = []

    async def search(self, query: str, agent_role: str, limit: int = 5) -> list[SearchResult]:
        self.calls.append({"query": query, "agent_role": agent_role, "limit": limit})
        return self.results


class FakeToolDispatcher:
    """Minimal fake that records dispatched calls."""

    def __init__(self, results: list[ToolResult] | None = None) -> None:
        self.results = results or []
        self.calls: list[list[ToolCall]] = []

    async def dispatch_many(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        self.calls.append(tool_calls)
        return self.results


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_all_none_deps(self) -> None:
        agent = StandardAgent(persona=_persona(), event_bus=_bus())
        assert agent.state == AgentState.READY
        assert agent._llm_router is None
        assert agent._knowledge_store is None
        assert agent._tool_dispatcher is None

    def test_with_all_deps(self) -> None:
        agent = StandardAgent(
            persona=_persona(),
            event_bus=_bus(),
            llm_router=FakeLLMRouter(),  # type: ignore[arg-type]
            knowledge_store=FakeKnowledgeStore(),  # type: ignore[arg-type]
            tool_dispatcher=FakeToolDispatcher(),  # type: ignore[arg-type]
            world_context="Year 2025, Q1",
        )
        assert agent.state == AgentState.READY
        assert agent._world_context == "Year 2025, Q1"


# ---------------------------------------------------------------------------
# _query_rag
# ---------------------------------------------------------------------------


class TestQueryRag:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_store(self) -> None:
        agent = StandardAgent(persona=_persona(), event_bus=_bus())
        result = await agent._query_rag({"type": "test"})
        assert result == []

    @pytest.mark.asyncio
    async def test_calls_store_with_correct_params(self) -> None:
        store = FakeKnowledgeStore(
            results=[
                SearchResult(
                    document=Document(id="1", content="doc content"),
                    score=0.9,
                )
            ]
        )
        agent = StandardAgent(
            persona=_persona(),
            event_bus=_bus(),
            knowledge_store=store,  # type: ignore[arg-type]
        )
        results = await agent._query_rag({"type": "question", "text": "budget?"})
        assert len(results) == 1
        assert results[0].document.content == "doc content"
        assert len(store.calls) == 1
        assert store.calls[0]["agent_role"] == "Tester"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_rag_access(self) -> None:
        store = FakeKnowledgeStore()
        agent = StandardAgent(
            persona=_persona(rag_access=[]),
            event_bus=_bus(),
            knowledge_store=store,  # type: ignore[arg-type]
        )
        results = await agent._query_rag("some query")
        assert results == []
        assert len(store.calls) == 0  # should not even call the store


# ---------------------------------------------------------------------------
# _call_llm
# ---------------------------------------------------------------------------


class TestCallLlm:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_router(self) -> None:
        agent = StandardAgent(persona=_persona(), event_bus=_bus())
        result = await agent._call_llm({"type": "test"}, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_calls_router_with_correct_tier(self) -> None:
        router = FakeLLMRouter()
        agent = StandardAgent(
            persona=_persona(llm_tier="routine"),
            event_bus=_bus(),
            llm_router=router,  # type: ignore[arg-type]
        )
        response = await agent._call_llm({"type": "test"}, [])
        assert response is not None
        assert response.content == "Hello from LLM"
        assert len(router.calls) == 1
        assert router.calls[0]["tier"] == LLMTier.ROUTINE

    @pytest.mark.asyncio
    async def test_includes_rag_in_messages(self) -> None:
        router = FakeLLMRouter()
        rag = [
            SearchResult(
                document=Document(id="1", content="relevant info"),
                score=0.95,
            )
        ]
        agent = StandardAgent(
            persona=_persona(),
            event_bus=_bus(),
            llm_router=router,  # type: ignore[arg-type]
        )
        await agent._call_llm({"type": "test"}, rag)
        messages = router.calls[0]["messages"]
        # The user message should contain the RAG content.
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert any("relevant info" in m["content"] for m in user_msgs)


# ---------------------------------------------------------------------------
# _dispatch_tools
# ---------------------------------------------------------------------------


class TestDispatchTools:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_dispatcher(self) -> None:
        agent = StandardAgent(persona=_persona(), event_bus=_bus())
        result = await agent._dispatch_tools(_completion())
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_response_is_none(self) -> None:
        dispatcher = FakeToolDispatcher()
        agent = StandardAgent(
            persona=_persona(),
            event_bus=_bus(),
            tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        )
        result = await agent._dispatch_tools(None)
        assert result == []

    @pytest.mark.asyncio
    async def test_dispatches_parsed_tool_calls(self) -> None:
        tool_result = ToolResult(call_id="c1", name="tool_a", output="ok")
        dispatcher = FakeToolDispatcher(results=[tool_result])
        agent = StandardAgent(
            persona=_persona(),
            event_bus=_bus(),
            tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        )
        content = '<tool_call>{"name": "tool_a", "arguments": {"x": 1}}</tool_call>'
        response = _completion(content)
        results = await agent._dispatch_tools(response)
        assert len(results) == 1
        assert results[0].name == "tool_a"
        assert len(dispatcher.calls) == 1
        assert dispatcher.calls[0][0].name == "tool_a"


# ---------------------------------------------------------------------------
# _emit_events
# ---------------------------------------------------------------------------


class TestEmitEvents:
    @pytest.mark.asyncio
    async def test_puts_message_on_bus(self) -> None:
        bus: asyncio.Queue[Any] = _bus()
        agent = StandardAgent(persona=_persona(), event_bus=bus)
        await agent._emit_events(_completion("output text"), [])
        assert not bus.empty()
        msg = bus.get_nowait()
        assert msg["type"] == "agent_message"
        assert msg["source"] == "test_agent"
        assert msg["content"] == "output text"

    @pytest.mark.asyncio
    async def test_no_emit_when_response_is_none(self) -> None:
        bus: asyncio.Queue[Any] = _bus()
        agent = StandardAgent(persona=_persona(), event_bus=bus)
        await agent._emit_events(None, [])
        assert bus.empty()

    @pytest.mark.asyncio
    async def test_no_emit_when_content_empty(self) -> None:
        bus: asyncio.Queue[Any] = _bus()
        agent = StandardAgent(persona=_persona(), event_bus=bus)
        await agent._emit_events(_completion(""), [])
        assert bus.empty()


# ---------------------------------------------------------------------------
# _parse_tool_calls helper
# ---------------------------------------------------------------------------


class TestParseToolCalls:
    def test_empty_string(self) -> None:
        assert _parse_tool_calls("") == []

    def test_no_pattern(self) -> None:
        assert _parse_tool_calls("Just some text without tools.") == []

    def test_single_tool_call(self) -> None:
        content = '<tool_call>{"name": "tool_a", "arguments": {"x": 1}}</tool_call>'
        calls = _parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0].name == "tool_a"
        assert calls[0].arguments == {"x": 1}

    def test_multiple_tool_calls(self) -> None:
        content = (
            '<tool_call>{"name": "a", "arguments": {}}</tool_call>'
            " some text "
            '<tool_call>{"name": "b", "arguments": {"k": "v"}}</tool_call>'
        )
        calls = _parse_tool_calls(content)
        assert len(calls) == 2
        assert calls[0].name == "a"
        assert calls[1].name == "b"


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------


class _OneShotRouter:
    """Fake router that returns content on the first call, empty on subsequent."""

    def __init__(self, content: str = "I have decided.") -> None:
        self.calls: list[dict[str, Any]] = []
        self._content = content

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        self.calls.append({"tier": tier, "messages": messages, "tools": tools})
        # Only return real content on the first call.
        content = self._content if len(self.calls) == 1 else ""
        return _completion(content)


@pytest.mark.asyncio
async def test_full_lifecycle_with_mocked_llm() -> None:
    """Start the agent, push an event, verify it processes and emits."""
    bus: asyncio.Queue[Any] = _bus()
    router = _OneShotRouter("I have decided.")
    agent = StandardAgent(
        persona=_persona(),
        event_bus=bus,
        llm_router=router,  # type: ignore[arg-type]
        world_context="Simulation tick 1",
    )

    agent.start()
    await asyncio.sleep(0)

    # Push an event for the agent to process.
    await bus.put({"type": "task_assigned", "payload": "do something"})

    # Give the loop time to process the event and emit results.
    await asyncio.sleep(0.3)

    assert len(router.calls) >= 1

    # The agent should have emitted a message back onto the bus (possibly
    # consumed by itself in a subsequent tick). Check short-term memory instead,
    # which reliably records every processed tick.
    assert len(agent.short_term_memory) >= 1
    first_tick = agent.short_term_memory[0]
    assert first_tick["llm_response"] is not None
    assert first_tick["llm_response"].content == "I have decided."

    await agent.stop()
    assert agent.state == AgentState.STOPPED


# ---------------------------------------------------------------------------
# _dispatch_tools — non-CompletionResponse input (line 109)
# ---------------------------------------------------------------------------


class TestDispatchToolsEdgeCases:
    @pytest.mark.asyncio
    async def test_returns_empty_for_non_completion_response(self) -> None:
        dispatcher = FakeToolDispatcher()
        agent = StandardAgent(
            persona=_persona(),
            event_bus=_bus(),
            tool_dispatcher=dispatcher,  # type: ignore[arg-type]
        )
        result = await agent._dispatch_tools("not a CompletionResponse")
        assert result == []
        assert len(dispatcher.calls) == 0


# ---------------------------------------------------------------------------
# _emit_events — non-CompletionResponse input (line 129)
# ---------------------------------------------------------------------------


class TestEmitEventsEdgeCases:
    @pytest.mark.asyncio
    async def test_no_emit_for_non_completion_response(self) -> None:
        bus: asyncio.Queue[Any] = _bus()
        agent = StandardAgent(persona=_persona(), event_bus=bus)
        await agent._emit_events("plain string, not CompletionResponse", [])
        assert bus.empty()


# ---------------------------------------------------------------------------
# _parse_tool_calls — invalid JSON branch (lines 172-173)
# ---------------------------------------------------------------------------


class TestParseToolCallsEdgeCases:
    def test_invalid_json_is_skipped(self) -> None:
        content = "<tool_call>not valid json</tool_call>"
        calls = _parse_tool_calls(content)
        assert calls == []

    def test_missing_name_key_is_skipped(self) -> None:
        content = '<tool_call>{"arguments": {"x": 1}}</tool_call>'
        calls = _parse_tool_calls(content)
        assert calls == []

    def test_valid_and_invalid_mixed(self) -> None:
        content = (
            '<tool_call>{"name": "good_tool", "arguments": {}}</tool_call>'
            "<tool_call>INVALID</tool_call>"
        )
        calls = _parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0].name == "good_tool"
