---
project_name: 'entwine'
user_name: 'Mikkel Damsgaard'
date: '2026-03-14'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 52
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

| Layer | Component | Version |
|-------|-----------|---------|
| Runtime | Python | ≥3.12 |
| Package manager | uv | (project standard — no pip/poetry) |
| Web | FastAPI | ≥0.115 |
| Web server | uvicorn[standard] | ≥0.34 |
| SSE | sse-starlette | ≥2.2 |
| LLM routing | LiteLLM Router | ≥1.60 |
| Vector store | Qdrant (self-hosted Docker) | qdrant-client ≥1.13 |
| Embeddings | OpenAI text-embedding-3-small | openai ≥1.60 |
| Validation | Pydantic v2 | ≥2.10 |
| Config | pydantic-settings | ≥2.7 |
| HTTP client | httpx (async) | ≥0.28 |
| Logging | structlog | ≥25.1 |
| CLI | typer | ≥0.15 |
| Platform: Slack | slack-sdk | ≥3.33 |
| Platform: Gmail | google-api-python-client | ≥2.160 |
| Platform: X | tweepy | ≥4.14 |
| Platform: GitHub | httpx (no extra SDK) | — |
| Lint/format | ruff | ≥0.15.5 |
| Type checking | mypy (strict) | ≥1.14 |
| Testing | pytest + pytest-asyncio + pytest-cov | ≥8.3 / ≥1.3 / ≥6.0 |
| Build | hatchling | — |

## Critical Implementation Rules

### Language-Specific Rules

- **`from __future__ import annotations`** — always include at top of every module; enables PEP 563 postponed evaluation, required for forward references with mypy strict
- **mypy strict mode** — all code must pass `mypy --strict`; no `# type: ignore` without comment explaining why; use `TYPE_CHECKING` guard for import cycles
- **`TYPE_CHECKING` imports** — put imports only needed for type annotations under `if TYPE_CHECKING:` to avoid circular imports (pattern used throughout `agents/`, `events/`)
- **`StrEnum` for enumerations** — use `StrEnum` (not plain `Enum`) so values serialize to strings directly; see `AgentState`
- **Pydantic v2 models** — all data models inherit `BaseModel`; use `Field(...)` for required fields, `Field(default_factory=...)` for mutable defaults; never use mutable defaults directly
- **`asyncio_mode = "auto"`** — all test coroutines are auto-detected by pytest-asyncio; no `@pytest.mark.asyncio` decorator needed
- **Async-only I/O** — never use blocking I/O in async code; all HTTP via `httpx.AsyncClient`, all LLM calls via `await router.complete()`
- **structlog for logging** — always `log = structlog.get_logger(__name__)`; use keyword args (`log.info("event.name", key=val)`); never use stdlib `logging` directly
- **Line length** — 100 chars (ruff enforced); double quotes; 4-space indent
- **Ruff rules** — `E, W, F, B, I, UP, C4, SIM, PTH, RUF` enabled; `E501` (line length) and `B008` (typer defaults) ignored
- **pathlib over os.path** — `PTH` rule enforced; use `Path` everywhere, never `os.path.join` etc.
- **isort via ruff** — imports must be sorted: stdlib → third-party → local; enforced by `I` rule set

### Framework & Architecture Rules

**Agent pattern:**
- All agents subclass `BaseAgent`; override `_query_rag`, `_call_llm`, `_dispatch_tools`, `_emit_events`, `_update_memory` — never override `_run` directly
- Agent loop is driven by `_next_event()` (asyncio.Queue with timeout); always handle `None` return (timeout tick)
- Lifecycle: `CREATED → READY → RUNNING ↔ PAUSED → STOPPED/ERROR`; call `start()` only when state is `READY`; `stop()` is idempotent
- `working_memory` cleared every tick; `short_term_memory` is a `deque(maxlen=256)` persisted across ticks
- Use typed `EventBus` (`subscribe`/`publish`) not raw `asyncio.Queue` for new agents

**Event bus:**
- `EventBus.publish()` is fire-and-forget (puts on internal queue); delivery happens in background `_dispatch_loop`
- Handlers can be sync callables or async coroutines — bus detects via `asyncio.iscoroutine(result)`
- `subscribe_all()` for monitoring/logging; `subscribe(event_type, cb)` for targeted handling
- Always call `await bus.start()` before publishing; `await bus.stop()` drains queue before shutdown

