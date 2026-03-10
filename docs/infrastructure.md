# entwine Infrastructure Specification

**Last updated:** 2026-03-10
**Authoritative ADR:** [ADR-007](adr/007-deployment-and-infrastructure.md)

---

## 1. Development Environment

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker Desktop | 4.x+ | https://docs.docker.com/desktop/ |
| Docker Compose | v2 (bundled with Desktop) | — |
| Python | 3.12+ | via `pyenv` or system |
| uv | latest | `pip install uv` |
| git | 2.x+ | system |

### First-time setup

```bash
git clone https://github.com/DigitalTwinSystems/entwine.git
cd entwine
cp .env.example .env          # fill in API keys (see §5)
uv run pre-commit install
docker compose up             # starts entwine + qdrant + ollama
```

The app is available at `http://localhost:8000`. Qdrant UI at `http://localhost:6333/dashboard`.

### Dev workflow commands

| Command | Purpose |
|---------|---------|
| `docker compose up` | Start all services (auto-applies `compose.override.yaml`) |
| `docker compose up --build entwine` | Rebuild the app container |
| `uv run pytest` | Run unit tests |
| `uv run ruff check src/` | Lint |
| `uv run mypy src/` | Type-check |

---

## 2. Docker Compose Specification

Three-file layered strategy ([merge semantics](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/)):

| File | Purpose | Used by |
|------|---------|---------|
| `compose.yaml` | Base: services, networks, volumes | Both |
| `compose.override.yaml` | Dev: bind mounts, debug ports, Ollama | `docker compose up` (auto) |
| `compose.prod.yaml` | Prod: image tags, resource limits, no bind mounts | `docker compose -f compose.yaml -f compose.prod.yaml up -d` |

### `compose.yaml` (base)

```yaml
services:
  entwine:
    build: .
    image: ghcr.io/digitaltwinsystems/entwine:latest
    restart: unless-stopped
    env_file: .env
    environment:
      - QDRANT_URL=http://qdrant:6333
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    ports:
      - "8000:8000"
    depends_on:
      qdrant:
        condition: service_healthy
    networks:
      - entwine-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    volumes:
      - qdrant-data:/qdrant/storage
    ports:
      - "6333:6333"
    networks:
      - entwine-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/readyz"]
      interval: 10s
      timeout: 3s
      retries: 5

networks:
  entwine-net:
    driver: bridge

volumes:
  qdrant-data:
```

### `compose.override.yaml` (dev, auto-applied)

```yaml
services:
  entwine:
    build:
      context: .
      target: dev
    volumes:
      - ./src:/app/src          # live code reload
    environment:
      - LOG_LEVEL=DEBUG
      - OTEL_TRACES_EXPORTER=console

  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "11434:11434"
    networks:
      - entwine-net

  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"   # Jaeger UI
      - "4317:4317"     # OTLP gRPC
    networks:
      - entwine-net

volumes:
  ollama-data:
```

### `compose.prod.yaml` (production overlay)

```yaml
services:
  entwine:
    image: ghcr.io/digitaltwinsystems/entwine:${IMAGE_TAG:-latest}
    build: !reset null            # never build in prod
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: 4G
    environment:
      - LOG_LEVEL=INFO
      - OTEL_TRACES_EXPORTER=otlp

  qdrant:
    environment:
      - QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}
    deploy:
      resources:
        limits:
          memory: 2G
```

### Service port summary

| Service | Host port | Container port | Purpose |
|---------|-----------|----------------|---------|
| entwine | 8000 | 8000 | FastAPI + HTMX UI |
| qdrant | 6333 | 6333 | Vector store HTTP / gRPC |
| ollama | 11434 | 11434 | Local LLM (dev only) |
| jaeger | 16686 | 16686 | Trace UI (dev only) |
| jaeger | 4317 | 4317 | OTLP gRPC collector (dev only) |

---

## 3. Container Specification

