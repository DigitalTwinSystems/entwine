"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from entwine.web.routes import router as dashboard_router
from entwine.web.sse import EventCollector

_event_collector = EventCollector()

# Global engine reference — set by the CLI before uvicorn starts.
_engine: Any = None


def set_engine(engine: Any) -> None:
    """Store the SimulationEngine instance for the web layer to use."""
    global _engine
    _engine = engine
    # Wire SSE collector to the engine's event bus.
    _event_collector.connect_to_bus(engine._event_bus)


def get_engine() -> Any:
    """Return the active SimulationEngine, or None."""
    return _engine


def get_event_collector() -> EventCollector:
    """Return the module-level EventCollector instance."""
    return _event_collector


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start and stop the simulation engine with the FastAPI server."""
    if _engine is not None:
        await _engine.start()
    yield
    if _engine is not None:
        await _engine.stop()


app = FastAPI(title="entwine", version="0.1.0", lifespan=lifespan)

app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for Docker and load-balancer health checks."""
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, Any]:
    """Return simulation status snapshot."""
    if _engine is not None:
        return _engine.get_status()
    return {"status": "no simulation loaded"}


@app.get("/events")
async def events() -> EventSourceResponse:
    """SSE endpoint for real-time agent events."""
    return EventSourceResponse(get_event_collector().event_generator())