**LLM Router:**
- Three tiers: `LLMTier.ROUTINE` (Haiku), `LLMTier.STANDARD` (Sonnet), `LLMTier.COMPLEX` (Opus)
- Always call `await router.complete(tier, messages, tools)` — never call litellm directly
- Messages must be OpenAI-compatible format: `[{"role": "user", "content": "..."}]`
- Cost is auto-tracked per call via `litellm.completion_cost()`

**Platform adapters:**
- All adapters subclass `PlatformAdapter` (ABC) — must implement `platform_name`, `send`, `read`, `available_actions`
- All adapters also subclass `PlatformClient` for HTTP calls — use `self._request()`, never raw httpx directly
- Factory auto-selects real vs stub adapter based on credential presence — never instantiate adapters directly, use factory
- Real and stub adapters expose identical interfaces — agents cannot tell the difference

**FastAPI / SSE:**
- Real-time dashboard uses SSE via `sse-starlette`; push events with `EventSourceResponse`
- Config loaded at startup via `pydantic-settings`; all settings from env vars, never hardcoded

**Config:**
- Root model: `FullConfig` (simulation + enterprise + agents list)
- Loaded from TOML/YAML; validated by Pydantic on load
- `AgentPersona.llm_tier` is a string key (`"routine"`, `"standard"`, `"complex"`) — not the `LLMTier` enum

### Testing Rules

**Structure:**
- `tests/unit/` — fast, no external services; mock LLM/platform/Qdrant calls
- `tests/integration/` — require running services; mark with `@pytest.mark.integration`; skipped in normal CI
- `tests/scenarios/` — multi-agent end-to-end scripted scenarios (morning standup, customer escalation, campaign launch)
- `tests/benchmarks/` — performance benchmarks (throughput, latency p50/p95/p99, memory)
- Test file naming: `test_<module>.py` mirroring `src/entwine/<module>.py`

**pytest config:**
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed; just `async def test_...`
- Coverage target: `--cov=src/entwine --cov-report=term-missing`; minimum 80% (`--cov-fail-under=80`)
- Run: `uv run pytest tests/ -q`; lint: `uv run ruff check src/ tests/`; format check: `uv run ruff format --check src/ tests/`

**Test patterns:**
- Use `asyncio.Queue()` directly when constructing `BaseAgent` in tests (not a full `EventBus` unless testing bus integration)
- Mock LLM responses by patching `LLMRouter.complete` — never make real API calls in unit tests
- `AgentPersona` can be constructed inline in tests with minimal fields: `name`, `role`, `goal` are required
- Use `pytest-asyncio` fixtures with `async def` — no `asyncio.run()` in tests
- Integration tests that need Qdrant: start via Docker Compose; tests skip gracefully if service unavailable

**Coverage:**
- New/changed code must have tests before merge
- Overall coverage must stay ≥80%
- No skipped tests except `@pytest.mark.integration` (external-service tests)

### Code Quality & Style Rules

**Ruff configuration:**
- Line length: 100 chars; double quotes; 4-space indent
- Enabled rule sets: `E, W, F, B, I, UP, C4, SIM, PTH, RUF`
- Ignored: `E501` (line length — handled by formatter), `B008` (typer requires `Option()` in defaults)
- Run formatter before checking: `uv run ruff format src/ tests/` then `uv run ruff check src/ tests/`

**File & module structure:**
- Package root: `src/entwine/` (hatchling src layout)
- Subpackages: `agents/`, `cli/`, `config/`, `events/`, `llm/`, `observability/`, `platforms/`, `rag/`, `simulation/`, `tools/`, `web/`
- Each subpackage has `__init__.py`; public API exported from `__init__.py`; implementation in named modules
- Models in `models.py`, settings in `settings.py`, main logic in descriptively named modules

**Naming conventions:**
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE` with module-level `_` prefix for private (e.g. `_SHORT_TERM_MAXLEN`)
- Private methods: `_single_leading_underscore`
- Event type strings: `noun.verb` format (e.g. `"agent.started"`, `"event_bus.published"`)

**Docstrings & comments:**
- Module-level docstring required (one line summary)
- Class docstring required for public classes
- Comments only where logic is non-obvious; no redundant comments
- No inline `# noqa` without explanation

