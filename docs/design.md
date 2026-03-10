# entsim — System Design and Architecture

**Date:** 2026-03-10

This document synthesises ADR-001 through ADR-010 into a cohesive system design reference. See the individual ADRs in `docs/adr/` for full rationale behind each decision.

---

## 1. System Overview

entsim is a digital twin platform that simulates SME operations using ~12 concurrent LLM-powered agents representing employees (CEO, CMO, developers, sales, QA, etc.). Agents interact with real external platforms (X, Gmail, Reddit, Slack, GitHub, Office 365) and a shared enterprise knowledge base to produce realistic simulated business activity.

**Key properties:**

- Single-process Python 3.12 asyncio application (ADR-001)
- I/O-bound workload: agents spend most time awaiting LLM API responses
- Config-as-code: TOML + YAML files define the simulated enterprise (ADR-004)
- Observable via a browser-based HTMX dashboard with SSE streaming (ADR-004)
- Deployable on a single Linux VM with Docker Compose (ADR-007)

### High-level architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         entsim process                              │
│                                                                     │
│  ┌─────────────┐   ┌──────────────────────────────────────────┐    │
│  │    CLI      │   │           FastAPI server                 │    │
│  │  (typer)    │   │  ┌──────────────┐  ┌──────────────────┐ │    │
│  └──────┬──────┘   │  │  HTMX/SSE   │  │   REST / API     │ │    │
│         │          │  │  Dashboard  │  │   endpoints      │ │    │
│         │          │  └──────┬───────┘  └────────┬─────────┘ │    │
│         │          └─────────│──────────────────│─────────────┘    │
│         │                    │ SSE events        │ control cmds     │
│         ▼                    ▼                   ▼                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  SimulationSupervisor                        │  │
│  │          (asyncio task — plain Python, not LLM)             │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │ manages                                 │
│        ┌──────────────────┼──────────────────┐                     │
│        ▼                  ▼                  ▼                     │
│  ┌───────────┐    ┌───────────────┐   ┌─────────────┐             │
│  │  Agent A  │    │   Agent B     │   │  Coder C    │             │
│  │ (asyncio  │    │  (asyncio     │   │ (asyncio    │             │
│  │   Task)   │    │    Task)      │   │   Task +    │             │
│  └─────┬─────┘    └──────┬────────┘   │  SDK loop)  │             │
│        │                 │            └──────┬───────┘             │
│        └─────────────────┴───────────────────┘                     │
│                          │ asyncio.Queue (event bus)                │
│                          │ shared world-state dict                  │
│                          ▼                                          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Tool Dispatcher                          │  │
│  └────┬───────────┬──────────┬──────────────┬───────────────────┘  │
│       │           │          │              │                       │
│       ▼           ▼          ▼              ▼                       │
│  Platform    Platform   Platform     knowledge                      │
│  adapters   adapters   adapters      query                         │
│  (real)     (real)    (simulated)                                  │
└───────┬───────────┬────────────────────────┬────────────────────────┘
        │           │                        │
        ▼           ▼                        ▼
  External       External             ┌──────────────┐
  platforms      platforms            │   Qdrant     │
  (X, Gmail,     (GitHub,             │  (Docker)    │
  Reddit, Slack, Office 365)          └──────────────┘
  LinkedIn stub)
        │                        ┌────────────────────┐
        │                        │  LiteLLM Router    │
        └────────────────────────►  Anthropic / OAI   │
                                 │  / Ollama (dev)    │
                                 └────────────────────┘
