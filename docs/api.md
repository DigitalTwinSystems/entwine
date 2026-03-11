# API and Endpoint Reference

Base URL: `http://localhost:8000` (configurable via `--host` and `--port`).

## Endpoints

### GET /health

Liveness probe.

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

No error cases. Always returns 200.

---

### GET /status

Simulation status snapshot with cost breakdown.

```bash
curl http://localhost:8000/status
```

**Response (simulation loaded):**

```json
{
  "simulation_name": "Acme Corp Simulation",
  "is_running": true,
  "elapsed_ticks": 42,
  "agent_count": 4,
  "agents": {
    "Alice Chen": {"state": "RUNNING", "role": "Chief Executive Officer"},
    "Ben Muller": {"state": "RUNNING", "role": "Senior Software Engineer"}
  },
  "clock": {
    "current_time": "2026-03-11T09:42:00+00:00",
    "is_running": true
  },
  "platforms": ["slack", "github", "email", "x", "linkedin"],
  "costs": {
    "global_cost_usd": 1.234567,
    "global_budget_usd": 50.0,
    "per_agent_budget_usd": 15.0,
    "budget_exceeded": false,
    "budget_exceeded_scope": null,
    "agents": {
      "Alice Chen": {
        "cost_usd": 0.5,
        "calls": 12,
        "tokens": {"input": 8000, "output": 2000}
      }
    }
  }
}
```

**Response (no simulation loaded):**

```json
{"status": "no simulation loaded"}
```

---

### GET /events

Server-Sent Events stream of real-time agent events.

```bash
curl -N http://localhost:8000/events
```

Each event is a JSON-encoded SSE message:

```
data: {"id": "uuid", "timestamp": "...", "source_agent": "Alice Chen", "event_type": "message_sent", "payload": {...}}

data: {"id": "uuid", "timestamp": "...", "source_agent": "system", "event_type": "system_event", "payload": {"tick": 43}}
```

Event types: `task_assigned`, `task_completed`, `message_sent`, `platform_action`, `agent_state_changed`, `system_event`.

Connection stays open until client disconnects.

---

### GET /

HTMX monitoring dashboard. Returns full HTML page with agent cards and simulation controls. Auto-updates via SSE.

---

### GET /agents

HTMX fragment returning agent status cards. Used as polling fallback by the dashboard.

```bash
curl http://localhost:8000/agents
```

Returns HTML fragment (not JSON).

---

### POST /simulation/start

Start or resume a paused simulation.

```bash
curl -X POST http://localhost:8000/simulation/start
```

```json
{"status": "ok"}
```

No-op if already running or no engine loaded.

---

### POST /simulation/pause

Pause all agents and the simulation clock.

```bash
curl -X POST http://localhost:8000/simulation/pause
```

```json
{"status": "ok"}
```

Agents finish their current tick before pausing.

---

### POST /simulation/stop

Stop the simulation. Clean shutdown of all agents, event bus, and clock.

```bash
curl -X POST http://localhost:8000/simulation/stop
```

```json
{"status": "ok"}
```

After stopping, use `/simulation/start` to restart.

---

## Error handling

All endpoints return standard HTTP status codes. The FastAPI framework handles validation errors (422) and internal errors (500) automatically with JSON error responses.
