---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: complete
inputDocuments:
  - docs/project-summary.md
  - docs/design.md
  - docs/infrastructure.md
  - docs/adr/001-programming-language-and-runtime.md
  - docs/adr/002-llm-providers-and-integration-strategy.md
  - docs/adr/003-rag-approaches-and-knowledge-management.md
  - docs/adr/004-user-interaction-model.md
  - docs/adr/005-agent-architecture-and-lifecycle.md
  - docs/adr/006-platform-api-integration.md
  - docs/adr/007-deployment-and-infrastructure.md
  - docs/adr/008-project-conventions-and-workflow.md
  - docs/adr/010-agentic-developer-integration.md
  - github://milestones/13 (M8 open issues)
  - github://milestones/14 (M9 open issues)
  - github://milestones/15 (M10 open issues)
  - github://milestones/17 (M12 open issues)
  - github://milestones/18 (M13 open issues)
---

# entwine - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for entwine, decomposing the remaining requirements from open GitHub milestones (M8 remaining, M9 remaining, M10, M12, M13) into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: System must provide a document ingestion CLI (`entwine ingest --source <dir>`) that chunks, embeds, and upserts docs into Qdrant with metadata (department, sensitivity, source path)
FR2: System must include sample company knowledge base documents (~7 realistic Acme Corp docs across departments)
FR3: System must enforce role-based RAG access by filtering Qdrant queries by agent's `rag_access` field against `accessible_roles` document metadata
FR4: System must support hybrid search (dense + BM25/SPLADE sparse + RRF fusion) with tunable parameters and evaluation dataset
FR5: System must integrate E2B Firecracker microVM sandboxes for isolated coder agent code execution
FR6: Coder agents must implement autonomous coding loop via Claude Agent SDK (read files → write code → run tests → iterate)
FR7: Coder agents must open real pull requests on GitHub via GitHubLiveAdapter after completing tasks
FR8: QA agent must review PRs using read-only GitHub tools and post review comments
FR9: Coder agent tools must include: read_file, write_file, run_command, search_code, git_commit, git_push (all routed to E2B sandbox)
FR10: System must support real platform integrations verified in production: Slack, GitHub, Gmail, X (Twitter)
FR11: System must have monitoring and alerting: health check polling, cost alerting at 80% budget, agent ERROR state alerting
FR12: System must produce post-simulation analysis report (cost breakdown, events, platform actions, observations, failure modes)
FR13: Economics subsystem must implement append-only SQLite ledger via `aiosqlite` with double-entry bookkeeping
FR14: Economics subsystem must implement chart of accounts (13 accounts across asset/liability/revenue/expense/transfer types)
FR15: Economics subsystem must implement balance sheet computation with `as_of` historical snapshots
FR16: Economics subsystem must implement multi-level spending approval hierarchy via event bus (agent → manager chain → CEO; CEO auto-approves)
FR17: System must integrate PayPal (real via `paypal-server-sdk` optional dep + stub adapter following existing pattern)
FR18: Agents must have 7 economics tools: record_expense, record_revenue, request_payment, check_balance, get_balance_sheet, get_ledger_snapshot, create_invoice
FR19: Economics API must expose 4 endpoints: GET /ledger, GET /ledger/snapshot, GET /balance-sheet, GET /accounts
FR20: Economics subsystem must be wired into SimulationEngine lifecycle (init_db on start, close on stop, tools registered)
FR21: Deployment VM must be provisioned (4 vCPU / 8 GB RAM / 50 GB SSD, Docker + Compose, Caddy TLS, firewall)
FR22: First live simulation must be run and documented (12-agent config, 1-2 hours, cost/events/actions captured)

### NonFunctional Requirements

NFR1: All new code must pass `uv run ruff check` and `uv run ruff format --check` with zero errors
NFR2: All new code must pass `uv run mypy src/ --strict`
NFR3: Coverage must remain ≥80% (`--cov-fail-under=80`) after all new code
NFR4: Integration tests requiring external services (Qdrant, E2B, PayPal, GitHub) must be marked `@pytest.mark.integration` and skipped in normal CI
NFR5: Optional dependencies (e2b, paypal, claude-agent-sdk) must not break installation when absent; factory falls back to stubs
NFR6: Decimal amounts in ledger stored as TEXT in SQLite; deserialized to Python `Decimal` — no float precision loss
NFR7: E2B sandbox sessions must have configurable `max_session_tokens` budget and timeout to prevent runaway cost
NFR8: Coder agent concurrency must be configurable via `max_coder_agents` (default 2) in simulation config
NFR9: PayPal integration must support sandbox environment (`api-m.sandbox.paypal.com`) for testing

