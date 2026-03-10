"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from entsim.web.routes import router as dashboard_router
from entsim.web.sse import EventCollector

app = FastAPI(title="entsim", version="0.1.0")

app.include_router(dashboard_router)

_event_collector = EventCollector()


def get_event_collector() -> EventCollector:
    """Return the module-level EventCollector instance (for dependency injection)."""
    return _event_collector


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for Docker and load-balancer health checks."""
    return {"status": "ok"}


@app.get("/events")
async def events() -> EventSourceResponse:
    """SSE endpoint for real-time agent events."""
    return EventSourceResponse(get_event_collector().event_generator())
