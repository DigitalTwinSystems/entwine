# ADR-010: Agentic Developer Integration for Coder Roles

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#10](https://github.com/DigitalTwinSystems/entsim/issues/10)

## Context

entsim simulates SME operations using ~12 concurrent LLM agents. Issue #10 asks whether those agents can include software developers ("coders") and, if so, how to make their work realistic by integrating with agentic coding tools.

Existing decisions constrain the solution space:
- **ADR-001:** Python 3.12+, asyncio, FastAPI
- **ADR-002:** LiteLLM Router, Anthropic primary (Claude Haiku/Sonnet/Opus tiers)
- **ADR-003:** Qdrant shared knowledge base, role-based metadata filtering
- **ADR-004:** Config-as-code (TOML/YAML) + HTMX monitoring dashboard

A coder agent must be able to write code, run tests, commit to git, and participate in review workflows — all autonomously and safely, without threatening host-machine integrity.

## Decision

**Yes, entsim supports coder agent roles.** The integration model is:

1. **Primary tool:** Claude Agent SDK (`claude-agent-sdk`) — wraps the coder agent's work loop natively in Python/asyncio.
2. **Sandboxed execution:** E2B microVM sandboxes for `Bash` tool calls that execute untrusted code.
3. **Real Git repositories**, accessed inside the sandbox, for authentic commit/PR workflows.
4. **Cross-role communication** via the existing entsim agent bus — a product-manager agent assigns tasks; a QA agent reviews output.