### Additional Requirements

- `aiosqlite` must be added to core dependencies in `pyproject.toml`
- `e2b` SDK added as optional dep (`entwine[coder]`)
- `paypal-server-sdk>=0.6` added as optional dep (`entwine[paypal]`)
- `claude-agent-sdk` (or `anthropic` with agent support) added as optional dep
- `reports_to: str | None` field added to `AgentPersona` (backward-compatible, default `None`)
- `EconomicsConfig` added to `FullConfig` with defaults
- ADR-011 must be written for Economics subsystem
- All docs updated: design.md, infrastructure.md, project-summary.md, api.md, configuration.md

### UX Design Requirements

N/A — entwine has no UI beyond the existing HTMX/SSE dashboard (already implemented). No UX stories required.

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 1 | Document ingestion CLI |
| FR2 | Epic 1 | Sample KB documents |
| FR3 | Epic 1 | Role-based RAG filtering |
| FR4 | Epic 1 | Hybrid search tuning & evaluation |
| FR5 | Epic 2 | E2B sandbox integration |
| FR6 | Epic 2 | Claude Agent SDK coder loop |
| FR7 | Epic 2 | GitHub PR workflow |
| FR8 | Epic 2 | QA agent PR review |
| FR9 | Epic 2 | Coder tools (file I/O, shell, git) |
| FR10 | Epic 4 | Real platform verification |
| FR11 | Epic 4 | Monitoring & alerting |
| FR12 | Epic 4 | Post-run analysis report |
| FR13 | Epic 3 | SQLite append-only ledger |
| FR14 | Epic 3 | Chart of accounts |
| FR15 | Epic 3 | Balance sheet + historical snapshots |
| FR16 | Epic 3 | Spending approval hierarchy |
| FR17 | Epic 3 | PayPal integration (real + stub) |
| FR18 | Epic 3 | Agent economics tools (7 tools) |
| FR19 | Epic 3 | Economics API endpoints |
| FR20 | Epic 3 | Engine integration |
| FR21 | Epic 4 | Provision deployment VM |
| FR22 | Epic 4 | First live simulation run |

## Epic List

### Epic 1: Knowledge-Powered Agents
Operators can seed the simulation with real company documents and have agents make decisions grounded in role-appropriate knowledge, with retrieval quality they can measure and tune.
**FRs covered:** FR1, FR2, FR3, FR4

### Epic 2: Coder Agent Subsystem
Operators can configure developer agent roles that autonomously write, test, and commit real code inside an isolated sandbox, producing genuine GitHub PRs that QA agents review.
**FRs covered:** FR5, FR6, FR7, FR8, FR9

### Epic 3: Financial Simulation
Operators can run a financially-aware simulation where agents manage budgets, seek multi-level spending approval, and make real PayPal payments, with a full ledger and balance sheet accessible via API.
**FRs covered:** FR13, FR14, FR15, FR16, FR17, FR18, FR19, FR20

### Epic 4: Live Deployment & Operations
Operators can deploy entwine to a production VM, connect and verify real platform integrations, monitor a live simulation run, and receive a structured analysis report of what happened.
**FRs covered:** FR10, FR11, FR12, FR21, FR22

---

## Epic 1: Knowledge-Powered Agents

Operators can seed the simulation with real company documents and have agents make decisions grounded in role-appropriate knowledge, with retrieval quality they can measure and tune.

### Story 1.1: Document Ingestion Pipeline

As a simulation operator,
I want a CLI command that ingests documents from a directory into the Qdrant knowledge base,
So that I can populate the simulation with real company knowledge without writing code.

**Acceptance Criteria:**

