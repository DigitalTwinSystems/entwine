"""StandardAgent: concrete LLM-powered agent backed by RAG and tool dispatch."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from entwine.agents.base import BaseAgent
from entwine.agents.models import AgentPersona
from entwine.agents.prompts import assemble_messages, build_system_prompt
from entwine.events.models import Event
from entwine.llm.models import CompletionResponse, LLMTier
from entwine.llm.router import LLMRouter
from entwine.observability.cost_tracker import CostTracker
from entwine.rag.models import SearchResult
from entwine.rag.store import KnowledgeStore
from entwine.tools.dispatcher import ToolDispatcher
from entwine.tools.models import ToolCall, ToolResult

log = structlog.get_logger(__name__)

# Map config tier names to LLMTier enum values.
_TIER_MAP: dict[str, LLMTier] = {
    "routine": LLMTier.ROUTINE,
    "fast": LLMTier.ROUTINE,
    "standard": LLMTier.STANDARD,
    "complex": LLMTier.COMPLEX,
    "premium": LLMTier.COMPLEX,
}


class StandardAgent(BaseAgent):
    """First concrete agent: wires up LLM, RAG, and tool dispatch.

    All external dependencies are optional so the agent degrades
    gracefully (e.g. no LLM router → ``_call_llm`` returns ``None``).
    """

    def __init__(
        self,
        persona: AgentPersona,
        event_bus: asyncio.Queue[Any],
        *,
        llm_router: LLMRouter | None = None,
        knowledge_store: KnowledgeStore | None = None,
        tool_dispatcher: ToolDispatcher | None = None,
        cost_tracker: CostTracker | None = None,
        world_context: str = "",
        tick_interval: float = 0.05,
    ) -> None:
        super().__init__(persona, event_bus, tick_interval=tick_interval)
        self._llm_router = llm_router
        self._knowledge_store = knowledge_store
        self._tool_dispatcher = tool_dispatcher
        self._cost_tracker = cost_tracker
        self._world_context = world_context

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    async def _query_rag(self, event: Any) -> list[SearchResult]:
        """Query the knowledge store for context relevant to *event*."""
        if self._knowledge_store is None:
            return []

        query_text = str(event) if not isinstance(event, str) else event
        collection = self._persona.rag_access[0] if self._persona.rag_access else None
        if collection is None:
            return []

        results = await self._knowledge_store.search(
            query=query_text,
            agent_role=self._persona.role,
        )
        log.debug(
            "standard_agent.rag_results",
            agent=self.name,
            num_results=len(results),
        )
        return results

    async def _call_llm(self, event: Any, rag_results: list[Any]) -> CompletionResponse | None:
        """Build messages and call the LLM router."""
        if self._llm_router is None:
            return None

        system_prompt = build_system_prompt(
            self._persona,
            available_tools=self._persona.tools or None,
            world_context=self._world_context,
            org_context=getattr(self, "_org_context", ""),
        )

        rag_strings = [r.document.content for r in rag_results if isinstance(r, SearchResult)]

        # Format the event for the LLM context.
        if isinstance(event, Event):
            event_text: Any = {
                "type": event.event_type,
                "from": event.source_agent,
                **event.payload,
            }
        else:
            event_text = event

        messages = assemble_messages(
            system_prompt=system_prompt,
            short_term_memory=list(self.short_term_memory),
            current_event=event_text,
            rag_results=rag_strings or None,
        )

        tier = _TIER_MAP.get(self._persona.llm_tier, LLMTier.STANDARD)

        try:
            response = await self._llm_router.complete(tier=tier, messages=messages)
        except Exception:
            log.exception("standard_agent.llm_error", agent=self.name)
            return None

        # Record cost if tracker is available.
        if self._cost_tracker is not None:
            try:
                self._cost_tracker.record(
                    agent_name=self.name,
                    cost_usd=response.cost_usd,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
            except Exception:
                log.warning("standard_agent.budget_exceeded", agent=self.name)

        log.debug(
            "standard_agent.llm_response",
            agent=self.name,
            model=response.model,
            tokens=response.output_tokens,
        )
        return response

    async def _dispatch_tools(self, llm_response: Any) -> list[ToolResult]:
        """Parse tool calls from the LLM response and dispatch them."""
        if self._tool_dispatcher is None or llm_response is None:
            return []

        if not isinstance(llm_response, CompletionResponse):
            return []

        tool_calls = _parse_tool_calls(llm_response.content)
        if not tool_calls:
            return []

        results = await self._tool_dispatcher.dispatch_many(tool_calls)
        log.debug(
            "standard_agent.tool_results",
            agent=self.name,
            num_calls=len(tool_calls),
            num_results=len(results),
        )
        return results

    async def _emit_events(self, llm_response: Any, tool_results: list[Any]) -> None:
        """Put a message event on the bus if the LLM produced content."""
        if llm_response is None:
            return
        if not isinstance(llm_response, CompletionResponse):
            return
        if not llm_response.content:
            return

        await self._event_bus.put(
            {
                "type": "agent_message",
                "source": self.name,
                "content": llm_response.content,
            }
        )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _parse_tool_calls(content: str) -> list[ToolCall]:
    """Extract tool-call blocks from LLM text content.

    Looks for a simple ``<tool_call>`` XML-style pattern:

        <tool_call>{"name": "...", "arguments": {...}}</tool_call>

    Returns an empty list when no pattern is found.
    """
    import json
    import re
    import uuid

    pattern = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
    calls: list[ToolCall] = []
    for match in pattern.finditer(content):
        try:
            data = json.loads(match.group(1).strip())
            calls.append(
                ToolCall(
                    name=data["name"],
                    arguments=data.get("arguments", {}),
                    call_id=data.get("call_id", str(uuid.uuid4())),
                )
            )
        except (json.JSONDecodeError, KeyError):
            log.warning("standard_agent.invalid_tool_call", raw=match.group(1))
    return calls