| Concern | Choice |
|---------|--------|
| Coding tool / agent loop | [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview) (`pip install claude-agent-sdk`) |
| Code-execution sandbox | [E2B](https://e2b.dev/) microVM (`pip install e2b`) |
| Repository model | Real Git repo, cloned inside E2B sandbox |
| CI/CD interaction | Simulated: coder agent pushes branch; entsim stub returns fake CI result |
| Code review workflow | PR description posted to entsim agent bus; QA/peer agent reviews via read-only tools |
| LLM tier for coder | Tier 2 (Claude Sonnet 4.6) by default; Tier 3 (Opus 4.6) for complex planning |

## Rationale

### Agentic coding tool landscape (early 2026)

| Tool | Integration model | Sandboxing | Python-native | Notes |
|------|------------------|------------|--------------|-------|
| **Claude Agent SDK** | Python/TS library (`query()` async generator) | Delegated to host or E2B | Yes (asyncio) | Same engine as Claude Code CLI; built-in Read/Write/Edit/Bash/Glob/Grep/WebSearch tools; hooks, subagents, sessions, MCP |
| **Aider** | CLI subprocess or unstable Python API (`Coder.create()`) | None (runs on host) | Unofficial API | `--message` flag enables non-interactive use; API explicitly unsupported/may break |
| **OpenHands** | REST API + Python SDK | Docker container per session (MIT core) | Yes | 77.6% SWE-bench Verified; enterprise edition for Kubernetes; heavier infra footprint |
| **OpenAI Codex CLI** | CLI subprocess | macOS Sandbox / network-off mode | No (npm) | Tight ChatGPT/OpenAI coupling; non-interactive mode limited |
| **AutoGen / AG2** | Python library | Pluggable (Docker executor, local) | Yes | Good multi-agent orchestration; code execution via `DockerCommandLineCodeExecutor` |
| **SWE-agent** | Python CLI / library | Docker | Yes | Research-grade; best for benchmark tasks, less suited to production embedding |

**Why Claude Agent SDK wins:**

- Fits the existing asyncio architecture with zero friction — `async for message in query(...)` drops directly into entsim's agent coroutines.
- Built-in tool set covers everything a coder needs: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, plus `WebSearch`/`WebFetch` for researching APIs.
- `ClaudeAgentOptions(allowed_tools=[...])` gives fine-grained tool gating — trivial to deny `Bash` in production or restrict to read-only for code-review agents.
- Hooks (`PreToolUse`, `PostToolUse`) enable audit logging of every file change and command.
- Subagents: the coder can spawn a specialized `code-reviewer` subagent with read-only tools for self-review before posting a PR.
- Session continuity (`resume=session_id`) lets a coder agent pause, hand off to QA, and resume with full context.
- Already on Anthropic — consistent with ADR-002 (primary provider), unified billing, same rate-limit headroom.
- SWE-bench Verified: Claude 4.5 Opus reaches ~76.8% resolution rate (top of leaderboard as of February 2026).

**Why not OpenHands:** Requires a sidecar Docker daemon per session. At 12 simulated employees, that is 1–3 coder agents sharing E2B sandboxes, not 12 Docker daemons. OpenHands is the fallback if we ever need its richer browser/GUI interaction.

**Why not Aider:** Its Python API is explicitly unsupported and offers no stability guarantees. CLI subprocess integration is fragile for a long-running asyncio simulation.

### Sandboxing approach

Coder agents execute untrusted AI-generated code. Running `Bash` on the host is unacceptable.

| Approach | Isolation | Startup | Python SDK | Cost |
|----------|-----------|---------|------------|------|
| **E2B microVM** | Firecracker-based VM | ~150 ms | Yes (`e2b`) | Pay-per-second |
| Docker container | Namespace + cgroups | ~500 ms–2 s | Via `docker-py` | Self-hosted infra cost |
| gVisor | Syscall interception | ~300 ms | Via Docker | Self-hosted |
| Firecracker (self-hosted) | VM | ~150 ms | Manual wiring | Ops overhead |
| Host (no sandbox) | None | 0 ms | N/A | Free but dangerous |

**E2B** is chosen because:
- Firecracker microVMs provide true VM-level isolation (separate kernel) at near-container startup speed.
- `pip install e2b` integrates cleanly into the Python async agent loop.
- Pay-per-second pricing scales to our workload: 1–3 coder agents running intermittent tasks, not continuously.
- No daemon to manage — E2B's cloud handles the sandbox fleet.
- Each coder agent session gets its own sandbox; sandboxes are discarded after the task.

The Claude Agent SDK's `Bash` tool is pointed at the E2B sandbox via a custom hook that intercepts `Bash` calls and executes them inside the sandbox instead of locally.

```python
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher
from e2b import Sandbox

async def bash_via_e2b(input_data, tool_use_id, context):
    cmd = input_data["tool_input"]["command"]
    with Sandbox() as sbx:
        result = sbx.commands.run(cmd)
    return {"output": result.stdout, "error": result.stderr}

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[bash_via_e2b])
        ]
    },
)
```

### Repository model

- A real Git repository (private GitHub repo per simulated enterprise) is cloned into the E2B sandbox at session start.
- The coder agent pushes branches and opens PRs through the GitHub API (or `gh` CLI inside the sandbox).
- This produces authentic git history, real diffs, and reviewable PRs — observable by QA/peer agents.
- CI/CD is simulated: entsim runs a stub that responds to webhook events with synthetic pass/fail results, avoiding the cost and complexity of real CI pipelines.

### Cross-role collaboration

| Workflow | Implementation |
|----------|---------------|
| PM assigns task | PM agent posts a `TaskAssigned` event to the entsim agent bus; coder agent subscribes and initiates an Agent SDK session |
| Coder opens PR | Coder agent calls GitHub API from inside sandbox; posts `PROpened` event to bus with PR URL |
| QA reviews | QA agent runs a read-only Claude Agent SDK session (`allowed_tools=["Read","Glob","Grep"]`) against the diff |
| Code review by peer | Second coder agent spawned as subagent with read-only tools; posts review comments to GitHub |
| CI result | entsim stub posts `CIResult` event; coder agent may resume session to fix failures |

All events flow through the existing asyncio event bus — no new IPC mechanism required.

### LLM cost implications

Coder agents are expensive: each coding task involves many tool calls over potentially minutes-long sessions, consuming far more tokens than a social-media or email agent.

| Agent type | Typical session tokens | LLM tier |
|------------|----------------------|----------|
| Social/email agent | 2K–10K | Haiku 4.5 (Tier 1) |
| Coder agent (routine task) | 20K–100K | Sonnet 4.6 (Tier 2) |
| Coder agent (complex feature) | 100K–500K+ | Opus 4.6 (Tier 3) for planning; Sonnet for execution |

Mitigations:
- Limit coder agents to 1–2 concurrent sessions (config parameter `max_coder_agents`).
- Use prompt caching on the shared system prompt (repo context, coding standards) — ADR-002's 60% cache hit rate applies here.
- Gate coder activation behind simulation config; default simulations omit coder roles.
- Set a per-session token budget via hook; abort and surface a `BudgetExceeded` event if exceeded.

### Security model

| Risk | Mitigation |
|------|-----------|
| AI-generated code escapes sandbox | E2B Firecracker VM; no shared kernel with host |
| Sandbox exfiltrates secrets | E2B sandbox has no access to host env vars; secrets injected explicitly and scoped |
| Coder agent commits malicious code | Simulated repo is isolated; real org repos are never connected |
| Runaway sandbox costs | E2B session timeout (configurable); entsim kills sandbox after task deadline |
| Prompt injection via repo content | `Bash` restricted to sandbox; `allowed_tools` excludes network tools by default |

### Configuration

```yaml
# entsim org config (YAML, per ADR-004)
roles:
  - id: coder_alice
    type: coder
    persona: "Senior backend engineer, Python specialist"
    llm_tier: standard          # sonnet-4-6
    sandbox: e2b
    repo: git@github.com:acme/backend.git
    max_session_tokens: 200000
    ci_stub: true               # use simulated CI
```

## Consequences

### Positive

- Coder agents are realistic: real git commits, real PRs, real code diffs reviewable by other agents.
- Claude Agent SDK integrates with zero new async primitives — same `asyncio` coroutine model as all other agents.
- E2B eliminates host-machine risk while keeping setup simple (one `pip install`, no Docker daemon).
- Cross-role workflows (PM → coder → QA) compose cleanly over the existing event bus.
- Prompt caching on repo context yields meaningful cost savings for multi-turn coding sessions.

### Negative

- Coder agents are 10–50x more expensive per session than social/email agents — must be explicitly enabled.
- E2B is a SaaS dependency; offline/air-gapped operation requires switching to self-hosted Firecracker or Docker.
- Each session clones a git repo into a fresh sandbox — adds latency (~5–30 s depending on repo size) and E2B compute cost.
- Claude Agent SDK is Anthropic-specific; switching LLM providers for coder agents requires evaluating alternative agent loops (OpenHands REST API is the nearest drop-in).
- Simulated CI/CD is not a substitute for real CI; entsim will not catch actual build breakage in the simulated codebase.

### Future options

- **Real CI:** Replace the CI stub with a GitHub Actions workflow in the simulated repo — adds authenticity at the cost of pipeline minutes.
- **OpenHands fallback:** If GUI/browser interaction is needed (e.g., filling web-based issue trackers), OpenHands can be spawned as a sidecar via its REST API.
- **Self-hosted sandboxes:** Replace E2B with self-hosted Firecracker (using [Kata Containers](https://katacontainers.io/) or [Flintlock](https://github.com/weaveworks-liquidmetal/flintlock)) if cost or data-residency requirements demand it.
- **Multi-repo teams:** Config allows multiple coder agents sharing one repo to simulate a real engineering team with parallel branches.
