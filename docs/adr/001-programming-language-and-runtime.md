# ADR-001: Programming Language and Runtime

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#1](https://github.com/DigitalTwinSystems/entsim/issues/1)

## Context

We need to choose a primary programming language and runtime for entsim — a digital twin platform that simulates SME operations using ~12 concurrent LLM agents interacting with external platforms (X, LinkedIn, Gmail/Office365, Reddit).

The workload is fundamentally I/O-bound: agents spend most of their time waiting for LLM API responses (100ms–30s per call). The language choice should optimize for ecosystem maturity, developer velocity, and framework availability rather than raw compute performance.

We evaluated four options: Python, TypeScript/Node.js, Go, and Rust, as well as hybrid multi-language approaches.

## Decision

**Python** is the primary language for entsim.

Specific choices:

| Component | Choice |
|-----------|--------|
| Python version | 3.12+ |
| Package manager | uv |
| Async runtime | asyncio (stdlib) |
| HTTP framework | FastAPI |
| Linting/formatting | ruff |
| Type checking | mypy or pyright |
| Containerization | Docker (python:3.12-slim) |

## Rationale

### Why Python

- **Agent framework dominance.** Every major agent framework is Python-native or Python-first: AutoGen/AG2, CrewAI, LangGraph, LlamaIndex, Claude Agent SDK, OpenAI Agents SDK, Pydantic AI. No other language comes close.
- **RAG ecosystem.** Best-in-class tooling: sentence-transformers, ChromaDB, Qdrant, FAISS, LlamaIndex document loaders (150+ connectors), mature chunking and embedding libraries.
- **LLM SDK maturity.** Official, production-grade async SDKs from Anthropic (`AsyncAnthropic`) and OpenAI (`AsyncOpenAI`). LiteLLM provides a unified interface across 100+ providers.
- **Concurrency is sufficient.** `asyncio.TaskGroup` with async HTTP clients handles 12 concurrent agents easily. The GIL is irrelevant for I/O-bound LLM API calls. CPU-bound work (if any) can be offloaded via `asyncio.to_thread()` or `ProcessPoolExecutor`.
- **Developer velocity.** Fastest path from idea to working agent. Abundant tutorials, examples, and community knowledge.

### Why not TypeScript/Node.js

TypeScript is a viable alternative with excellent async I/O, well-typed LLM SDKs, and the largest package ecosystem (npm). However:
- The agent framework ecosystem is narrower (Vercel AI SDK and LangChain.js are the main options).
- RAG tooling is less mature — fewer document loaders, less battle-tested chunking strategies.
- LangChain.js historically lags behind Python LangChain in features.

Would reconsider if the team were TypeScript-native.

### Why not Go

Go has official LLM SDKs and excellent concurrency (goroutines), but:
- LangChainGo is far less feature-complete than Python LangChain.
- No equivalents to CrewAI, AutoGen, LangGraph, or LlamaIndex.
- Fewer RAG building blocks and AI community resources.

Go remains a good candidate for infrastructure components if needed later.

### Why not Rust

Rust offers the best raw performance and memory safety, but:
- No official Anthropic SDK. Community OpenAI crate (`async-openai`) is the main option.
- Agent framework ecosystem is nascent (Rig is promising but early).
- Development velocity cost is too high for the project's current stage.

### Why not hybrid from day one

Teams building multi-agent systems consistently report that:
- At ~12 agents, there is no scale problem justifying multi-language complexity.
- The real challenges are prompt engineering, agent memory, and LLM API reliability — all application-layer concerns.
- "Start monolith, split later" is the well-validated pattern.

## Consequences

### Positive
- Access to the richest AI/LLM ecosystem available
- Fastest iteration speed for agent development
- Largest hiring pool for AI-focused developers
- Single language reduces operational complexity (one build pipeline, one deployment, unified debugging)

### Negative
- Deployment requires shipping a Python runtime (mitigated by Docker containers)
- Slower startup than compiled languages (not meaningful for a long-running service)
- If a component later needs extreme performance, it must be extracted to a compiled language
- Type safety is opt-in (mitigated by mypy/pyright and ruff)

### Future escape hatches
- **Temporal** (Go server, Python SDK) if workflow durability becomes critical — no Go code needed from our side.
- **Go/Rust sidecar** if a specific component (embedding server, rate limiter, API gateway) needs extraction for performance.
- These are not planned; they are documented options to revisit only when a concrete bottleneck is measured.