```

---

## 2. Component Architecture

| Component | Location | Technology | ADR |
|---|---|---|---|
| Agent runtime | `src/entsim/agents/` | asyncio coroutines + dataclasses | ADR-005 |
| LLM integration | `src/entsim/agents/` | LiteLLM Router | ADR-002 |
| RAG / knowledge layer | `src/entsim/rag/` | Qdrant + text-embedding-3-small | ADR-003 |
| Platform adapters | `src/entsim/platforms/` | tweepy, asyncpraw, slack-sdk, etc. | ADR-006 |
| Event bus | In-process | `asyncio.Queue` per agent | ADR-005 |
| Simulation supervisor | `src/entsim/agents/supervisor.py` | Plain Python asyncio task | ADR-005 |
| Config model | `src/entsim/config/` | Pydantic Settings + TOML + YAML | ADR-004 |
| Monitoring UI | `src/entsim/web/` | FastAPI + HTMX + sse-starlette | ADR-004 |
| CLI | `src/entsim/` | typer | ADR-004 |
| Coder sub-system | `src/entsim/agents/coder/` | Claude Agent SDK + E2B | ADR-010 |
| Observability | Cross-cutting | structlog + OpenTelemetry + Prometheus | ADR-007 |

### Package structure (ADR-008)

```
src/entsim/
├── agents/
│   ├── base.py          # AgentRuntime, lifecycle states, event loop
│   ├── memory.py        # working context, short-term buffer, Qdrant writes
│   ├── supervisor.py    # SimulationSupervisor
│   ├── tools.py         # tool dispatcher
│   └── coder/           # CoderAgent, E2B wiring, SDK hooks
├── config/              # Pydantic Settings, TOML/YAML loaders
├── platforms/           # one module per platform adapter
├── rag/                 # Qdrant client, embedding calls, hybrid search
└── web/                 # FastAPI app, HTMX routes, SSE endpoint
```

---

## 3. Agent System

### 3.1 Lifecycle

```
CREATED ──init()──► READY ──start()──► RUNNING
                                          │
                      ◄──resume()── PAUSED ◄──pause()──┤
                                          │
                                        ERROR ◄──exception──┤
                                          │
                                    STOPPED ◄──stop()──┤
```

| State | Behaviour |
|---|---|
| `CREATED` | Instance constructed; no asyncio task |
| `READY` | Persona + config loaded; task not started |
| `RUNNING` | Coroutine active; processing events |
| `PAUSED` | Sleeping on `asyncio.Event`; zero LLM cost |
| `ERROR` | Exception caught; supervisor notified |
| `STOPPED` | Task cancelled; resources released |

### 3.2 Agent loop (per agent, per tick)

```
1. Wait for trigger (scheduled tick / inbound message / external event)
2. Assemble context (persona + short-term memory + RAG results)
3. Call LiteLLM Router → Claude (tier selected by role config)
4. Dispatch tool calls; integrate results
5. Publish output events to agent bus; write memories
6. Back to step 1
```

Agents sleep between ticks — zero CPU or LLM cost when idle (ADR-005).

### 3.3 Memory layers

| Layer | Storage | Scope | Retention |
|---|---|---|---|
| Working context | In-process list (last N messages) | One loop iteration | Cleared each tick |
| Short-term buffer | In-process circular buffer | Simulation session | Lost on process restart |
| Long-term memory | Qdrant (`agent_id` metadata filter) | Across sessions | Explicit expiry |
| Shared world state | In-process dict (`asyncio.Lock`) | All agents | Session-scoped |

Short-term buffer is pruned by importance score when it approaches the LLM's context window. Long-term reads use hybrid RAG search filtered by `agent_id` (ADR-003).

### 3.4 Persona loading

Personas are declarative YAML, loaded and validated at startup by Pydantic Settings (ADR-004):

```yaml
agents:
  - id: cmo
    role: "Chief Marketing Officer"
    goal: "Grow brand awareness and generate qualified leads"
    backstory: "10-year B2B SaaS marketing veteran, data-driven"
    llm_tier: standard          # → Claude Sonnet 4.6
    working_hours: "08:00-18:00"
    rag_access: [marketing, sales, company-wide]
    tools: [post_to_linkedin, draft_email, read_crm, query_knowledge]
```

No code change is needed to add or modify an agent role.

### 3.5 Inter-agent communication

| Pattern | Mechanism | When to use |
|---|---|---|
| Event bus (primary) | `asyncio.Queue` per agent; typed `AgentMessage` dataclasses | Delegation, status updates, meeting requests |
| Shared world state | Shared dict behind `asyncio.Lock` | Simulation-global facts (date, company metrics, campaigns) |
| Direct tool call | Agent A tool invokes Agent B's handler | Synchronous request-reply (CEO asks CMO for a report) |

No external broker; all 12 agents share one asyncio event loop with zero serialisation overhead (ADR-005).

### 3.6 Supervisor

`SimulationSupervisor` is a plain Python asyncio task — not an LLM:

- Monitors every agent `asyncio.Task` for exceptions
- On `ERROR`: logs, emits SSE event to dashboard, applies recovery strategy
- Recovery options per agent: `restart` / `pause` (alert operator) / `skip` (degrade)
- Propagates global pause/resume via a shared `asyncio.Event`

### 3.7 Scheduling

A `SimulationClock` drives simulation time (configurable speed multiplier, e.g. 10× real time). Each agent loop checks `current_hour` against its `working_hours` config; it idles outside those hours unless an urgent event exceeds a configurable urgency threshold.

### 3.8 Observability hooks

Every lifecycle transition emits a structured log entry and an SSE fragment to the dashboard (ADR-004):

| Hook | Trigger |
|---|---|
| `on_agent_start` / `on_agent_stop` | RUNNING / STOPPED transitions |
| `on_agent_pause` / `on_agent_error` | PAUSED / ERROR transitions |
| `on_llm_start` / `on_llm_end` | LiteLLM call boundaries |
| `on_tool_start` / `on_tool_end` | Tool dispatch boundaries |
| `on_message_sent` | Agent publishes to event bus |
| `on_memory_write` | Long-term memory updated |

---

## 4. Data Flow

### 4.1 Standard agent action: post to X

```
SimulationClock tick
        │
        ▼
