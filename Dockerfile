# ── Stage 1: builder ──
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency manifests first to maximize cache hits
COPY pyproject.toml uv.lock ./

# Install runtime dependencies only (no dev extras)
RUN uv sync --no-dev --frozen

# ── Stage 2: runtime ──
FROM python:3.12-slim

WORKDIR /app

# Copy only the virtual environment and application source
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY pyproject.toml ./

# Non-root user
RUN useradd -m entsim && chown -R entsim /app
USER entsim

# Put venv on PATH so uv and python resolve correctly
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "entsim.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