Single-stage build on `python:3.12-slim` ([best practices](https://docs.docker.com/build/building/best-practices/)). No multi-stage build — no compiled extensions at this stage (ADR-007).

### `Dockerfile`

```dockerfile
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
RUN useradd -m entwine && chown -R entwine /app
USER entwine

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "entwine", "serve"]
```

### Build notes

- In CI, pin base image to a digest (`python:3.12-slim@sha256:...`) for supply-chain integrity.
- Layer order: system deps → `uv` → lockfile copy → `uv sync` → source copy. Source changes only invalidate the last layer.
- `uv sync --frozen` enforces the lockfile; fails if `uv.lock` is out of date.

### Source layout (ADR-008)

```
src/
└── entwine/
    ├── __init__.py
    ├── agents/        # asyncio agent coroutines, supervisor
    ├── config/        # Pydantic Settings, TOML/YAML loaders
    ├── rag/           # Qdrant async client, hybrid search
    └── web/           # FastAPI app, HTMX routes, SSE endpoints
```

---

## 4. Production Deployment

### VM specification

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| vCPU | 2 | 4 |
| RAM | 8 GB | 16 GB |
| Disk | 40 GB SSD | 80 GB SSD |
| OS | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| Cost | ~$50/mo | ~$80–100/mo |

Rationale: 12 asyncio agents in one process have no horizontal scaling requirement. Single VM is sufficient (ADR-007).

### Initial VM setup

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER

# Clone repo and configure
git clone https://github.com/DigitalTwinSystems/entwine.git /opt/entwine
cd /opt/entwine
cp .env.example .env    # fill prod secrets

# Start production stack
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

### Caddy reverse proxy

Caddy provides automatic TLS via Let's Encrypt with zero configuration (ADR-007).

Install on the VM (not in Docker, so it survives container restarts):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

**`/etc/caddy/Caddyfile`:**

```caddyfile
entwine.example.com {
    reverse_proxy localhost:8000

    # Cache static assets
    @static path /static/*
    handle @static {
        header Cache-Control "public, max-age=86400"
        reverse_proxy localhost:8000
    }

    # SSE — disable buffering
    @sse path /events/*
    handle @sse {
        reverse_proxy localhost:8000 {
            flush_interval -1
        }
    }

    log {
        output file /var/log/caddy/access.log
        format json
    }
}
```

```bash
sudo systemctl enable --now caddy
```

### Production deployment command (used by `deploy.yml`)

```bash
cd /opt/entwine
git pull origin main
IMAGE_TAG=${GITHUB_SHA::8} docker compose -f compose.yaml -f compose.prod.yaml pull
IMAGE_TAG=${GITHUB_SHA::8} docker compose -f compose.yaml -f compose.prod.yaml up -d
```

`restart: unless-stopped` ensures containers recover from VM reboots. Health checks prevent traffic routing to an unhealthy container.

---

## 5. Secrets Management

### `.env` structure

`.env` is git-ignored. Copy `.env.example` and fill in values.

```dotenv
# ── LLM providers (required in prod; optional in dev — Ollama used instead) ──
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# ── Platform OAuth tokens ──
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...

GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...

OFFICE365_TENANT_ID=...
OFFICE365_CLIENT_ID=...
OFFICE365_CLIENT_SECRET=...

REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_REFRESH_TOKEN=...

SLACK_BOT_TOKEN=xoxb-...

GITHUB_APP_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github_app.pem

# ── Qdrant (no auth in dev; required in prod) ──
QDRANT_API_KEY=

# ── E2B (required only when coder agents are enabled — ADR-010) ──
E2B_API_KEY=

# ── Observability ──
OTEL_SERVICE_NAME=entwine
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# ── App settings ──
LOG_LEVEL=INFO
```

### Pydantic Settings loading order

Settings are loaded via [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) (ADR-004). Priority (highest wins):

1. Environment variables (from shell or `--env-file`)
2. `.env` file (loaded by `env_file:` in Compose)
3. TOML/YAML config files (`config/settings.toml`)
4. Pydantic field defaults

```python
# src/entwine/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str
    openai_api_key: str | None = None
    qdrant_url: str = "http://localhost:6333"
    log_level: str = "INFO"
    # ... (all vars above)
```

Missing required vars raise a `ValidationError` at startup with a clear error message — fail fast.

### Per-environment secret storage

| Environment | Mechanism |
|-------------|-----------|
| Local dev | `.env` file, distributed manually to each developer |
| GitHub Actions CI | [GitHub Actions secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) (set manually in repo settings) |
| Production VM | `.env` file on VM, copied via `scp` or SSH on initial setup |

Do not use Doppler or HashiCorp Vault until team or secret count grows significantly (ADR-007).

---

## 6. Observability Stack

### Signals

| Signal | Tool | Config |
|--------|------|--------|
| Structured logs | `structlog` or `python-json-logger` → stdout → Docker log driver | `LOG_LEVEL` env var |
| Traces | OpenTelemetry → Jaeger (dev) / OTLP endpoint (prod) | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Metrics | `prometheus-fastapi-instrumentator` → Prometheus scrape | `/metrics` endpoint |
| LLM cost | `litellm.completion_cost()` logged per request | Application layer |

### Structured logging

```python
import structlog

log = structlog.get_logger()

# In agent hooks (ADR-005):
log.info("agent.llm_call", agent_id=agent.id, model=tier, tokens=usage.total_tokens,
         cost_usd=cost, duration_ms=elapsed)
```

JSON output goes to stdout; Docker captures it via the default `json-file` log driver. Tail with `docker compose logs -f entwine`.

### OpenTelemetry setup

```bash
uv add opentelemetry-distro opentelemetry-exporter-otlp
opentelemetry-bootstrap -a install   # auto-installs instrumentation packages
```

```python
# src/entwine/web/app.py — instrument at startup
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
```

Set `OTEL_TRACES_EXPORTER=console` in dev to print traces to stdout without needing Jaeger.

### Prometheus metrics

```python
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app)
# Exposes GET /metrics (Prometheus text format)
```

Scrape config for a self-hosted Prometheus instance:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: entwine
    static_configs:
      - targets: ["entwine:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```

### Health check endpoints

| Endpoint | Method | Returns | Purpose |
|----------|--------|---------|---------|
| `/health` | GET | `{"status": "ok"}` | Docker / load-balancer liveness |
| `/health/ready` | GET | `{"status": "ok", "qdrant": "ok"}` | Readiness (checks Qdrant) |
| `/metrics` | GET | Prometheus text | Metrics scrape |

Minimum viable observability for a single VM: structured logs only. Add Prometheus + Grafana when there is a concrete question logs cannot answer (ADR-007).

---

## 7. CI/CD Pipelines

Three GitHub Actions workflows. All run on `ubuntu-latest`. No self-hosted runners.

### `ci.yml` — lint, type-check, test (push / PR to any branch)

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          version: "latest"
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync --frozen

      - name: Lint
        run: uv run ruff check src/ tests/

      - name: Format check
        run: uv run ruff format --check src/ tests/

      - name: Type-check
        run: uv run mypy src/

      - name: Unit tests
        run: uv run pytest -m "not integration" --cov=src/entwine --cov-fail-under=80
```

### `build.yml` — build and push Docker image (push to `main`)

```yaml
name: Build

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ghcr.io/digitaltwinsystems/entwine:latest
            ghcr.io/digitaltwinsystems/entwine:${{ github.sha }}
          cache-from: type=registry,ref=ghcr.io/digitaltwinsystems/entwine:latest
          cache-to: type=inline
```

### `deploy.yml` — deploy to VM (manual dispatch or tag `v*`)

```yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Image tag to deploy (default: latest)"
        default: "latest"
  push:
    tags: ["v*"]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: ${{ secrets.PROD_USER }}
          key: ${{ secrets.PROD_SSH_KEY }}
          script: |
            cd /opt/entwine
            git pull origin main
            IMAGE_TAG=${{ inputs.image_tag || github.sha }} \
              docker compose -f compose.yaml -f compose.prod.yaml pull
            IMAGE_TAG=${{ inputs.image_tag || github.sha }} \
              docker compose -f compose.yaml -f compose.prod.yaml up -d
            docker system prune -f
```

### Required GitHub Actions secrets

| Secret | Used by |
|--------|---------|
| `GITHUB_TOKEN` | Auto-provided; GHCR push in `build.yml` |
| `PROD_HOST` | Production VM IP or hostname |
| `PROD_USER` | SSH username on VM |
| `PROD_SSH_KEY` | SSH private key (Ed25519 recommended) |
| `ANTHROPIC_API_KEY` | Integration tests (optional) |
| `OPENAI_API_KEY` | Integration tests (optional) |

---

## 8. Network Architecture

### Service discovery

All services communicate over the `entwine-net` Docker bridge network using service names as hostnames:

```
entwine  →  qdrant:6333     (vector store)
entwine  →  ollama:11434    (local LLM, dev only)
entwine  →  jaeger:4317     (OTLP traces, dev only)
```

In production, `ollama` and `jaeger` are absent. Traces go to an external OTLP endpoint via `OTEL_EXPORTER_OTLP_ENDPOINT`.

### External API connectivity

The `entwine` container needs outbound HTTPS (port 443) to:

| Endpoint | Purpose | ADR |
|----------|---------|-----|
| `api.anthropic.com` | Claude LLM calls | ADR-002 |
| `api.openai.com` | OpenAI fallback + embeddings | ADR-002, ADR-003 |
| `api.twitter.com` | X (Twitter) platform | ADR-006 |
| `gmail.googleapis.com` | Gmail integration | ADR-006 |
| `graph.microsoft.com` | Office 365 / Graph API | ADR-006 |
| `oauth.reddit.com`, `oauth.redditapis.com` | Reddit | ADR-006 |
| `slack.com` | Slack internal app | ADR-006 |
| `api.github.com` | GitHub App | ADR-006 |
| `e2b.dev` | Coder agent sandboxes (when enabled) | ADR-010 |

No inbound ports beyond 8000 (proxied by Caddy on 443) are required.

### Full port map

| Port | Protocol | Direction | Service | Environment |
|------|----------|-----------|---------|-------------|
| 443 | HTTPS | Inbound | Caddy → entwine:8000 | Prod |
| 8000 | HTTP | Inbound | entwine FastAPI | Dev (direct) |
| 6333 | HTTP/gRPC | Internal | Qdrant | Both |
| 11434 | HTTP | Internal | Ollama | Dev only |
| 16686 | HTTP | Inbound | Jaeger UI | Dev only |
| 4317 | gRPC | Internal | Jaeger OTLP | Dev only |
