"""Unit tests for the HTMX monitoring dashboard."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from entsim.web.app import app


class TestDashboardRoutes:
    @pytest.mark.asyncio
    async def test_get_dashboard_returns_html(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "entsim" in response.text

    @pytest.mark.asyncio
    async def test_get_agents_returns_html_fragment(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/agents")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "agent-card" in response.text

    @pytest.mark.asyncio
    async def test_post_simulation_start(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/simulation/start")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_post_simulation_pause(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/simulation/pause")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_post_simulation_stop(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/simulation/stop")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
