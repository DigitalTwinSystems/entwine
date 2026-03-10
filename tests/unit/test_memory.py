"""Unit tests for MemoryStore long-term memory persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from entsim.agents.memory import MemoryStore
from entsim.rag.models import Document, SearchResult
from entsim.rag.store import KnowledgeStore


@pytest.fixture()
def mock_knowledge_store() -> MagicMock:
    store = MagicMock(spec=KnowledgeStore)
    store.upsert = AsyncMock()
    store.search = AsyncMock(return_value=[])
    return store


@pytest.fixture()
def memory_store(mock_knowledge_store: MagicMock) -> MemoryStore:
    return MemoryStore(knowledge_store=mock_knowledge_store, agent_id="agent-42")


# ---------------------------------------------------------------------------
# persist
# ---------------------------------------------------------------------------


class TestPersist:
    @pytest.mark.asyncio
    async def test_persist_calls_upsert(
        self,
        memory_store: MemoryStore,
        mock_knowledge_store: MagicMock,
    ) -> None:
        tick = {"event": "price_change", "llm_response": "noted", "tool_results": []}
        await memory_store.persist(tick)

        mock_knowledge_store.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_creates_document_with_correct_metadata(
        self,
        memory_store: MemoryStore,
        mock_knowledge_store: MagicMock,
    ) -> None:
        tick = {"event": "price_change", "llm_response": "noted", "tool_results": []}
        await memory_store.persist(tick)

        call_args = mock_knowledge_store.upsert.call_args
        docs: list[Document] = call_args[0][0] if call_args[0] else call_args[1]["documents"]
        assert len(docs) == 1

        doc = docs[0]
        assert doc.id.startswith("agent-42:")
        assert doc.metadata["agent_id"] == "agent-42"
        assert doc.metadata["type"] == "tick_memory"
        assert "timestamp" in doc.metadata
        assert "agent-42" in doc.metadata["accessible_roles"]

    @pytest.mark.asyncio
    async def test_persist_document_content_is_nonempty(
        self,
        memory_store: MemoryStore,
        mock_knowledge_store: MagicMock,
    ) -> None:
        tick = {"event": "meeting", "llm_response": "schedule it", "tool_results": ["ok"]}
        await memory_store.persist(tick)

        docs: list[Document] = mock_knowledge_store.upsert.call_args[0][0]
        assert len(docs[0].content) > 0


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------


class TestRecall:
    @pytest.mark.asyncio
    async def test_recall_calls_search(
        self,
        memory_store: MemoryStore,
        mock_knowledge_store: MagicMock,
    ) -> None:
        await memory_store.recall("quarterly roadmap")

        mock_knowledge_store.search.assert_awaited_once_with(
            query="quarterly roadmap",
            agent_role="agent-42",
            limit=5,
        )

    @pytest.mark.asyncio
    async def test_recall_returns_search_results(
        self,
        memory_store: MemoryStore,
        mock_knowledge_store: MagicMock,
    ) -> None:
        expected = [
            SearchResult(
                document=Document(id="agent-42:abc", content="some memory"),
                score=0.88,
            ),
        ]
        mock_knowledge_store.search.return_value = expected

        results = await memory_store.recall("budget")
        assert results == expected

    @pytest.mark.asyncio
    async def test_recall_respects_limit(
        self,
        memory_store: MemoryStore,
        mock_knowledge_store: MagicMock,
    ) -> None:
        await memory_store.recall("anything", limit=3)

        mock_knowledge_store.search.assert_awaited_once_with(
            query="anything",
            agent_role="agent-42",
            limit=3,
        )


# ---------------------------------------------------------------------------
# _summarize_tick
# ---------------------------------------------------------------------------


class TestSummarizeTick:
    def test_produces_nonempty_string(self) -> None:
        tick = {"event": "alert", "llm_response": "ack", "tool_results": ["done"]}
        result = MemoryStore._summarize_tick(tick)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_handles_none_values_gracefully(self) -> None:
        tick = {"event": None, "llm_response": None, "tool_results": None}
        result = MemoryStore._summarize_tick(tick)
        assert isinstance(result, str)
        assert len(result) > 0  # Should produce "Empty tick"

    def test_handles_empty_dict(self) -> None:
        result = MemoryStore._summarize_tick({})
        assert result == "Empty tick"

    def test_includes_event_info(self) -> None:
        tick = {"event": "budget_update", "llm_response": None, "tool_results": None}
        result = MemoryStore._summarize_tick(tick)
        assert "budget_update" in result

    def test_truncates_long_llm_response(self) -> None:
        tick = {"event": None, "llm_response": "x" * 500, "tool_results": None}
        result = MemoryStore._summarize_tick(tick)
        # The snippet should be at most 200 chars of the original
        assert len(result) < 500
