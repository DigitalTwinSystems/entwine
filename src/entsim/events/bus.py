"""Asyncio-based event bus with pub/sub support."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import structlog

from entsim.events.models import Event

log = structlog.get_logger(__name__)

# A handler can be a plain callable or a coroutine function.
EventHandler = Callable[[Event], Any]


class EventBus:
    """Central pub/sub event bus backed by an asyncio.Queue.

    Usage::

        bus = EventBus()
        await bus.start()

        bus.subscribe("task_assigned", my_handler)
        bus.subscribe_all(monitor_handler)

        await bus.publish(TaskAssigned(source_agent="ceo", payload={"task": "write report"}))

        await bus.stop()
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        # event_type -> list of handlers
        self._subscribers: defaultdict[str, list[EventHandler]] = defaultdict(list)
        # handlers that receive every event
        self._all_subscribers: list[EventHandler] = []
        self._task: asyncio.Task[None] | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, callback: EventHandler) -> None:
        """Register *callback* to receive events of *event_type*."""
        self._subscribers[event_type].append(callback)
        log.debug("event_bus.subscribed", event_type=event_type, callback=repr(callback))

    def subscribe_all(self, callback: EventHandler) -> None:
        """Register *callback* to receive every event (for monitoring/logging)."""
        self._all_subscribers.append(callback)
        log.debug("event_bus.subscribed_all", callback=repr(callback))

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: Event) -> None:
        """Put *event* on the internal queue for dispatching.

        The call returns immediately; delivery happens in the background
        dispatch loop started by :meth:`start`.
        """
        await self._queue.put(event)
        log.debug(
            "event_bus.published",
            event_id=event.id,
            event_type=event.event_type,
            source_agent=event.source_agent,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background dispatch loop."""
        if self._running:
            log.warning("event_bus.already_running")
            return
        self._running = True
        self._task = asyncio.get_running_loop().create_task(
            self._dispatch_loop(), name="event_bus_dispatch"
        )
        log.info("event_bus.started")

    async def stop(self) -> None:
        """Drain remaining events and shut down the dispatch loop."""
        if not self._running:
            return
        # Let the dispatch loop process pending items before stopping.
        await self._queue.join()
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        log.info("event_bus.stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _dispatch_loop(self) -> None:
        """Continuously read events from the queue and fan out to handlers."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            try:
                await self._dispatch(event)
            finally:
                self._queue.task_done()

    async def _dispatch(self, event: Event) -> None:
        """Fan out a single event to type-specific and wildcard subscribers."""
        handlers: list[EventHandler] = (
            self._subscribers.get(event.event_type, []) + self._all_subscribers
        )
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.exception(
                    "event_bus.handler_error",
                    event_id=event.id,
                    event_type=event.event_type,
                    handler=repr(handler),
                )
