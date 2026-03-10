"""Dashboard routes for the HTMX monitoring UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _get_agents_data() -> list[dict[str, str]]:
    """Return agent data from the live engine, or demo data as fallback."""
    from entsim.web.app import get_engine

    engine = get_engine()
    if engine is not None:
        return [
            {
                "name": agent.name,
                "role": agent.persona.role,
                "department": agent.persona.department,
                "state": agent.state.value,
            }
            for agent in engine._agents
        ]
    return [
        {
            "name": "ceo",
            "role": "Chief Executive Officer",
            "department": "Executive",
            "state": "READY",
        },
        {
            "name": "cto",
            "role": "Chief Technology Officer",
            "department": "Engineering",
            "state": "READY",
        },
        {
            "name": "cmo",
            "role": "Chief Marketing Officer",
            "department": "Marketing",
            "state": "READY",
        },
    ]


def _get_simulation_status() -> str:
    """Return current simulation status string."""
    from entsim.web.app import get_engine

    engine = get_engine()
    if engine is not None:
        return "running" if engine.is_running else "stopped"
    return "stopped"


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the main monitoring dashboard."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"agents": _get_agents_data(), "simulation_status": _get_simulation_status()},
    )


@router.get("/agents", response_class=HTMLResponse)
async def agents(request: Request) -> HTMLResponse:
    """Return agent status cards as an HTML fragment (HTMX polling fallback)."""
    cards_html = ""
    for agent in _get_agents_data():
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
    """Start the simulation."""
    from entsim.web.app import get_engine

    engine = get_engine()
    if engine is not None and not engine.is_running:
        await engine.start()
    return {"status": "ok"}


@router.post("/simulation/pause")
async def simulation_pause() -> dict[str, str]:
    """Pause the simulation."""
    from entsim.web.app import get_engine

    engine = get_engine()
    if engine is not None:
        await engine.pause()
    return {"status": "ok"}


@router.post("/simulation/stop")
async def simulation_stop() -> dict[str, str]:
    """Stop the simulation."""
    from entsim.web.app import get_engine

    engine = get_engine()
    if engine is not None:
        await engine.stop()
    return {"status": "ok"}
