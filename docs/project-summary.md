# entwine — Project Summary

**entwine** is an LLM-powered digital twin of a small-to-medium enterprise (SME). It simulates how a real company operates — its people, communications, decisions, and software development — using AI agents that behave like employees.

---

## What is entwine?

A **digital twin** is a running software model of a real-world system. entwine applies this idea to a company: instead of modelling a factory floor or a power grid, it models the people, workflows, and digital tools that make up a small business.

Each simulated employee is an AI agent — a piece of software powered by a large language model (LLM) — that has a job title, a personality, goals, domain knowledge, and access to real digital platforms (email, Slack, GitHub, social media). The agents work, communicate, make decisions, and produce real digital artefacts during a simulation run.

---

## Why?

Running experiments on a real company is slow, risky, and expensive. entwine lets teams compress time and explore "what if" questions safely.

| Use case | Description |
|----------|-------------|
| **Training** | Onboard employees or test processes against a realistic simulated environment before going live. |
| **Process testing** | Validate new workflows, escalation paths, or communication policies without disrupting real staff. |
| **What-if analysis** | Explore the downstream effects of a strategic decision — a product launch, a pricing change, a hiring decision. |
| **Content pipeline testing** | Generate realistic volumes of social media posts, emails, Slack messages, and code PRs to stress-test content moderation, analytics pipelines, or review tooling. |
| **Research** | Study how information propagates through an organisation, how roles influence decision-making, or how AI assistants interact with human-like peers. |

---

## How it works

At a high level, entwine runs a configurable number of AI agents — typically around 12 — simultaneously. Each agent:

1. **Has a defined persona**: a job title, background, goals, working hours, and the set of tools available to that role.
2. **Reads from a shared knowledge base**: company documents, procedures, and context, filtered by what that role should have access to.
3. **Reacts to events**: messages from other agents, scheduled tasks, or triggers from the simulation clock.
4. **Takes actions**: sends emails, posts to social media, writes code, drafts documents, or delegates tasks to colleagues.
5. **Observes the results**: reads replies, monitors metrics, and adjusts its next actions accordingly.

A lightweight simulation engine controls time (which can run faster than real time), routes messages between agents, and monitors agent health. A browser-based dashboard shows what every agent is doing in real time.

The simulation is configured entirely through human-readable files — an org chart, persona definitions, and simulation parameters — so different enterprise scenarios can be swapped in without writing code.

---

## The simulated enterprise

A typical entwine simulation runs roughly 12 agents covering a realistic SME org chart:

| Role | What they do in the simulation |
|------|-------------------------------|
| CEO | Sets priorities, reviews reports, makes strategic decisions |
| CMO | Plans and executes marketing campaigns |
| CTO | Oversees technical direction, reviews architecture |
| Developer (1–3) | Writes code, opens pull requests, fixes bugs |
| Product Manager | Writes specs, assigns tasks, liaises between dev and business |
| Sales representative | Drafts outreach emails, follows up with prospects |
| Customer support agent | Handles incoming support queries |
| Marketing specialist | Creates social media content, drafts blog posts |
| Data analyst | Generates reports, answers ad-hoc data questions |
| HR / Operations | Coordinates internal comms, onboarding, scheduling |

Agents interact with each other as colleagues would: a product manager assigns a feature task to a developer, a CMO approves a social post drafted by a marketing specialist, a CEO sends a company-wide update over Slack.

Working hours are simulated: agents are active during configured business hours and idle outside them, with urgent events able to wake them early — just like real employees.

---

## Platform integrations

Agents do not just send messages to each other. They interact with the same external platforms a real SME uses:

| Platform | Integration | What agents do |
|----------|-------------|----------------|
| **X (Twitter)** | Real — Basic API tier ($200/month) | Post updates, read mentions, engage with content |
| **LinkedIn** | Simulated (partner approval required for real API) | Posts and engagement logged internally; synthetic responses returned |
| **Gmail** | Real — Google Workspace OAuth | Send and read email as named personas |
| **Office 365** | Real — Microsoft Graph API | Send and read email via service accounts |
| **Reddit** | Real — standard OAuth | Post to subreddits, read community discussions |
| **Slack** | Real — internal app (no Marketplace review) | Post in channels, read threads, DM colleagues |
| **GitHub** | Real — GitHub App | Open issues, push branches, create pull requests |

All platform interactions go through a shared adapter layer that handles authentication, rate limiting, and retry logic centrally. Simulated adapters (like LinkedIn) expose exactly the same interface as real ones, so agents cannot tell the difference — and can be promoted to real integrations later without changing agent code.

---

## Coder agents

One of entwine's distinctive capabilities is the ability to simulate software developers who write, test, and commit actual code.