CMO Agent loop wakes
        │
        ├─► RAG query: "recent campaigns, brand voice" → Qdrant hybrid search
        │         (dept=marketing filter, dense+sparse RRF)
        │
        ├─► Assemble context: persona + short-term buffer + RAG results
        │
        ├─► LiteLLM Router → Claude Sonnet 4.6 (Tier 2)
        │         returns: tool_call{ name="post_to_x", args={text: "..."} }
        │
        ├─► Tool dispatcher → XAdapter.send(text)
        │         → tweepy async client → X Basic API ($200/mo)
        │         → returns: tweet_id, metrics
        │
        ├─► on_tool_end hook → SSE event → HTMX dashboard
        │
        ├─► AgentMessage{type="post_published"} → agent bus
        │         (other agents, e.g. analytics agent, may react)
        │
        └─► Memory write: short-term buffer + Qdrant long-term
```

### 4.2 Inter-agent delegation: CEO assigns report to CMO

```
CEO Agent
  ├─► LLM decides: request quarterly report from CMO
  ├─► tool_call{ name="delegate_task", recipient="cmo", task="Q2 report" }
  └─► Tool dispatcher → AgentMessage{type="task_delegation", reply_to=corr_id}
                                │ → CMO's asyncio.Queue
                                ▼
                         CMO Agent wakes on message
                           ├─► RAG + LLM → draft report
                           └─► AgentMessage{type="task_result", reply_to=corr_id}
                                       │ → CEO's asyncio.Queue
                                       ▼
                               CEO Agent resumes
```

---

## 5. Integration Architecture

### 5.1 LLM providers (ADR-002)

```
LiteLLM Router
├── "routine"  → anthropic/claude-haiku-4-5      ($1/$5 per MTok)
├── "standard" → anthropic/claude-sonnet-4-6     ($3/$15)
│               fallback: openai/gpt-4.1         ($2/$8)
├── "complex"  → anthropic/claude-opus-4-6       ($5/$25)
└── dev only   → ollama/llama4-scout             (free, local)
```

| Tier | Target volume | Typical users |
|---|---|---|
| Tier 1 (routine) | ~70% of requests | Data retrieval, template filling, classification |
| Tier 2 (standard) | ~25% | Most agent reasoning, platform interactions |
| Tier 3 (complex) | ~5% | Orchestration decisions, multi-domain planning |

Prompt caching on shared system prompts (org structure, simulation rules) targets ≥60% cache hit rate — ~4× cost reduction vs. naive single-model usage.

Rate-limit strategy: LiteLLM Router `max_parallel_requests` per deployment; monitor `anthropic-ratelimit-*` headers; cross-provider fallback on saturation.

### 5.2 Vector store (ADR-003)

```
Qdrant (Docker, Apache 2.0)
├── Collection: enterprise_docs
│     ├── Dense vectors: text-embedding-3-small (1536d, OpenAI)
│     ├── Sparse vectors: SPLADE
│     └── Metadata: { department, sensitivity, accessible_roles, source, updated_at }
│
└── Query path:
      Agent requests knowledge
        ├─► Dense ANN retrieval (semantic similarity)
        ├─► Sparse BM25/SPLADE retrieval (keyword matching)
        └─► RRF fusion: score = Σ 1/(60 + rank_i)
              filtered by accessible_roles matching agent's rag_access config
