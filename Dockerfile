# ── Stage 1: builder ──
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv from official image (faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first to maximize cache hits
COPY pyproject.toml uv.lock ./

# Install runtime dependencies only (no dev extras)
RUN uv sync --no-dev --frozen

# ── Stage 2: runtime ──
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/DigitalTwinSystems/entwine"
LABEL org.opencontainers.image.description="LLM-powered enterprise digital twin simulation"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy only the virtual environment and application source
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY pyproject.toml ./

# Non-root user
RUN useradd -m entwine && chown -R entwine /app
USER entwine

# Put venv on PATH so python resolves correctly
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "entwine.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