**Given** a directory containing `.md`, `.txt`, `.pdf`, or `.docx` files
**When** I run `entwine ingest --source <dir> --config <config.yaml>`
**Then** all documents are chunked (configurable size + overlap), embedded via `text-embedding-3-small`, and upserted into the `enterprise_knowledge` Qdrant collection

**Given** a document is ingested
**When** it is stored in Qdrant
**Then** each chunk has metadata: `department`, `sensitivity`, `accessible_roles`, `source_path`, `content_hash`

**Given** I run ingest twice on the same file
**When** the content has not changed
**Then** the existing chunks are not re-embedded (idempotent via content hash dedup)

**Given** a large directory
**When** ingestion is running
**Then** progress is reported per-file to stdout and the command exits non-zero on failure

### Story 1.2: Sample Company Knowledge Base

As a simulation operator,
I want a ready-to-use sample knowledge base for Acme Corp included in the repository,
So that I can run a realistic simulation immediately without creating documents myself.

**Acceptance Criteria:**

**Given** the repository is cloned
**When** I look in `examples/knowledge/`
**Then** I find at least 7 documents covering: `company-handbook.md` (company-wide), `engineering-standards.md` (engineering), `marketing-playbook.md` (marketing), `sales-process.md` (sales), `support-runbook.md` (support), `product-roadmap.md` (executive), `onboarding-guide.md` (company-wide)

**Given** each sample document
**When** it is read
**Then** it is 500–1000 words of plausible, internally-consistent Acme Corp content with correct `department` and `accessible_roles` front-matter or metadata

**Given** the sample knowledge base
**When** I run `entwine ingest --source examples/knowledge/`
**Then** all 7 documents ingest without error

### Story 1.3: Role-Based Knowledge Access

As a simulation operator,
I want agents to only retrieve documents their role is permitted to access,
So that a sales agent cannot read engineering-only documents and the simulation reflects realistic information boundaries.

**Acceptance Criteria:**

**Given** documents ingested with `accessible_roles: [engineering, company-wide]`
**When** an agent with `rag_access: [engineering]` queries the knowledge store
**Then** those documents are returned

**Given** the same documents
**When** an agent with `rag_access: [marketing]` queries the knowledge store
**Then** the engineering-only documents are NOT returned

**Given** a `company-wide` document
**When** any agent queries the knowledge store
**Then** the document is returned regardless of the agent's department

**Given** the role filter is applied
**When** it is executed
**Then** filtering happens server-side in Qdrant via metadata pre-filter (not post-filter in Python)

### Story 1.4: Hybrid Search Tuning & Evaluation

As a simulation operator,
I want hybrid search (dense + sparse + RRF) enabled and its quality measurable,
So that agents retrieve the most relevant knowledge chunks and I can tune retrieval before running a long simulation.

**Acceptance Criteria:**

**Given** the Qdrant collection is configured
**When** it is initialised
**Then** it has both dense vectors (1536d, `text-embedding-3-small`) and sparse vectors (BM25/SPLADE) enabled

**Given** a query is issued
**When** results are retrieved
**Then** RRF fusion (k=60 default, configurable) combines dense and sparse rankings

**Given** `examples/evaluation/rag_eval_dataset.json` with 20 queries and expected relevant documents
**When** I run `entwine evaluate-rag --dataset examples/evaluation/rag_eval_dataset.json`
**Then** the command reports precision@5, recall@5, and MRR for dense-only vs hybrid modes

**Given** the evaluation results
**When** documented
**Then** optimal RRF parameters and collection settings are recorded in `docs/configuration.md`

---

## Epic 2: Coder Agent Subsystem

Operators can configure developer agent roles that autonomously write, test, and commit real code inside an isolated sandbox, producing genuine GitHub PRs that QA agents review.

### Story 2.1: E2B Sandbox Integration

As a simulation operator,
I want coder agents to execute code inside isolated E2B Firecracker microVM sandboxes,
So that AI-generated code never runs on the host machine and the simulation is safe to operate.

**Acceptance Criteria:**

**Given** `e2b` is added as optional dep (`entwine[coder]`) in `pyproject.toml`
**When** E2B credentials are absent
**Then** the coder subsystem is disabled gracefully and the rest of entwine starts normally

