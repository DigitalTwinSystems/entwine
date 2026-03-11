# Operator Runbook

## Starting a simulation

### Via CLI (development)

```bash
uv run entwine start --config examples/entwine.yaml --host 0.0.0.0 --port 8000
```

### Via Docker Compose (production)

```bash
docker compose up -d
```

The simulation starts automatically on server boot via the FastAPI lifespan handler.

## Controlling the simulation

| Action | Command |
|--------|---------|
| Start/Resume | `curl -X POST http://localhost:8000/simulation/start` |
| Pause | `curl -X POST http://localhost:8000/simulation/pause` |
| Stop | `curl -X POST http://localhost:8000/simulation/stop` |

Pause suspends all agents and the simulation clock. Resume picks up where it left off. Stop is a clean shutdown.

## Monitoring

### Dashboard

Open http://localhost:8000 in a browser. Shows agent cards with real-time state updates via SSE.

### Status endpoint

```bash
curl -s http://localhost:8000/status | python3 -m json.tool
```

Returns:
- `simulation_name`, `is_running`, `elapsed_ticks`, `agent_count`
- Per-agent state and role
- Clock info (simulated time, running status)
- Platform list
- Cost breakdown (global total, per-agent costs/calls/tokens)

### Live event stream

```bash
curl -N http://localhost:8000/events
```

SSE stream of all agent events (task assignments, messages, platform actions, state changes).

## Cost monitoring

Budget enforcement is automatic:
- **Per-agent budget**: agent receives `BudgetExceeded`, logs warning, stops making LLM calls
- **Global budget**: simulation auto-pauses when total spend reaches limit

Check current spend:

```bash
curl -s http://localhost:8000/status | python3 -c "
import sys, json
data = json.load(sys.stdin)
costs = data.get('costs', {})
print(f'Total: \${costs.get(\"global_cost_usd\", 0):.4f} / \${costs.get(\"global_budget_usd\", \"unlimited\")}')
for name, info in costs.get('agents', {}).items():
    print(f'  {name}: \${info[\"cost_usd\"]:.4f} ({info[\"calls\"]} calls)')
"
```

## Logs

### Docker Compose

```bash
docker compose logs -f entwine         # application logs
docker compose logs -f qdrant          # vector store logs
```

### Local development

Logs go to stderr in structured format (via `structlog`). Set level via config or env:

```bash
ENTWINE_LOG_LEVEL=DEBUG uv run entwine start --config examples/entwine.yaml
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Agent stuck in `ERROR` state | Unhandled exception in agent loop | Check logs; supervisor recovery strategy applies (default: `skip`) |
| `BudgetExceeded` in logs | Agent or global spend hit limit | Increase `*_budget_usd` in config, or let simulation remain paused |
| Platform auth failure | Invalid/expired credentials | Regenerate token; see [platform guides](platforms/) |
| Qdrant connection refused | Qdrant not running | `docker compose up -d qdrant` |
| `No module named 'slack_sdk'` | Optional dep not installed | `uv sync --extra slack` (or `--extra platforms` for all) |
| Simulation won't start | Config validation error | Run `uv run entwine validate --config <path>` |
| High memory usage | Agent short-term memory accumulation | Memory is bounded (maxlen=256 per agent); restart if needed |

## Backup and restore

### Qdrant data

Qdrant stores vectors in the `qdrant-data` Docker volume.

```bash
# Backup
docker compose stop qdrant
docker run --rm -v entwine_qdrant-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/qdrant-backup.tar.gz -C /data .
docker compose start qdrant

# Restore
docker compose stop qdrant
docker run --rm -v entwine_qdrant-data:/data -v $(pwd):/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/qdrant-backup.tar.gz -C /data"
docker compose start qdrant
```

## Upgrading

```bash
docker compose pull         # pull latest images
docker compose up -d        # restart with new images
```

For local development:

```bash
git pull
uv sync
uv run entwine start --config examples/entwine.yaml
```