```

One collection; no per-agent duplication. Role-based access enforced by metadata pre-filter server-side.

### 5.3 Platform adapters (ADR-006)

All adapters implement a common async interface (`send`, `read`, `search`) backed by a shared `PlatformClient` base class with asyncio exponential backoff and `Retry-After` / `X-RateLimit-Reset` header handling.

| Platform | Type | Library | Auth | Monthly cost |
|---|---|---|---|---|
| X (Twitter) | Real (Basic) | tweepy async | OAuth 2.0 | $200 |
| LinkedIn | Simulated stub | `LinkedInAdapter` | n/a | Free |
| Gmail | Real | google-auth-oauthlib + googleapiclient | OAuth 2.0 (3-legged) | Free (Workspace billed separately) |
| Office 365 | Real | msal + httpx | OAuth 2.0 (client creds) | Free (M365 license required) |
| Reddit | Real | asyncpraw | OAuth 2.0 | Free |
| Slack | Real (internal app) | slack-sdk | Bot token | Free |
| GitHub | Real (GitHub App) | PyGithub / httpx | OAuth 2.0 / PAT | Free |

LinkedIn is simulated: the `LinkedInAdapter` stub logs intended actions to Qdrant with `status=simulated` and returns plausible synthetic responses. Agents are unaware; swap to real adapter when partner access is obtained.

---

## 6. Coder Agent Subsystem (ADR-010)

Coder agents are standard entsim agents with an extended tool set and a sandboxed execution environment.

### 6.1 Architecture

```
CoderAgent (asyncio Task)
    │
    ├─► Receives TaskAssigned event from PM agent (via agent bus)
    │
    ├─► Starts Claude Agent SDK session (async generator)
    │     allowed_tools: [Read, Write, Edit, Bash, Glob, Grep]
    │     PreToolUse hook: intercepts Bash → routes to E2B sandbox
    │
    │   ┌─────────────────────────────────────────┐
    │   │  E2B microVM (Firecracker)              │
    │   │  ├─ git clone <simulated-repo>          │
    │   │   ├─ Run AI-generated code safely       │
    │   │  └─ git push branch → GitHub API       │
    │   └─────────────────────────────────────────┘
    │
    ├─► Posts PROpened event → agent bus → QA agent / peer agent
    │
    ├─► QA agent runs read-only SDK session (Read, Glob, Grep only)
    │     posts review comments to GitHub
    │
    └─► Coder resumes session on CIResult / review event
```

### 6.2 Coder vs. standard agent

| Aspect | Standard agent | Coder agent |
|---|---|---|
| Tool set | Platform adapters (post, email, etc.) | Read, Write, Edit, Bash, Glob, Grep |
| LLM tier | Haiku (routine) or Sonnet (standard) | Sonnet (execution), Opus (planning) |
| Session length | Short (2K–10K tokens) | Long (20K–500K+ tokens) |
| Sandbox | None needed | E2B Firecracker microVM |
| Concurrency limit | Config: all agents | Config: `max_coder_agents` (default 2) |
| Cost relative to social/email agents | 1× | 10–50× per session |
| Git interaction | None | Real branches + PRs on simulated repo |
| CI/CD | n/a | Simulated stub (webhook events with synthetic results) |

### 6.3 Cross-role workflow

```
PM agent  ──TaskAssigned──►  Coder agent  ──PROpened──►  QA agent
                                │                           │
                                │◄─────── CIResult ─────────┤
                                │         (stub)            │
                                │◄─── ReviewComment ────────┘
                                │     (GitHub API)
                                └──► (resumes session, fixes issues)
```

All events flow over the existing `asyncio.Queue` bus — no new IPC mechanism.

### 6.4 Security model

| Risk | Mitigation |
|---|---|
| Untrusted code escapes sandbox | E2B Firecracker VM (separate kernel) |
| Sandbox exfiltrates host secrets | Secrets injected explicitly; no host env access |
| Malicious code in real repos | Simulated repo is isolated; real org repos never connected |
| Runaway E2B cost | Session timeout; `max_session_tokens` budget enforced via hook |
| Prompt injection via repo content | Bash restricted to sandbox; network tools excluded by default |

---

## 7. Configuration Model (ADR-004)

Two complementary config file types, both validated by Pydantic Settings at startup:

| Format | File | Content |
|---|---|---|
| TOML | `entsim.toml` | Flat simulation parameters: timing, LLM settings, feature flags, speed multiplier |
| YAML | `enterprise.yaml` | Hierarchical: org chart, agent personas, role relationships, platform credentials |

Config is loaded via Pydantic Settings with layered priority: **file defaults < environment variables < CLI overrides**.

### Key YAML sections

```yaml
simulation:
  speed_multiplier: 10          # 10× real time
  start_date: "2026-03-10"

