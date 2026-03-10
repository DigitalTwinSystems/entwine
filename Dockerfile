FROM python:3.12-slim

WORKDIR /app

# Install uv — layer cached until this step changes
RUN pip install uv

# Copy dependency manifests first to maximize cache hits
COPY pyproject.toml uv.lock ./

# Install runtime dependencies only (no dev extras)
RUN uv sync --no-dev --frozen

# Copy application source
COPY src/ ./src/

# Non-root user
RUN useradd -m entsim && chown -R entsim /app
USER entsim

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "entsim.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
