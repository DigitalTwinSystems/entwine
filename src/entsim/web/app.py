"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="entsim", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for Docker and load-balancer health checks."""
    return {"status": "ok"}