**Given** a `SandboxManager` is instantiated with a task
**When** `create_sandbox()` is called
**Then** an E2B Firecracker microVM is provisioned with Python 3.12, git, and common dev tools

**Given** an active sandbox
**When** `execute_command(cmd)` is called
**Then** the command runs inside the VM and returns stdout, stderr, and exit code

**Given** a sandbox with `max_session_tokens` or timeout reached
**When** the limit is exceeded
**Then** the sandbox is destroyed and a `SandboxTimeout` exception is raised

**Given** a task completes or fails
**When** `destroy_sandbox()` is called
**Then** the VM is torn down and all resources are released; unit tests mock the E2B client

### Story 2.2: Claude Agent SDK Coder Loop

As a simulation operator,
I want coder agents to autonomously implement tasks using the Claude Agent SDK,
So that developer agents produce real code changes through iterative read-write-test cycles.

**Acceptance Criteria:**

**Given** `CoderAgent` subclasses `StandardAgent` and receives a `TaskAssigned` event
**When** the agent starts work
**Then** it initiates a Claude Agent SDK session with tools: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`

**Given** the SDK session is active
**When** the agent issues a `Bash` tool call
**Then** it is intercepted via `PreToolUse` hook and routed to the E2B sandbox (not the host)

**Given** the coding loop runs
**When** it completes
**Then** token usage and cost are tracked through the existing `CostTracker` per agent

**Given** `max_session_tokens` is configured
**When** the session approaches the limit
**Then** the session is cleanly terminated and a `SessionBudgetExceeded` event is published

**Given** `max_coder_agents` is set (default 2) in simulation config
**When** more tasks arrive than the concurrency limit
**Then** excess tasks are queued until a coder slot is free

### Story 2.3: Coder Agent Tools

As a coder agent,
I want file I/O, shell execution, and git tools routed through my sandbox,
So that I can read, write, and commit code safely without accessing the host filesystem.

**Acceptance Criteria:**

**Given** the following tools are registered in `ToolDispatcher` for coder agents: `read_file`, `write_file`, `run_command`, `search_code`, `git_commit`, `git_push`
**When** any tool is called
**Then** it delegates to `SandboxManager` with configurable timeout and output size limits

**Given** `git_commit` is called with a message
**When** it executes
**Then** staged changes are committed inside the sandbox repo with the given message

**Given** `git_push` is called
**When** it executes
**Then** the branch is pushed to the remote GitHub repository via the sandbox's git credentials

**Given** a `run_command` call produces output exceeding the size limit
**When** the limit is hit
**Then** output is truncated and a warning is included in the tool result

### Story 2.4: GitHub PR Workflow

As a simulation operator,
I want coder agents to open real GitHub pull requests after completing tasks,
So that the simulation produces genuine git history, diffs, and reviewable PRs.

**Acceptance Criteria:**

**Given** a coder agent completes implementation and tests pass in the sandbox
**When** the agent calls `git_push`
**Then** a real PR is opened on the configured GitHub repository via `GitHubLiveAdapter` with the task description as PR body

**Given** a PR is opened
**When** the `PROpened` event is published to the agent bus
**Then** the QA agent and any subscribed peer coder agents receive it

**Given** a `CIResult` event arrives (simulated stub returning pass/fail)
**When** the result is a failure
**Then** the coder agent resumes its SDK session, reads the CI output, and iterates

**Given** the full workflow: task → code → PR → CI → review
**When** run as a scenario test with scripted agents
**Then** all events flow correctly over the existing asyncio event bus without new IPC

### Story 2.5: QA Agent PR Review

As a simulation operator,
I want a QA agent that reviews pull requests using read-only GitHub tools,
So that the simulated engineering team has a realistic code review step before merging.

**Acceptance Criteria:**

**Given** the QA agent receives a `PROpened` event
**When** it processes the event
**Then** it opens a read-only Claude Agent SDK session with only `Read`, `Glob`, `Grep` tools

**Given** the read-only session is active
**When** the agent reviews the PR diff
**Then** it analyses code quality, test coverage gaps, and style, then posts review comments via `GitHubLiveAdapter.add_comment()`

**Given** the review is complete
**When** the QA agent decides
**Then** it either approves the PR or requests changes by publishing a `ReviewComplete` event to the agent bus

**Given** no E2B credentials are present
**When** the QA agent attempts to review
**Then** it still functions (QA uses read-only tools only; no sandbox required)

---

## Epic 3: Financial Simulation

Operators can run a financially-aware simulation where agents manage budgets, seek multi-level spending approval, and make real PayPal payments, with a full ledger and balance sheet accessible via API.

### Story 3.1: Economics Data Models & ADR

As a developer,
I want foundational Pydantic models and ADR-011 for the economics subsystem,
So that all subsequent economics stories have a consistent, documented data contract to build on.

**Acceptance Criteria:**

**Given** `docs/adr/011-economics-and-financial-subsystem.md` is created
**When** it is read
**Then** it documents: SQLite+aiosqlite choice, USD-only currency, PayPal as payment provider, event-bus approval flow, CEO autonomy via `reports_to: None`, TEXT storage for Decimal

**Given** `src/entwine/economics/models.py` is created
**When** imported
**Then** it exports: `AccountType` (StrEnum), `Account`, `LedgerEntry`, `BalanceSheet`, `ApprovalRequest` — all Pydantic v2 models with correct field types

**Given** `AgentPersona` in `src/entwine/agents/models.py`
**When** loaded from YAML without a `reports_to` field
**Then** it defaults to `None` (backward-compatible)

**Given** `EconomicsConfig` added to `FullConfig`
**When** no `economics:` section appears in config YAML
**Then** it defaults to `initial_cash_usd=10000.00`, `ledger_db_path="entwine_ledger.db"`, `approval_threshold_usd=0.00`

**Given** all existing tests
**When** run after these changes
**Then** they all still pass (zero regressions)

### Story 3.2: Ledger & Chart of Accounts

As a simulation operator,
I want an append-only SQLite ledger with a standard chart of accounts,
So that all financial activity in the simulation is durably recorded with Decimal precision and queryable by time, agent, or category.

**Acceptance Criteria:**

**Given** `aiosqlite` added to core deps and `src/entwine/economics/ledger.py` created
**When** `await ledger.init_db()` is called
**Then** the `ledger_entries` table is created if it does not exist

**Given** a `LedgerEntry` is appended
**When** queried back
**Then** `amount_usd` round-trips as `Decimal` with no floating-point loss (stored as TEXT)

**Given** `query()` is called with filters (`agent_id`, `category`, `since`, `until`, `limit`, `offset`)
**When** filters are applied
**Then** only matching entries are returned, respecting pagination

**Given** `balance_by_account()` is called
**When** executed
**Then** it returns a `dict[str, Decimal]` with correct sums per account code

**Given** `default_chart()` in `src/entwine/economics/chart_of_accounts.py`
**When** called
**Then** it returns exactly 13 accounts covering all 5 types (asset, liability, revenue, expense, transfer) with unique codes

**Given** unit tests using SQLite `:memory:`
**When** run
**Then** all ledger and chart-of-accounts tests pass without external dependencies

### Story 3.3: Spending Approval Hierarchy

As a simulation operator,
I want agent spending to flow through a manager approval chain up to the CEO,
So that the simulation models realistic corporate financial governance.

**Acceptance Criteria:**

**Given** `src/entwine/economics/approval.py` with `ApprovalManager`
**When** a CEO agent (whose `reports_to` is `None`) requests approval
**Then** it is auto-approved immediately — no event published

**Given** a non-CEO agent requests approval
**When** `request_approval()` is called
**Then** a `SpendingApprovalRequested` event is published to the direct manager's inbox

**Given** a manager approves but is not the CEO
**When** `process_response()` is called with `approved=True`
**Then** the request is escalated to the manager's manager

**Given** any approver in the chain denies
**When** `process_response()` is called with `approved=False`
**Then** the chain stops and the request is marked `denied`

**Given** the full chain reaches the CEO and they approve
**When** processed
**Then** the request is marked `approved` and ready for payment execution

**Given** three new event types in `src/entwine/events/models.py`
**When** imported
**Then** `SpendingApprovalRequested`, `SpendingApprovalResponse`, and `TransactionRecorded` are available

### Story 3.4: PayPal Platform Integration

As a simulation operator,
I want a PayPal adapter (real + stub) following the existing platform pattern,
So that agents can trigger real PayPal payouts in production or fall back to a stub during testing.

**Acceptance Criteria:**

**Given** `paypal-server-sdk>=0.6` added as optional dep (`entwine[paypal]`)
**When** PayPal credentials are absent
**Then** the factory registers the `PayPalAdapter` stub — entwine starts normally

**Given** `ENTWINE_PAYPAL_CLIENT_ID` and `ENTWINE_PAYPAL_CLIENT_SECRET` are set
**When** the factory runs
**Then** `PayPalLiveAdapter` is registered, authenticating via OAuth2 client credentials

**Given** `PayPalLiveAdapter` is active
**When** `send("send_payout", payload)` is called
**Then** it calls `POST /v1/payments/payouts` on the configured environment (sandbox or live)

**Given** the stub adapter
**When** `send("send_payout", payload)` is called
**Then** it returns a simulated transaction reference (UUID) without making any real API call

**Given** `available_actions()` is called on either adapter
**When** returned
**Then** it lists `send_payout`, `create_invoice`, `search_transactions`, `get_balance`

### Story 3.5: Agent Economics Tools

As a simulation agent,
I want economics tools to record expenses, request payments, and check balances,
So that I can participate in the simulated company's financial activity using standard tool calls.

**Acceptance Criteria:**

**Given** 7 tools registered in `ToolDispatcher`: `record_expense`, `record_revenue`, `request_payment`, `check_balance`, `get_balance_sheet`, `get_ledger_snapshot`, `create_invoice`
**When** `record_expense` is called
**Then** two double-entry `LedgerEntry` records are appended: debit expense account (5xxx), credit cash account (1000/1010)

**Given** `record_revenue` is called
**When** appended
**Then** debit cash account, credit revenue account (4xxx)

**Given** `request_payment` is called by a non-CEO agent
**When** executed
**Then** it triggers the approval flow via `ApprovalManager`; on approval, calls PayPal adapter `send_payout` and records ledger entries with external tx ref

**Given** `check_balance` is called with an account code
**When** executed
**Then** it returns the current `Decimal` balance for that account

**Given** `get_ledger_snapshot` is called with optional filters
**When** executed
**Then** it returns paginated `LedgerEntry` list matching filters

### Story 3.6: Economics API & Engine Integration

As a simulation operator,
I want economics data accessible via HTTP endpoints and the ledger wired into the engine lifecycle,
So that I can inspect financial state via the API and the ledger persists correctly across simulation runs.

**Acceptance Criteria:**

**Given** `src/entwine/web/economics_routes.py` with an `APIRouter`
**When** mounted in `app.py`
**Then** four endpoints are available: `GET /ledger`, `GET /ledger/snapshot`, `GET /balance-sheet`, `GET /accounts`

**Given** `GET /ledger` is called with `limit=5&offset=10`
**When** returned
**Then** paginated entries are returned with `amount_usd` as strings (not floats)

**Given** `GET /balance-sheet?as_of=<ISO datetime>`
**When** executed
**Then** a historical snapshot is returned filtered to entries up to that timestamp

**Given** `SimulationEngine.start()` is called
**When** the engine initialises
**Then** `await ledger.init_db()` is called and an initial cash entry is appended if the ledger is empty

**Given** `SimulationEngine.stop()` is called
**When** executed
**Then** `await ledger.close()` is called cleanly

**Given** `ApprovalManager` is instantiated in the engine
**When** wired
**Then** it subscribes to `spending_approval_response` events on the event bus

---

## Epic 4: Live Deployment & Operations

Operators can deploy entwine to a production VM, connect and verify real platform integrations, monitor a live simulation run, and receive a structured analysis report of what happened.

### Story 4.1: Provision Deployment VM

As a simulation operator,
I want a production-ready Linux VM configured for entwine,
So that I have a stable, secure environment to run live simulations against real platforms.

**Acceptance Criteria:**

**Given** a cloud VM (AWS EC2 / DigitalOcean / Hetzner) with min 4 vCPU, 8 GB RAM, 50 GB SSD running Ubuntu 24.04 LTS
**When** provisioned following `docs/infrastructure.md`
**Then** Docker and Docker Compose v2 are installed and `docker compose version` succeeds

**Given** the VM is provisioned
**When** the firewall is configured
**Then** only ports 80, 443 (web) and SSH are open; all other inbound ports are blocked

**Given** a DNS record pointing to the VM IP
**When** Caddy is started
**Then** TLS certificates are issued via Let's Encrypt and `https://<domain>/health` returns `{"status": "ok"}`

