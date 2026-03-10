"""Dashboard routes for the HTMX monitoring UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

# Placeholder agent data used until the simulation runtime is wired in.
_DEMO_AGENTS = [
    {"name": "ceo", "role": "Chief Executive Officer", "department": "Executive", "state": "READY"},
    {
        "name": "cto",
        "role": "Chief Technology Officer",
        "department": "Engineering",
        "state": "READY",
    },
    {"name": "cmo", "role": "Chief Marketing Officer", "department": "Marketing", "state": "READY"},
]


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main monitoring dashboard."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"agents": _DEMO_AGENTS, "simulation_status": "stopped"},
    )


@router.get("/agents", response_class=HTMLResponse)
async def agents(request: Request) -> HTMLResponse:
    """Return agent status cards as an HTML fragment (HTMX polling fallback)."""
    cards_html = ""
    for agent in _DEMO_AGENTS:
        cards_html += (
            f'<div class="agent-card">'
            f'<div class="agent-name">{agent["name"]}</div>'
            f'<div class="agent-role">{agent["role"]}</div>'
            f'<div class="agent-dept">{agent["department"]}</div>'
            f'<div class="agent-state state-{agent["state"]}">'
            f'<span class="state-dot"></span> {agent["state"]}'
            f"</div>"
            f'<div class="agent-timestamp">&mdash;</div>'
            f"</div>"
        )
    return HTMLResponse(content=cards_html)


@router.post("/simulation/start")
async def simulation_start() -> dict[str, str]:
    """Start the simulation (placeholder)."""
    return {"status": "ok"}


@router.post("/simulation/pause")
async def simulation_pause() -> dict[str, str]:
    """Pause the simulation (placeholder)."""
    return {"status": "ok"}


@router.post("/simulation/stop")
async def simulation_stop() -> dict[str, str]:
    """Stop the simulation (placeholder)."""
    return {"status": "ok"}
