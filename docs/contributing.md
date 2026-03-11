# Architecture Overview for Contributors

## Project structure

```
src/entwine/
  agents/       # Agent framework: BaseAgent, StandardAgent, Supervisor, persona models, prompts
  cli/          # Typer CLI: start, validate, version commands
  config/       # YAML/TOML loader + Pydantic models (FullConfig, SimulationConfig, etc.)
  events/       # EventBus (async pub/sub) + typed event models
  llm/          # LLMRouter (LiteLLM), tier routing, completion models
  observability/# CostTracker with budget enforcement
  platforms/    # Platform adapters (Slack, GitHub, Gmail, X, LinkedIn), factory, registry
  rag/          # KnowledgeStore (Qdrant), EmbeddingService, hybrid search
  simulation/   # SimulationEngine, SimulationClock
  tools/        # ToolDispatcher, built-in tools (delegate_task, query_knowledge, read_metrics)
  web/          # FastAPI app, HTMX dashboard, SSE streaming

tests/
  unit/         # Isolated unit tests (mocked dependencies)
  integration/  # Engine regression tests, platform adapter tests
  scenarios/    # Multi-agent scripted scenarios (standup, escalation, campaign)
  benchmarks/   # Performance: throughput, latency percentiles, memory
```

## Key abstractions

| Abstraction | Base class | Location |
|-------------|------------|----------|
| Agent | `BaseAgent` → `StandardAgent` | `agents/base.py`, `agents/standard.py` |
| Platform | `PlatformAdapter` (ABC) | `platforms/adapter.py` |
| Event | `Event` (Pydantic) | `events/models.py` |
| Tool | `ToolCall` / `ToolResult` | `tools/dispatcher.py` |
| LLM | `LLMRouter` | `llm/router.py` |

## How to add a new platform adapter

1. Create `src/entwine/platforms/<name>.py`
2. Implement `PlatformAdapter`:
   ```python
   class MyLiveAdapter(PlatformAdapter):
       platform_name = "myplatform"
       async def send(self, action: str, payload: dict) -> dict: ...
       async def read(self, query: str, limit: int = 10) -> list[dict]: ...
       def available_actions(self) -> list[str]: ...
   ```
3. Add credential settings to `platforms/settings.py` (Pydantic Settings with `ENTWINE_` prefix)
4. Register in `platforms/factory.py` — try real adapter if credentials present, fall back to stub
5. Add stub to `platforms/stubs.py` for credential-free operation
6. Add optional dependency to `pyproject.toml` if an SDK is needed
7. Write tests in `tests/unit/test_platforms.py`
8. Add setup guide in `docs/platforms/<name>.md`

## How to add a new agent tool

1. Add handler function in `src/entwine/tools/builtin.py`:
   ```python
   async def my_tool(arg1: str, arg2: int = 0) -> str:
       """Tool description."""
       return "result"
   ```
2. Register in `SimulationEngine.__init__`:
   ```python
   dispatcher.register(
       name="my_tool",
       handler=my_tool,
       description="What this tool does.",
       parameters={"type": "object", "properties": {...}, "required": [...]},
   )
   ```
3. Add tool name to agent personas in config YAML
4. Write unit test for the handler

## How to add a new agent persona

Config-only — no code changes. Add an entry to the `agents:` list in your YAML config:

```yaml
agents:
  - name: "New Person"
    role: "Job Title"
    department: "Department"
    goal: "What they do"
    llm_tier: "standard"
    tools: [draft_email, query_knowledge]
```

## Test structure

| Directory | Purpose | Run command |
|-----------|---------|-------------|
| `tests/unit/` | Fast, isolated, mocked | `uv run pytest tests/unit/ -q` |
| `tests/integration/` | Engine + subsystem wiring | `uv run pytest tests/integration/ -q` |
| `tests/scenarios/` | Multi-agent scripted flows | `uv run pytest tests/scenarios/ -q` |
| `tests/benchmarks/` | Performance baselines | `uv run pytest tests/benchmarks/ -q` |

All tests: `uv run pytest tests/ -q`

## Definition of Done

| Gate | Command |
|------|---------|
| Lint clean | `uv run ruff check src/ tests/` |
| Format clean | `uv run ruff format --check src/ tests/` |
| Tests green | `uv run pytest tests/ -q` |
| Coverage >= 80% | Check `pytest-cov` output |
| Docs current | ADRs, design.md, infrastructure.md reflect changes |
| Clean tree | `git status` shows no unstaged changes |

## Code style

- **Formatter/linter**: ruff (line-length 100, target py312)
- **Type checking**: mypy strict
- **Async**: stdlib asyncio everywhere; no threads except Google API wrapper
- **Models**: Pydantic v2 for all data classes
- **Settings**: Pydantic Settings with `ENTWINE_` env prefix
- **Imports**: absolute imports; `from __future__ import annotations` in all modules
