# Quickstart

Get entwine running from scratch in under 10 minutes.

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.12+ | `python3 --version` |
| uv | latest | `uv --version` |
| Docker + Compose | latest | `docker compose version` |

## 1. Clone and install

```bash
git clone https://github.com/digitaltwinsystems/entwine.git
cd entwine
uv sync
```

Install optional platform SDKs if needed:

```bash
uv sync --extra platforms   # all platform adapters
uv sync --extra slack       # Slack only
```

## 2. Configure environment

```bash
cp .env.production.example .env
```

Edit `.env` — at minimum set:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Platform credentials (Slack, GitHub, Gmail, X) are optional. Without them, entwine uses stub adapters that return simulated responses.

## 3. Start services

```bash
docker compose up -d qdrant    # vector store
uv run entwine start --config examples/entwine.yaml
```

Or run everything via Docker Compose:

```bash
docker compose up -d
```

## 4. Observe

- **Dashboard**: http://localhost:8000
- **Status API**: http://localhost:8000/status
- **Live events**: http://localhost:8000/events (SSE stream)

The example config (`examples/entwine.yaml`) runs 4 agents — CEO, engineer, marketing head, and support engineer — at Acme Corp with 30-second ticks and a $50 budget cap.

## 5. Control the simulation

```bash
# Pause
curl -X POST http://localhost:8000/simulation/pause

# Resume
curl -X POST http://localhost:8000/simulation/start

# Stop
curl -X POST http://localhost:8000/simulation/stop
```

## 6. Validate a config without running

```bash
uv run entwine validate --config examples/entwine.yaml
```

## Next steps

- [Configuration reference](configuration.md) — all config fields and env vars
- [Platform setup guides](platforms/) — connect real Slack, GitHub, Gmail, X
- [Operator runbook](runbook.md) — monitoring, troubleshooting, upgrades
