# ADR-007: Deployment and Infrastructure Architecture

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#7](https://github.com/DigitalTwinSystems/entwine/issues/7)

## Context

entwine is a Python asyncio multi-agent system (ADR-001) running ~12 concurrent agents backed by Qdrant (ADR-003), LiteLLM (ADR-002), and a FastAPI/HTMX UI (ADR-004). We need to define:

- How the system runs locally during development
- The minimum viable production deployment
- How secrets (LLM API keys, platform credentials) are managed across environments
- What observability stack to use
- CI/CD pipeline strategy

The system is **I/O-bound and single-process**: one FastAPI server, one asyncio event loop, one Qdrant sidecar. There is no distributed compute requirement at this scale.

## Decision

### Local development: Docker Compose

All services run locally via Docker Compose using a layered file strategy:

| File | Purpose |
|------|---------|
| `compose.yaml` | Base: service definitions, networks, named volumes |
| `compose.override.yaml` | Dev overrides: bind mounts, debug ports, Ollama |
| `compose.prod.yaml` | Prod overrides: image tags, resource limits, no bind mounts |

Run dev: `docker compose up` (auto-applies override).
Run prod-like locally: `docker compose -f compose.yaml -f compose.prod.yaml up -d`.

See [Docker Compose merge documentation](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) for layering semantics.

### Services

| Service | Image | Notes |
|---------|-------|-------|
| `entwine` | `python:3.12-slim` (built locally) | FastAPI app + agent runtime |
| `qdrant` | `qdrant/qdrant:latest` | Vector store (ADR-003) |
| `ollama` | `ollama/ollama:latest` | Local LLM for dev only (ADR-002) |