**Given** `.env` is populated with real API keys
**When** `docker compose -f compose.yaml -f compose.prod.yaml up -d` is run
**Then** all services start healthy: `entwine` passes its healthcheck, `qdrant` passes its healthcheck

**Given** the deployment
**When** verified
**Then** the setup steps are documented in a runbook update to `docs/runbook.md`

### Story 4.2: Real Platform Integration Verification

As a simulation operator,
I want all real platform adapters verified working against live APIs,
So that agents can post, email, and interact with real services during the live simulation.

**Acceptance Criteria:**

**Given** Slack credentials (`ENTWINE_SLACK_BOT_TOKEN`) configured
**When** `SlackLiveAdapter.send("post_message", {...})` is called
**Then** a message appears in the configured Slack channel

**Given** GitHub credentials (`ENTWINE_GITHUB_TOKEN`) configured
**When** `GitHubLiveAdapter.send("create_issue", {...})` is called
**Then** an issue is created in the configured test repository

**Given** Gmail credentials configured
**When** `EmailLiveAdapter.send("send_email", {...})` is called
**Then** an email is delivered to the configured test address

**Given** X credentials configured
**When** `XLiveAdapter.send("post_tweet", {...})` is called
**Then** a tweet is posted (use draft/test mode if available to avoid public posts)