**mypy strict requirements:**
- All function signatures fully annotated (params + return type)
- `Any` permitted only with explicit rationale
- No implicit `Optional` — use `X | None` syntax (Python 3.10+ union syntax)
- `dict[str, Any]` for untyped external API payloads is acceptable

### Development Workflow Rules

**Git:**
- Trunk-based: all work branches off `main`; short-lived feature branches
- Commit messages: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`)
- No force-push to `main`

**Definition of Done (all gates must pass before merge):**
1. `uv run ruff check src/ tests/` — zero errors
2. `uv run ruff format --check src/ tests/` — zero reformats
3. `uv run pytest tests/ -q` — all green, no skips (except `@pytest.mark.integration`)
4. Coverage ≥80% (`--cov-fail-under=80`)
5. New/changed code has tests
6. ADRs, `docs/design.md`, `docs/infrastructure.md`, `docs/project-summary.md` updated if decision/architecture changed

**Adding dependencies:**
- Add via `uv add <pkg>` (not pip); commit updated `pyproject.toml` and lockfile
- Optional platform deps go in `[project.optional-dependencies]` not core deps
- Do a quick health check: recent releases, active maintenance, adoption

**ADRs:**
- Significant technical decisions → new ADR in `docs/adr/`
- Follow format of `docs/adr/001-programming-language-and-runtime.md`
- Number sequentially; don't reuse or delete

**CI/CD:**
- GitHub Actions + `ghcr.io` for Docker images
- Docker Compose for local dev and single-VM deployment
- Caddy reverse proxy in front of uvicorn

### Critical Don't-Miss Rules

**Anti-patterns to avoid:**
- ❌ Never subclass `PlatformAdapter` without also subclassing `PlatformClient` — the base class provides rate limiting and retry logic all adapters need
- ❌ Never instantiate platform adapters directly — always use the factory; it selects real vs stub based on credentials
- ❌ Never call `asyncio.run()` inside async code or tests — already inside a running loop
- ❌ Never use `time.sleep()` in async code — use `await asyncio.sleep()`
- ❌ Never call litellm directly — always go through `LLMRouter.complete()`; direct calls bypass cost tracking and tier routing
- ❌ Never override `BaseAgent._run()` — override the five hook methods instead
- ❌ Never put mutable objects as Pydantic field defaults — always use `Field(default_factory=...)`
- ❌ Never use stdlib `logging` — always structlog with `log = structlog.get_logger(__name__)`
- ❌ Never use `os.path` — use `pathlib.Path`; ruff `PTH` rules will catch this
- ❌ Never add new dependencies without updating `pyproject.toml` via `uv add`

**Edge cases:**
- `BaseAgent._next_event()` returns `None` on timeout — callers must handle `None` before processing
- `EventBus.stop()` drains the queue (`await queue.join()`) — ensure all publishers are done before stopping or it will block
- `AgentPersona.llm_tier` is validated as a free-form string, not the `LLMTier` enum — map it explicitly when constructing `LLMRouter` calls
- `PlatformClient._request()` raises the last exception after exhausting retries — callers must handle `httpx.HTTPStatusError`
- `RateLimiter` uses `asyncio.Lock` — acquiring it in a tight loop without `await asyncio.sleep()` will starve other coroutines

**Security:**
- Never log credentials, API keys, or tokens — structlog bindings are inspectable; use masked placeholders
- All agent-generated code runs inside E2B microVM sandboxes — never execute AI-generated code on the host
- Platform credentials loaded from env vars only — never hardcode or commit secrets

**Budget enforcement:**
- `global_budget_usd` and `per_agent_budget_usd` in `SimulationConfig` are hard limits — the supervisor enforces them and will stop agents; always set sensible values in simulation configs
- Cost is tracked per `CompletionResponse.cost_usd` — ensure all LLM calls go through `LLMRouter` so cost is captured

---

## Usage Guidelines

**For AI Agents:**
- Read this file before implementing any code in this project
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**
- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review quarterly for outdated rules
- Remove rules that become obvious over time

_Last Updated: 2026-03-14_