No message broker, no separate worker process. Agents are `asyncio.Task` objects within the single FastAPI process. If durable task queuing becomes necessary, [Temporal](https://temporal.io/) (Go server, Python SDK) is the first candidate — no Go code required on our side (escape hatch documented in ADR-001).

### Production deployment: single VM

Minimum viable production is a single Linux VM (e.g., 4 vCPU / 16 GB RAM) running Docker Compose prod configuration.

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Reverse proxy | [Caddy](https://caddyserver.com/) | Automatic TLS, zero-config HTTPS, one binary |
| Process supervisor | Docker Compose (`restart: unless-stopped`) | Sufficient for single-VM; no orchestrator overhead |
| Container registry | GitHub Container Registry (`ghcr.io`) | Free for public repos, native GitHub Actions integration |

Kubernetes is out of scope until there is a measured scale or multi-tenancy requirement. The system's concurrency model (asyncio tasks, not processes) makes horizontal scaling unnecessary at the ~12-agent target.

### Container build strategy

Single-stage build using `python:3.12-slim`. Multi-stage builds add complexity without benefit here (no compiled extensions, no large build-time dependencies).

Key practices ([Docker best practices](https://docs.docker.com/build/building/best-practices/)):
- Copy `pyproject.toml` / `uv.lock` before source code to maximize layer cache hits
- Install dependencies via `uv sync --no-dev --frozen`
- Run as non-root user (`USER entwine`)
- Pin base image digest in CI for supply-chain integrity

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen
COPY src/ ./src/
RUN useradd -m entwine && chown -R entwine /app
USER entwine
CMD ["uv", "run", "entwine", "serve"]
```

### Secrets management

| Context | Strategy |
|---------|----------|
| Local dev | `.env` file (git-ignored), loaded by Docker Compose `env_file:` |
| CI (GitHub Actions) | GitHub Actions secrets (set manually or synced via [Doppler](https://docs.doppler.com/docs/github-actions)) |
| Production VM | Environment variables injected at container start via `--env-file` or a secrets manager |

Secret categories:
- **LLM API keys**: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` — required in prod, optional in dev (Ollama used instead)
- **Platform credentials**: per-platform OAuth tokens (`X_API_KEY`, `LINKEDIN_CLIENT_SECRET`, etc.)
- **Qdrant**: no auth in dev; enable Qdrant API key (`QDRANT__SERVICE__API_KEY`) in prod

All secrets are consumed via [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) at startup (ADR-004), failing fast with a clear error if required vars are missing.

Do not use Doppler or a full secrets manager until the team grows beyond one or two developers. GitHub Actions secrets + `.env` files cover the current scope.

### Observability

| Signal | Tool | Integration |
|--------|------|-------------|
| Traces | [OpenTelemetry](https://opentelemetry.io/docs/languages/python/getting-started/) → Jaeger (dev) / OTLP endpoint (prod) | `opentelemetry-distro` + `opentelemetry-instrument` |
| Metrics | [Prometheus](https://prometheus.io/docs/introduction/overview/) scrape + Grafana dashboards | `prometheus-fastapi-instrumentator` |
| Logs | Structured JSON logs → stdout → Docker log driver | `structlog` or `python-json-logger` |
| LLM cost | LiteLLM `completion_cost()` logged per request | Application layer |

Minimum viable observability for a single VM: structured logs only. Add Prometheus + Grafana when there is a concrete question the logs can't answer. OpenTelemetry instrumentation should be added early (low effort, high future value) even if the collector backend is `console` initially.

Jaeger all-in-one Docker image is suitable for local trace inspection: `jaegertracing/all-in-one:latest`, port `16686`.

### CI/CD pipeline: GitHub Actions

Three workflows:

| Workflow | Trigger | Steps |
|----------|---------|-------|
| `ci.yml` | Push / PR to any branch | Lint (ruff), type-check (mypy), unit tests (pytest) |
| `build.yml` | Push to `main` | Build Docker image, push to `ghcr.io` with `sha` and `latest` tags |
| `deploy.yml` | Manual dispatch or tag `v*` | SSH to VM, `docker compose pull && docker compose up -d` |

All workflows run on `ubuntu-latest`. Docker layer cache is preserved via `actions/cache` or `--cache-from` with the registry image.

No self-hosted runners at this stage.

## Rationale

### Why single VM over Kubernetes

- 12 asyncio agents in one process have no horizontal scaling requirement
- Kubernetes adds significant operational overhead (ingress controllers, pod scheduling, ConfigMaps, Secrets objects, readiness probes)
- A 4 vCPU / 16 GB VM comfortably runs all services; cost is ~$50–100/month on any major cloud
- Escape hatch: Compose files are the production config; migrating to Kubernetes later means writing Deployments from the Compose definitions — a well-understood path

### Why not serverless (Lambda / Cloud Run)

- asyncio agent tasks are long-running (minutes to hours per simulation run) — serverless has hard timeout limits (15 min for Lambda, 60 min for Cloud Run)
- Cold start latency is incompatible with persistent agent state in memory
- Qdrant requires persistent storage — not naturally serverless

### Why Caddy over nginx

- Automatic TLS via Let's Encrypt with zero configuration
- Single binary, no separate `certbot` cron job
- Sufficient for single-origin reverse proxy use case
- nginx remains viable if more advanced routing is needed

### Why no message broker

At ~12 agents all running in the same asyncio event loop, `asyncio.Queue` provides all inter-agent communication primitives needed. Adding RabbitMQ or Redis Streams at this scale would be over-engineering. Revisit if:
- Agents need to survive process restarts (durability)
- Agent count grows beyond what one process can handle
- Multiple entwine instances need to share work

## Consequences

### Positive

- Entire system runs on a developer laptop with `docker compose up`
- Production deployment is a single VM — minimal operational surface area
- Secrets management is simple and auditable
- OpenTelemetry instrumentation added early preserves future backend flexibility
- GitHub Actions CI/CD is free for public repos and integrates natively with `ghcr.io`

### Negative

- Single VM is a single point of failure — no automatic failover
- No horizontal scaling path without refactoring agents out of the shared process
- Manual deploy workflow means downtime during `docker compose up -d` restart (mitigated by health checks and `restart: unless-stopped`)
- `.env` files require manual distribution to new developers (no central secrets store)

### Future escape hatches

- **Temporal** for durable agent workflows if simulation must survive restarts
- **Kubernetes** if multi-tenancy or horizontal scaling becomes necessary — Compose → Helm chart is the migration path
- **Doppler / HashiCorp Vault** if the team or secret count grows significantly
- **Grafana Cloud** (free tier) instead of self-hosted Prometheus + Grafana to eliminate the observability VM overhead