agents:
  - id: ceo
    role: "Chief Executive Officer"
    llm_tier: complex
    working_hours: "07:00-20:00"
    rag_access: [company-wide]
    tools: [delegate_task, read_metrics, post_to_slack]

  - id: coder_alice
    type: coder                  # activates coder subsystem (ADR-010)
    llm_tier: standard
    sandbox: e2b
    repo: git@github.com:acme/backend.git
    max_session_tokens: 200000
    ci_stub: true

platforms:
  x:
    enabled: true
    tier: basic
  linkedin:
    enabled: true
    mode: simulated              # LinkedInAdapter stub
```

Config-as-code enables reproducible simulation experiments via git branches (e.g., branch per scenario).

---

## 8. Deployment (ADR-007)

### 8.1 Service topology

| Service | Image | Role |
|---|---|---|
| `entsim` | `python:3.12-slim` (local build) | FastAPI + agent runtime + supervisor |
| `qdrant` | `qdrant/qdrant:latest` | Vector store |
| `ollama` | `ollama/ollama:latest` | Local LLM (dev only) |

All in Docker Compose. No message broker, no orchestrator.

### 8.2 Environments

| Environment | Command | Notes |
|---|---|---|
| Local dev | `docker compose up` | Applies `compose.override.yaml`; bind mounts, Ollama, debug ports |
| Prod-like local | `docker compose -f compose.yaml -f compose.prod.yaml up -d` | Resource limits, image tags, no bind mounts |
| Production | Single 4 vCPU / 16 GB VM, Caddy reverse proxy (auto-TLS) | `docker compose pull && docker compose up -d` via GitHub Actions deploy workflow |

### 8.3 CI/CD (GitHub Actions)

| Workflow | Trigger | Steps |
|---|---|---|
| `ci.yml` | Push / PR (any branch) | ruff lint, mypy strict, pytest (unit only) |
| `build.yml` | Push to `main` | Build image, push to `ghcr.io` with `sha` + `latest` tags |
| `deploy.yml` | Manual or `v*` tag | SSH to VM, `docker compose up -d` |

### 8.4 Observability stack

| Signal | Tool | Notes |
|---|---|---|
| Traces | OpenTelemetry → Jaeger (dev) / OTLP (prod) | Add early; backend is swappable |
| Metrics | Prometheus + Grafana | Add when logs cannot answer the question |
| Logs | structlog → stdout (JSON) → Docker log driver | Minimum viable from day one |
| LLM cost | `litellm.completion_cost()` logged per call | Application layer; no extra infra |

### 8.5 Secrets

| Context | Strategy |
|---|---|
| Local dev | `.env` file (git-ignored), loaded by `docker compose env_file:` |
| CI | GitHub Actions secrets |
| Production | Environment variables injected at container start |

Required secrets: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, platform OAuth tokens. All consumed via Pydantic Settings; startup fails fast if required vars are missing.

---

## 9. ADR Reference Index

| ADR | Decision | Key outcome |
|---|---|---|
| ADR-001 | Python 3.12 + asyncio + uv + FastAPI | Single-language stack, richest AI ecosystem |
| ADR-002 | LiteLLM Router, Anthropic primary, 3-tier model strategy | ~4× cost reduction; provider portability |
| ADR-003 | Qdrant (self-hosted), hybrid search (SPLADE + dense + RRF) | Native async, role-based filtering, zero ongoing cost |
| ADR-004 | Config-as-code (TOML/YAML) + FastAPI + HTMX + SSE | Browser-accessible monitoring; reproducible experiments |
| ADR-005 | Custom asyncio coroutine loop, in-process event bus, non-LLM supervisor | Minimal complexity for 12 long-lived agents |
| ADR-006 | Real integrations (X, Gmail, Office 365, Reddit, Slack, GitHub); LinkedIn simulated | Six real platforms; partner-gated platforms stubbed |
| ADR-007 | Docker Compose, single VM, Caddy, GitHub Actions | Low operational overhead; ~$50–100/mo infra |
| ADR-008 | Trunk-based dev, Conventional Commits, mypy strict, ruff, pytest | Consistent quality from day one |
| ADR-010 | Claude Agent SDK + E2B microVM sandboxes for coder agents | Realistic coding simulation with VM-level isolation |
