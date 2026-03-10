"""BaseAgent: lifecycle management, memory, and the main async loop."""

from __future__ import annotations

import asyncio
import collections
from typing import Any

import structlog

from entsim.agents.models import AgentPersona, AgentState

log = structlog.get_logger(__name__)

# Maximum number of entries retained in the short-term memory buffer.
_SHORT_TERM_MAXLEN: int = 256


class BaseAgent:
    """Continuous event-driven agent coroutine with lifecycle management.

    Lifecycle
    ---------
    CREATED → (init()) → READY → (start()) → RUNNING
                                                 │
                         PAUSED ◄──pause()────────┤◄──resume()──┐
                                                 │               │
                         ERROR  ◄──exception─────┤               │
                                                 │               │
                         STOPPED ◄──stop()────────┘               │
                                                                   │
                         PAUSED ─────────────────────────────────►┘
    """

    def __init__(
        self,
        persona: AgentPersona,
        event_bus: asyncio.Queue[Any],
    ) -> None:
        self._persona = persona
        self._event_bus = event_bus

        self._state: AgentState = AgentState.CREATED
        self._task: asyncio.Task[None] | None = None

        # asyncio.Event used to pause/resume the main loop.
        self._resume_event: asyncio.Event = asyncio.Event()
        self._resume_event.set()  # Starts in "not paused" (set) state.

        # asyncio.Event signalling the loop should exit.
        self._stop_event: asyncio.Event = asyncio.Event()

        # Working memory: cleared on each loop tick.
        self.working_memory: dict[str, Any] = {}

        # Short-term memory: circular buffer persisted across ticks.
        self.short_term_memory: collections.deque[Any] = collections.deque(
            maxlen=_SHORT_TERM_MAXLEN
        )

        self._transition(AgentState.READY)
        log.info("agent.initialised", agent=self._persona.name)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the agent's unique identifier."""
        return self._persona.name

    @property
    def persona(self) -> AgentPersona:
        """Return the agent's persona (read-only)."""
        return self._persona

    @property
    def state(self) -> AgentState:
        """Return the current lifecycle state."""
        return self._state

    # ------------------------------------------------------------------
    # Lifecycle control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Schedule the agent's main loop as an asyncio Task.

        Must be called from within a running event loop.
        Raises RuntimeError if the agent is not in READY state.
        """
        if self._state != AgentState.READY:
            raise RuntimeError(
                f"Cannot start agent '{self.name}': expected READY, got {self._state.value}."
            )
        self._task = asyncio.get_running_loop().create_task(self._run(), name=f"agent:{self.name}")
        log.info("agent.started", agent=self.name)

    async def pause(self) -> None:
        """Suspend the main loop after its current tick completes."""
        if self._state != AgentState.RUNNING:
            log.warning("agent.pause_ignored", agent=self.name, state=self._state.value)
            return
        self._resume_event.clear()
        self._transition(AgentState.PAUSED)
        log.info("agent.paused", agent=self.name)

    async def resume(self) -> None:
        """Resume a paused agent."""
        if self._state != AgentState.PAUSED:
            log.warning("agent.resume_ignored", agent=self.name, state=self._state.value)
            return
        self._transition(AgentState.RUNNING)
        self._resume_event.set()
        log.info("agent.resumed", agent=self.name)

    async def stop(self) -> None:
        """Request a clean shutdown and await task completion."""
        if self._state in (AgentState.STOPPED, AgentState.ERROR):
            return
        self._stop_event.set()
        # Unblock a potentially paused loop so it can observe the stop event.
        self._resume_event.set()
        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._transition(AgentState.STOPPED)
        log.info("agent.stopped", agent=self.name)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Continuous event-driven agent loop (runs as an asyncio Task)."""
        self._transition(AgentState.RUNNING)
        try:
            while not self._stop_event.is_set():
                # 1. Honour pause: wait until resumed (or stop is requested).
                await self._resume_event.wait()
                if self._stop_event.is_set():
                    break

                # 2. Await the next trigger from the event bus (non-blocking
                #    peek; fall through immediately if nothing is queued).
                event = await self._next_event()
                if event is None:
                    # No event available — yield control and retry.
                    await asyncio.sleep(0)
                    continue

                # 3. Clear working memory for this tick.
                self.working_memory.clear()

                # 4. Query RAG (stub — concrete subclasses override).
                rag_results = await self._query_rag(event)

                # 5. Call LLM (stub — concrete subclasses override).
                llm_response = await self._call_llm(event, rag_results)

                # 6. Dispatch tool calls (stub — concrete subclasses override).
                tool_results = await self._dispatch_tools(llm_response)

                # 7. Emit output events onto the bus.
                await self._emit_events(llm_response, tool_results)

                # 8. Update short-term memory.
                self._update_memory(event, llm_response, tool_results)

        except asyncio.CancelledError:
            log.info("agent.cancelled", agent=self.name)
            raise
        except Exception as exc:
            self._transition(AgentState.ERROR)
            log.exception("agent.error", agent=self.name, error=str(exc))
            raise

        self._transition(AgentState.STOPPED)

    # ------------------------------------------------------------------
    # Overridable stubs
    # ------------------------------------------------------------------

    async def _next_event(self) -> Any | None:
        """Return the next event from the bus without blocking, or None."""
        try:
            return self._event_bus.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _query_rag(self, event: Any) -> list[Any]:
        """Query relevant RAG collections. Override in subclasses."""
        return []

    async def _call_llm(self, event: Any, rag_results: list[Any]) -> Any:
        """Call the LLM with assembled context. Override in subclasses."""
        return None

    async def _dispatch_tools(self, llm_response: Any) -> list[Any]:
        """Dispatch tool calls from the LLM response. Override in subclasses."""
        return []

    async def _emit_events(self, llm_response: Any, tool_results: list[Any]) -> None:
        """Publish output events onto the event bus. Override in subclasses."""

    def _update_memory(self, event: Any, llm_response: Any, tool_results: list[Any]) -> None:
        """Append tick summary to short-term memory."""
        self.short_term_memory.append(
            {
                "event": event,
                "llm_response": llm_response,
                "tool_results": tool_results,
            }
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, new_state: AgentState) -> None:
        old = self._state
        self._state = new_state
        log.debug(
            "agent.state_transition",
            agent=self._persona.name if hasattr(self, "_persona") else "?",
            old=old.value,
            new=new_state.value,
        )
