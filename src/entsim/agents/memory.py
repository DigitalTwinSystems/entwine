"""MemoryStore: long-term memory persistence to Qdrant via KnowledgeStore."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from entsim.rag.models import Document, SearchResult
from entsim.rag.store import KnowledgeStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class MemoryStore:
    """Persists agent tick summaries to Qdrant for long-term recall.

    Each tick is summarised into a concise text string and stored as a
    :class:`Document` in the shared :class:`KnowledgeStore`.  Retrieval
    is scoped to the owning agent via an ``agent_id`` metadata filter.
    """

    def __init__(self, knowledge_store: KnowledgeStore, agent_id: str) -> None:
        self._store = knowledge_store
        self._agent_id = agent_id

    async def persist(self, tick_summary: dict[str, Any]) -> None:
        """Generate a text summary from *tick_summary* and upsert it.

        Args:
            tick_summary: Dict typically containing ``event``,
                ``llm_response``, and ``tool_results`` keys.
        """
        summary_text = self._summarize_tick(tick_summary)
        doc_id = f"{self._agent_id}:{uuid.uuid4()}"
        doc = Document(
            id=doc_id,
            content=summary_text,
            metadata={
                "agent_id": self._agent_id,
                "timestamp": datetime.now(tz=UTC).isoformat(),
                "type": "tick_memory",
                "accessible_roles": [self._agent_id],
            },
        )
        await self._store.upsert([doc])
        logger.info(
            "memory.persisted",
            agent_id=self._agent_id,
            doc_id=doc_id,
        )

    async def recall(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search stored memories scoped to this agent.

        Args:
            query: Natural-language query string.
            limit: Maximum number of results to return.

        Returns:
            Ranked list of :class:`SearchResult` objects.
        """
        results = await self._store.search(
            query=query,
            agent_role=self._agent_id,
            limit=limit,
        )
        logger.info(
            "memory.recalled",
            agent_id=self._agent_id,
            num_results=len(results),
        )
        return results

    @staticmethod
    def _summarize_tick(tick: dict[str, Any]) -> str:
        """Produce a concise text summary from a tick dictionary.

        Extracts key information from ``event``, ``llm_response``, and
        ``tool_results`` entries, gracefully handling ``None`` values.
        """
        parts: list[str] = []

        event = tick.get("event")
        if event is not None:
            parts.append(f"Event: {event}")

        llm_response = tick.get("llm_response")
        if llm_response is not None:
            snippet = str(llm_response)[:200]
            parts.append(f"LLM response: {snippet}")

        tool_results = tick.get("tool_results")
        if tool_results:
            parts.append(f"Tool results: {tool_results}")

        return "; ".join(parts) if parts else "Empty tick"
