"""SSE infrastructure for streaming real-time agent events."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog

from entwine.events.bus import EventBus
from entwine.events.models import Event

log = structlog.get_logger(__name__)


class EventCollector:
    """Collects events from an EventBus and streams them as SSE events.

    Usage::

        collector = EventCollector()
        collector.connect_to_bus(bus)

        # In a FastAPI endpoint:
        return EventSourceResponse(collector.event_generator())
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def handler(self, event: Event) -> None:
        """Receive an event from the EventBus and enqueue it for SSE streaming."""
        sse_event = {
            "event": event.event_type,
            "data": json.dumps(event.model_dump(mode="json")),
            "id": event.id,
        }
        await self._queue.put(sse_event)
        log.debug("sse.event_queued", event_id=event.id, event_type=event.event_type)

    async def event_generator(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield SSE-formatted events from the internal queue."""
        while True:
            sse_event = await self._queue.get()
            yield sse_event

    def connect_to_bus(self, bus: EventBus) -> None:
        """Subscribe to all events on the given EventBus."""
        bus.subscribe_all(self.handler)
        log.info("sse.connected_to_bus")