**Given** any platform adapter fails credential validation at startup
**When** the factory runs
**Then** it falls back to the stub adapter and logs a `WARNING` — entwine does not crash

**Given** all platform tests
**When** documented
**Then** any platform-specific gotchas or rate limit observations are added to the relevant `docs/platforms/<platform>.md`

### Story 4.3: Monitoring & Alerting

As a simulation operator,
I want lightweight monitoring and alerting for the live deployment,
So that I am notified when the simulation encounters problems without a heavy observability stack.

**Acceptance Criteria:**

**Given** a health check poller (cron job or external uptime monitor)
**When** `GET /health` returns non-200 or times out
**Then** an alert is sent (email or Slack notification)

**Given** the simulation is running
**When** global LLM cost reaches 80% of `global_budget_usd`
**Then** a warning log entry at `WARNING` level is emitted and an alert notification is triggered

**Given** any agent enters `ERROR` state
**When** the supervisor detects it
**Then** a structured log entry at `ERROR` level is emitted and an alert notification is triggered

**Given** Docker log output
**When** the simulation is running
**Then** structured JSON logs are accessible via `docker compose logs -f entwine` and contain `agent_id`, `event_type`, `cost_usd` fields

**Given** the monitoring setup
**When** documented
**Then** alert thresholds, notification channels, and log access instructions are in `docs/runbook.md`

### Story 4.4: First Live Simulation Run & Report

As a simulation operator,
I want to run a complete 1–2 hour live simulation and produce a findings report,
So that I can validate entwine works end-to-end with real platforms and establish a baseline for future runs.

**Acceptance Criteria:**

**Given** the production VM is running with all platform integrations verified
**When** `entwine start --config examples/acme-corp.yaml` is run with 12-agent config
**Then** all agents start successfully and the dashboard shows their status in real time

**Given** the simulation runs for 120–240 ticks (at 30s tick interval = 1–2 hours)
**When** it completes or is stopped
**Then** total cost, event count, and platform action count are visible via `GET /status`

**Given** the simulation run is complete
**When** `docs/reports/first-live-run.md` is written
**Then** it contains: total LLM cost breakdown by agent and tier, event types and counts, platform actions taken, agent behaviour observations, failure modes encountered, performance metrics (tick latency, memory), and tuning recommendations

**Given** the report
**When** reviewed
**Then** it includes at least one screenshot of the dashboard at a key moment during the run
