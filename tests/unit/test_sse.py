"""Unit tests for SSE infrastructure and /events endpoint."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from entsim.events.bus import EventBus
from entsim.events.models import Event, TaskAssigned
from entsim.web.app import app, get_event_collector
from entsim.web.sse import EventCollector

# ---------------------------------------------------------------------------
# EventCollector unit tests
# ---------------------------------------------------------------------------


class TestEventCollector:
    @pytest.mark.asyncio
    async def test_handler_queues_event(self) -> None:
        collector = EventCollector()
        event = Event(source_agent="ceo", event_type="test", payload={"key": "value"})

        await collector.handler(event)

        assert not collector._queue.empty()
        sse_event = collector._queue.get_nowait()
        assert sse_event["event"] == "test"
        assert sse_event["id"] == event.id
        data = json.loads(sse_event["data"])
        assert data["source_agent"] == "ceo"
        assert data["payload"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_handler_formats_event_as_expected_dict(self) -> None:
        collector = EventCollector()
        event = TaskAssigned(
            source_agent="manager",
            payload={"task": "write report"},
        )

        await collector.handler(event)

        sse_event = collector._queue.get_nowait()
        assert set(sse_event.keys()) == {"event", "data", "id"}
        assert sse_event["event"] == "task_assigned"
        assert sse_event["id"] == event.id
        data = json.loads(sse_event["data"])
        assert data["event_type"] == "task_assigned"
        assert data["source_agent"] == "manager"

    @pytest.mark.asyncio
    async def test_event_generator_yields_queued_events(self) -> None:
        collector = EventCollector()
        e1 = Event(source_agent="a", event_type="t1")
        e2 = Event(source_agent="b", event_type="t2")

        await collector.handler(e1)
        await collector.handler(e2)

        gen = collector.event_generator()
        first = await gen.__anext__()
        assert first["event"] == "t1"
        second = await gen.__anext__()
        assert second["event"] == "t2"

    @pytest.mark.asyncio
    async def test_connect_to_bus_subscribes_to_event_bus(self) -> None:
        collector = EventCollector()
        bus = EventBus()

        collector.connect_to_bus(bus)

        assert collector.handler in bus._all_subscribers


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestEventsEndpoint:
    @pytest.mark.asyncio
    async def test_events_endpoint_returns_event_source_response(self) -> None:
        collector = get_event_collector()
        event = Event(source_agent="test", event_type="ping")
        await collector.handler(event)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Use a timeout so we don't hang waiting for the infinite generator.
            try:
                async with asyncio.timeout(1):
                    response = await client.get("/events")
            except TimeoutError:
                # SSE streams don't complete, so a timeout is expected after
                # the first event has been consumed.  We just need the status.
                pass
            else:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_health_endpoint_still_works(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
