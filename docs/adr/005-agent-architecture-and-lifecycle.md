# ADR-005: Agent Architecture and Lifecycle

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#5](https://github.com/DigitalTwinSystems/entsim/issues/5)

## Context

entsim simulates SME operations using ~12 concurrent LLM agents that represent employees (CEO, CMO, developers, sales, etc.). Each agent must:

- Maintain a persona, goals, and role-appropriate knowledge
- Run continuously or on schedule across a simulation session
- Communicate with other agents and interact with external platforms (X, LinkedIn, Gmail/Office365, Reddit)
- Be observable, pausable, and recoverable from failures

We reviewed four agent framework patterns before deciding on a custom lightweight design:

| Framework | Lifecycle model | Communication | Memory | Notes |
|-----------|----------------|---------------|--------|-------|
| [AutoGen/AG2](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html) | Stateful, task-driven `run()` | Structured message types (TextMessage, ToolCallEvent) | Accumulated message history per agent | SelectorGroupChat, Swarm, GraphFlow orchestration patterns |
| [CrewAI](https://docs.crewai.com/concepts/agents) | Task execution model; `kickoff()` per crew run | Tool-based + delegation | `respect_context_window` summarization; pluggable memory | Persona via role/goal/backstory YAML |
| [LangGraph](https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/) | Graph nodes; LLM → tool → loop | MessagesState; ToolMessage accumulation | Persistent state via checkpointers | Supervisor via orchestrator-worker graph; `Send` API for parallel workers |
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | Built-in agent loop; Runner manages execution | Handoffs + function tools; MCP integration | Sessions (SQLAlchemy-backed); working context | RunHooks/AgentHooks for lifecycle events; manager vs. handoff orchestration |

**Key insight from all frameworks:** agents are fundamentally a loop — `LLM call → tool dispatch → result integration → repeat until done`. The differences are in how state is persisted, how agents coordinate, and how lifecycle events are surfaced.

entsim's requirements differ from typical chatbot/workflow agents:

- Agents are **long-lived and continuous**, not single-task runners. A CEO agent runs for the duration of a simulation session (hours).
- Agents simulate **human-like schedules** — they are active during configured working hours and idle otherwise.
- **12 agents are a small, known set**, not a dynamic swarm. The topology is fixed per simulation.
- All agents share a Python asyncio process (ADR-001). Cross-process communication is not needed initially.

## Decision

### Agent execution model: continuous event-driven loop

Each agent runs as an `asyncio.Task` executing a coroutine loop. The loop:

1. Waits for the next trigger (scheduled tick, incoming message, or external event)
2. Assembles context (persona, memory, relevant messages, RAG results)
3. Calls LiteLLM Router with assembled context + tool definitions (ADR-002)
4. Dispatches any tool calls; integrates results
5. Publishes output events; updates memory
6. Loops back to step 1

Agents do **not** run on a fixed poll interval. They sleep until triggered, keeping CPU and LLM cost at zero when idle.

### Lifecycle states

```
CREATED ──init()──► READY ──start()──► RUNNING
                                          │
                      ◄──resume()── PAUSED ◄──pause()──┤
                                          │
                                        ERROR ◄──exception──┤
                                          │
                                    STOPPED ◄──stop()──┤
```

| State | Description |
|-------|-------------|
| `CREATED` | Instance constructed; no asyncio task yet |
| `READY` | Persona and config loaded; task not started |
| `RUNNING` | asyncio task active; processing events |
| `PAUSED` | Task suspended via asyncio.Event; no LLM calls |
| `ERROR` | Unhandled exception caught; supervisor notified |
| `STOPPED` | Task cancelled cleanly; resources released |

### Agent anatomy

Each agent is a Python dataclass + coroutine class:

```
AgentConfig (YAML)
    └── AgentPersona       # role, goals, backstory, working hours
    └── AgentMemory        # short-term buffer + long-term Qdrant refs
    └── AgentRuntime       # asyncio task handle, state, event queues
    └── AgentTools         # registered tool functions for this role
```

**Persona definition** lives in YAML (per ADR-004 config-as-code):

```yaml
agents:
  - id: cmo
    role: "Chief Marketing Officer"
    goal: "Grow brand awareness and generate qualified leads"
    backstory: "10-year B2B SaaS marketing veteran, data-driven, prefers LinkedIn and content marketing"
    llm_tier: standard          # maps to LiteLLM Router model (ADR-002)
    working_hours: "08:00-18:00"
    rag_access: [marketing, sales, company-wide]
    tools: [post_to_linkedin, draft_email, read_crm, query_knowledge]
```

### Memory architecture

| Layer | Storage | Scope | Retention |
|-------|---------|-------|-----------|
| **Working context** | In-process Python list (last N messages) | Single agent loop iteration | Cleared each tick |
| **Short-term memory** | In-process circular buffer (configurable window) | Current simulation session | Lost on restart |
| **Long-term memory** | Qdrant collection (ADR-003) with `agent_id` metadata | Persistent across sessions | Explicit expiry |
| **Shared world state** | In-process dict (asyncio-safe via Lock) | All agents | Session-scoped |

Short-term buffer size defaults to the LLM's effective context window, pruned by importance score when full. Long-term memories are written asynchronously; reads use RAG hybrid search filtered by `agent_id`.

### Inter-agent communication

Three patterns, in order of preference:

| Pattern | Mechanism | Use case |
|---------|-----------|----------|
| **Event bus** (primary) | `asyncio.Queue` per agent; publisher posts typed events | Most agent-to-agent signals (meeting requests, status updates, delegation) |
| **Shared world state** | Shared dict behind `asyncio.Lock` | Simulation-global facts visible to all agents (current date, company metrics, active campaigns) |
| **Direct tool call** | Agent A calls a tool that invokes Agent B's handler | Synchronous request-reply (CEO asks CMO for a report; waits for response) |

No external message broker (Redis, RabbitMQ) is introduced at this scale. All 12 agents share a process and can communicate in-memory with zero serialization overhead.

Event types are typed Python dataclasses:

```python
@dataclass
class AgentMessage:
    sender_id: str
    recipient_id: str          # or "broadcast"
    message_type: str          # e.g. "task_delegation", "status_update"
    payload: dict
    timestamp: datetime
    reply_to: str | None       # correlation id for request-reply
```

### Supervisor pattern

A lightweight `SimulationSupervisor` asyncio task monitors all agents:

- Watches each agent's `asyncio.Task` for exceptions
- On `ERROR` state: logs, emits SSE event (ADR-004 monitoring), applies recovery strategy
- Recovery strategies (configured per agent):
  - `restart` — reinitialize agent with same config; reload short-term memory from last checkpoint
  - `pause` — suspend agent; alert operator; resume on manual command
  - `skip` — mark agent as degraded for the session; simulation continues without it
- Respects simulation pause/resume: sets a global `asyncio.Event` that all agent loops check

The supervisor is **not** an LLM agent itself — it is plain Python control logic. This avoids the "quis custodiet" problem of an LLM supervising LLMs.

### Agent-to-platform interaction

Agents interact with external platforms (X, LinkedIn, Gmail, Reddit) exclusively via **tools** — Python async functions registered in the agent's tool list. The LLM cannot call external APIs directly.

```
Agent LLM output ──► tool_call{name, args}
                            │
                    Tool dispatcher
                            │
            ┌───────────────┼───────────────┐
            │               │               │
      post_to_x()    send_email()    post_to_linkedin()
            │               │               │
      Platform API    Platform API    Platform API
```

Tools are sandboxed: they can fail without crashing the agent. Failed tool calls return an error result that the LLM can reason about and retry or escalate.

### Scheduling: continuous vs. scheduled

Agents run **continuously during their configured working hours**. Outside working hours, the agent loop idles (sleeping on a condition variable). This simulates realistic human availability:

- A `SimulationClock` drives the simulation time (configurable speed multiplier, e.g. 10× real time)
- Each agent checks `simulation_clock.current_hour` against its `working_hours` config on each loop iteration
- Agents can be triggered outside working hours by urgent events (configurable urgency threshold)

### Observability hooks

Each lifecycle transition and significant agent event emits a structured log entry and an SSE event to the monitoring dashboard (ADR-004). Hooks mirror the [OpenAI Agents SDK `RunHooks` pattern](https://openai.github.io/openai-agents-python/ref/lifecycle/):

| Hook | Trigger |
|------|---------|
| `on_agent_start` | Agent enters RUNNING |
| `on_agent_pause` | Agent enters PAUSED |
| `on_agent_error` | Unhandled exception caught |
| `on_agent_stop` | Agent enters STOPPED |
| `on_llm_start` / `on_llm_end` | LiteLLM call boundaries |
| `on_tool_start` / `on_tool_end` | Tool dispatch boundaries |
| `on_message_sent` | Agent publishes a message |
| `on_memory_write` | Long-term memory updated |

## Rationale

### Why a custom loop over adopting a framework

| Criterion | AutoGen | CrewAI | LangGraph | Custom loop |
|-----------|---------|--------|-----------|-------------|
| Continuous long-lived agents | Awkward (task-oriented) | Awkward (crew.kickoff per run) | Possible with persistent state | Natural (coroutine loop) |
| asyncio-native | Partial | No (uses threads internally) | Yes (async graph execution) | Yes (asyncio.Task) |
| Working-hour simulation | Not built in | Not built in | Not built in | Config-driven |
| 12-agent fixed topology | Over-engineered | Over-engineered | Good fit | Simple |
| Dependency footprint | Heavy | Heavy | Medium | Minimal |
| LiteLLM integration | Via model_client | Via LLM config | Via model | Direct |

For 12 known, long-lived agents in a single asyncio process, a thin custom loop is less complexity than adopting a framework. Frameworks add value when agent topology is dynamic, unknown at startup, or requires a visual builder. None of those conditions apply here.

If requirements change (dynamic agent spawning, cross-process distribution), [LangGraph](https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/) is the first framework to adopt: it is asyncio-native, supports persistent state via checkpointers, and integrates cleanly with LiteLLM.

### Why event bus over direct messaging

- Decouples sender and receiver — agents don't hold references to each other
- Natural fan-out for broadcast events (simulation state changes)
- Easy to replay for debugging (queue is inspectable)
- Avoids deadlocks that arise from synchronous agent-to-agent calls in an async loop

### Why in-process over external broker

At 12 agents on one host, Redis/RabbitMQ add operational overhead with no throughput or reliability benefit. Asyncio queues handle thousands of messages per second without network I/O. If agents are later distributed across hosts, the event bus abstraction layer makes migration to an external broker (NATS, Redis Streams) a localized change.

### Why a non-LLM supervisor

LLM-based supervisors (as in some AutoGen and CrewAI orchestration patterns) are appealing but introduce:
- Non-determinism in recovery decisions
- Additional LLM cost and latency per supervision cycle
- Circular failure modes (supervisor LLM fails when system is under stress)

Plain Python supervision is fast, cheap, deterministic, and testable.

## Consequences

### Positive

- Simple mental model: each agent is one asyncio coroutine + config YAML
- Persona and tools are fully config-driven — adding/modifying agents requires no code changes
- In-process communication eliminates serialization overhead and external dependencies
- Custom loop gives precise control over scheduling, memory management, and observability
- Lifecycle hooks feed directly into the ADR-004 monitoring dashboard without extra plumbing
- Non-LLM supervisor is fully unit-testable

### Negative

- Custom loop code must implement what frameworks provide for free (retry logic, context windowing, hook dispatch)
- No framework community or plugin ecosystem to draw on for new agent capabilities
- If agent count grows substantially or agents need cross-host distribution, the in-process event bus must be replaced
- Working-hour simulation adds state that must be handled correctly across pause/resume cycles
- Short-term memory is lost on process restart unless checkpointing is added (future work)

### Future escape hatches

- **LangGraph migration**: if dynamic topology or cross-process distribution is needed, the agent loop can be replaced with a LangGraph graph while keeping persona config, tool definitions, and memory layers intact.
- **External event broker**: replace `asyncio.Queue` with NATS or Redis Streams by swapping the event bus adapter — agent code unchanged.
- **Persistent short-term memory**: add a Redis or SQLite checkpoint per agent to survive restarts without full long-term memory retrieval.