A coder agent uses the [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) to run an autonomous coding loop: it reads files, writes code, runs tests, and iterates until the task is complete — the same engine that powers Claude Code. Crucially, all code execution happens inside an isolated microVM (provided by [E2B](https://e2b.dev/)), so AI-generated code never runs on the host machine.

The workflow mirrors a real engineering team:

1. A product manager agent posts a task to the shared event bus.
2. A coder agent picks it up, clones the simulated company's GitHub repository into a fresh sandbox, and begins work.
3. The coder opens a pull request on GitHub with a real diff.
4. A QA agent reviews the PR using read-only tools.
5. A peer coder agent may add review comments.
6. A simulated CI system returns a pass/fail result; the coder iterates if needed.

This produces genuine git history, real code diffs, and reviewable pull requests — not synthetic placeholders.

---

## Technology choices

| Component | Choice | Why |
|-----------|--------|-----|
| Language | Python 3.12+ | Dominant ecosystem for AI/LLM tooling; best agent frameworks and RAG libraries |
| LLM provider | Anthropic Claude (primary), OpenAI (fallback) | Best prompt-caching economics; highest rate limits for multi-agent workloads |
| LLM routing | LiteLLM Router | Unified interface across providers; built-in fallback chains and cost tracking |
| Vector store | Qdrant (self-hosted via Docker) | Native async Python client; native hybrid search; free to self-host |
| Embeddings | OpenAI `text-embedding-3-small` | Negligible cost at project scale; good retrieval quality |
| Web framework | FastAPI + HTMX + SSE | Real-time monitoring dashboard; Python-only stack; no JS build pipeline |
| Configuration | TOML + YAML (Pydantic-validated) | Declarative, version-controlled scenario definitions |
| Coder sandbox | E2B microVM (Firecracker) | VM-level isolation; 150 ms startup; pay-per-second; no daemon to manage |
| Deployment | Docker Compose on a single Linux VM | Simple; sufficient for 12-agent workload; scales to Kubernetes if needed |
| CI/CD | GitHub Actions + `ghcr.io` | Free for public repos; native Docker registry integration |

**Cost profile:** With a tiered model strategy (routine tasks on Claude Haiku, standard reasoning on Claude Sonnet, complex planning on Claude Opus) and prompt caching, running 12 agents costs roughly **$8–12 per hour** — about 4x cheaper than running all agents on the same model without caching.

---

## Current status and roadmap

| Milestone | Status | Scope |
|-----------|--------|-------|
| **M1 — Analysis & Architecture** | Complete | Technology evaluation; all ADRs written and accepted |
| **M2 — Core Platform & Agent Framework** | Complete | Agent lifecycle, event bus, LLM integration, persona config, supervisor, tool dispatcher |
| **M3 — Platform Integrations** | Complete | Real adapters for Slack (`slack-sdk`), GitHub (`httpx`), Gmail (`google-api-python-client`), X/Twitter (`tweepy`); enhanced LinkedIn simulation; shared `PlatformClient` base with rate limiting and exponential backoff; factory auto-selects real vs stub based on credentials |
| **M4 — Enterprise Modeling & Roles** | Complete | Org chart, roles, responsibilities, inter-agent communication patterns |
| **M5 — User Interface & Observability** | Complete | HTMX + SSE monitoring dashboard, agent status cards, simulation controls |
| **M6 — End-to-End Scenarios & Testing** | Complete | Cost tracking with per-agent/global budget enforcement; regression test suite; performance benchmarks (throughput, latency p50/p95/p99, memory); scripted multi-agent scenarios (morning standup, customer escalation, campaign launch) |
| **M7 — Usage Documentation** | Complete | Quickstart guide, configuration reference, platform adapter setup guides (Slack, GitHub, Gmail, X, LinkedIn), operator runbook, API/endpoint reference, architecture overview for contributors |

---

## Architecture decisions (ADR index)

All significant decisions are recorded as Architecture Decision Records in [`docs/adr/`](adr/):

| ADR | Title | Summary |
|-----|-------|---------|
| [001](adr/001-programming-language-and-runtime.md) | Programming Language and Runtime | Python 3.12+ with asyncio, uv, FastAPI, and ruff |
| [002](adr/002-llm-providers-and-integration-strategy.md) | LLM Providers and Integration Strategy | Anthropic Claude as primary, OpenAI as fallback, via LiteLLM Router with three cost tiers |
| [003](adr/003-rag-approaches-and-knowledge-management.md) | RAG Approaches and Knowledge Management | Qdrant vector store with hybrid search; shared collection with role-based metadata filtering |
| [004](adr/004-user-interaction-model.md) | User Interaction Model | Config-as-code (TOML/YAML) for simulation setup; FastAPI + HTMX + SSE for real-time monitoring |
| [005](adr/005-agent-architecture-and-lifecycle.md) | Agent Architecture and Lifecycle | Continuous asyncio coroutine loop per agent; in-process event bus; non-LLM supervisor |
| [006](adr/006-platform-api-integration.md) | Platform API Integration Feasibility | Real integrations for X, Gmail, Office 365, Reddit, Slack, GitHub; simulated LinkedIn adapter |
| [007](adr/007-deployment-and-infrastructure.md) | Deployment and Infrastructure Architecture | Docker Compose on a single VM; Caddy reverse proxy; GitHub Actions CI/CD |
| [008](adr/008-project-conventions-and-workflow.md) | Project Conventions and Development Workflow | Trunk-based git workflow; Conventional Commits; mypy strict; 80% test coverage floor |
| [010](adr/010-agentic-developer-integration.md) | Agentic Developer Integration for Coder Roles | Claude Agent SDK for coder agents; E2B microVM sandboxes; real GitHub PRs |
