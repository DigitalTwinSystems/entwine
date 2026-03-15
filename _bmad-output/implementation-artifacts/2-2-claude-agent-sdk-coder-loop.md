# Story 2.2: Claude Agent SDK Coder Loop

Status: done

## Story

As a simulation operator,
I want coder agents to autonomously implement tasks using the Claude Agent SDK,
So that developer agents produce real code changes through iterative read-write-test cycles.

## Acceptance Criteria

1. **Given** `CoderAgent` subclasses `BaseAgent` and receives a `TaskAssigned` event
   **When** the agent starts work
   **Then** it initiates a Claude Agent SDK session with tools: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`

2. **Given** the SDK session is active
   **When** the agent issues a `Bash` tool call
   **Then** it is intercepted via `PreToolUse` hook and routed to the E2B sandbox (not the host)

3. **Given** the coding loop runs
   **When** it completes
   **Then** token usage and cost are tracked through the existing `CostTracker` per agent

4. **Given** `max_session_tokens` is configured
   **When** the session approaches the limit
   **Then** the session is cleanly terminated and a `SessionBudgetExceeded` event is published

5. **Given** `max_coder_agents` is set (default 2) in simulation config
   **When** more tasks arrive than the concurrency limit
   **Then** excess tasks are queued until a coder slot is free

## Tasks / Subtasks

- [x] Task 1: Add `claude-agent-sdk` optional dependency (AC: #1)
  - [x] Add `claude-agent-sdk>=0.1.48` to `pyproject.toml` under `[project.optional-dependencies]` in `coder` extra (alongside `e2b`)
  - [x] Run `uv lock` to update lockfile
  - [x] Verify `import entwine` works without `claude-agent-sdk` installed

- [x] Task 2: Create SDK session wrapper (AC: #1, #3)
  - [x] Create `src/entwine/agents/coder_sdk.py` with `CoderSDKSession` class
  - [x] Conditional import: `try: from claude_agent_sdk import query, ClaudeAgentOptions` with `SDK_AVAILABLE` flag
  - [x] `CoderSDKSession.__init__` accepts: `sandbox_manager`, `repo_url`, `max_tokens`, `cost_tracker`, `agent_id`
  - [x] `async run(prompt) -> CodingTaskResult`: calls `query()` with `ClaudeAgentOptions`, iterates messages, collects results
  - [x] Extract token usage and cost from ResultMessage (duck-typed via `total_cost_usd` attr)
  - [x] Record cost via `CostTracker.record()` if tracker provided

- [x] Task 3: Implement PreToolUse hook for Bash → E2B routing (AC: #2)
  - [x] Create `_make_bash_sandbox_hook()` factory in `coder_sdk.py`
  - [x] When `tool_name == "Bash"`: execute command via `SandboxManager.run_command()`, deny local execution, return result as `systemMessage`
  - [x] For `Write`/`Edit` tools: route file writes to sandbox via `_make_write_sandbox_hook()`
  - [x] For `Read` tool: route reads to sandbox via `_make_read_sandbox_hook()`
  - [x] Pass hooks via `ClaudeAgentOptions(hooks={"PreToolUse": [HookMatcher(...)]})`

- [x] Task 4: Token budget enforcement and SessionBudgetExceeded event (AC: #4)
  - [x] Add `SessionBudgetExceeded` event type to `src/entwine/events/models.py`
  - [x] Track cumulative tokens during SDK session via ResultMessage usage
  - [x] If `max_session_tokens` exceeded: terminate session cleanly (use `max_budget_usd` in ClaudeAgentOptions as proxy)
  - [x] Publish `SessionBudgetExceeded` event to event bus with agent_id, tokens_used, max_tokens

- [x] Task 5: Coder agent concurrency limiter (AC: #5)
  - [x] Add `max_coder_agents: int = 2` field to `SimulationConfig` in `src/entwine/config/models.py`
  - [x] Create `CoderSemaphore` class (wraps `asyncio.Semaphore`) in `src/entwine/agents/coder_sdk.py`
  - [x] `CoderAgent._call_llm` must acquire semaphore before starting SDK session, release on completion
  - [x] Queued tasks wait on semaphore — no polling loop

- [x] Task 6: Refactor CoderAgent to use CoderSDKSession (AC: #1, #2, #3)
  - [x] Update `CoderAgent.__init__` to accept optional `CoderSDKSession` factory and `CoderSemaphore`
  - [x] Refactor `_call_llm` to use `CoderSDKSession.run()` via `_call_llm_sdk_session()`
  - [x] Maintain backward compat: if no SDK session factory, fall back to existing `AgentSDKFactory` protocol
  - [x] Update `_handle_task_assigned` to use new session flow

- [x] Task 7: Unit tests (AC: #1–#5)
  - [x] Test `CoderSDKSession` with mocked `query()` — verify message iteration, result extraction
  - [x] Test Bash hook intercepts commands and routes to sandbox mock
  - [x] Test file tool hooks route to sandbox (read + write)
  - [x] Test token tracking from ResultMessage
  - [x] Test cost recording via `CostTracker`
  - [x] Test `SessionBudgetExceeded` event model
  - [x] Test concurrency limiter queues excess tasks
  - [x] Test graceful degradation when `claude-agent-sdk` not installed
  - [x] Verify no regressions: 502 passed, 11 skipped

## Dev Notes

### Architecture Compliance

- **Existing CoderAgent**: `src/entwine/agents/coder.py` already has the agent class with `SandboxProtocol`, `SandboxProvider`, and `AgentSDKSession`/`AgentSDKFactory` protocols. The new `CoderSDKSession` replaces the generic `AgentSDKFactory` with a concrete Claude Agent SDK wrapper.
- **SandboxManager**: Created in story 2.1 at `src/entwine/sandbox/manager.py`. Implements `SandboxProtocol`. Use it for all sandbox operations.
- **CostTracker**: Exists at `src/entwine/observability/cost_tracker.py`. Call `tracker.record(agent_id, cost_usd, input_tokens, output_tokens)`.
- **EventBus**: Use typed `EventBus.publish()` for `SessionBudgetExceeded`. Event types live in `src/entwine/events/models.py`.
- **CodingTaskResult**: Exists at `src/entwine/agents/coder_models.py` — reuse it.

### Claude Agent SDK Reference (v0.1.48)

```python
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, HookMatcher

# One-shot query with tools
async for message in query(
    prompt="Implement the feature",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
        cwd="/path/to/repo",
        system_prompt="You are an expert developer",
        max_turns=20,
        max_budget_usd=1.0,
        hooks={
            "PreToolUse": [
                HookMatcher(matcher="Bash", hooks=[bash_hook]),
            ],
        },
    ),
):
    if isinstance(message, ResultMessage):
        cost = message.total_cost_usd
        tokens = message.usage  # {input_tokens, output_tokens, ...}
```

**PreToolUse hook signature:**
```python
async def bash_hook(input_data, tool_use_id, context):
    # input_data["tool_name"], input_data["tool_input"]["command"]
    # Return deny + systemMessage to intercept:
    return {
        "systemMessage": f"Output:\n{result}",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Routed to E2B sandbox",
        },
    }
```

- Package: `claude-agent-sdk` (NOT `anthropic`)
- Fully async (`asyncio`)
- `query()` returns `AsyncIterator[Message]`
- `ResultMessage` has `total_cost_usd`, `usage`, `session_id`, `num_turns`

### Previous Story (2.1) Learnings

- E2B is optional dep — use conditional import pattern with `*_AVAILABLE` flag
- `SandboxManager` at `src/entwine/sandbox/manager.py` implements `SandboxProtocol` and `SandboxProvider`
- Must patch `E2B_AVAILABLE`/`SDK_AVAILABLE` in tests alongside mocking the SDK classes
- Factory pattern: return `None` when credentials missing

### Project Structure Notes

- New file: `src/entwine/agents/coder_sdk.py` — SDK session wrapper and hooks
- Modified: `src/entwine/agents/coder.py` — refactor to use new session
- Modified: `src/entwine/events/models.py` — add `SessionBudgetExceeded`
- Modified: `src/entwine/config/models.py` — add `max_coder_agents`
- Tests: `tests/unit/test_coder_sdk.py`

### Testing Standards

- Mock `claude_agent_sdk.query()` — never call real SDK in unit tests
- Use `_patch_sdk()` helper similar to `_patch_e2b()` from story 2.1
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed
- 80% coverage minimum

### Anti-patterns to Avoid

- Do NOT import `claude_agent_sdk` at module level — conditional import only
- Do NOT bypass `CostTracker` — all costs must be recorded
- Do NOT use `asyncio.run()` inside async code
- Do NOT create new event bus patterns — use existing `EventBus.publish()`
- Do NOT use polling for concurrency — use `asyncio.Semaphore`

### References

- [Source: docs/adr/010-agentic-developer-integration.md] — Claude Agent SDK chosen
- [Source: src/entwine/agents/coder.py] — Existing CoderAgent with protocols
- [Source: src/entwine/sandbox/manager.py] — SandboxManager (story 2.1)
- [Source: src/entwine/observability/cost_tracker.py] — CostTracker
- [Source: src/entwine/events/models.py] — Event type definitions
- [Source: docs/design.md#Section 6] — Coder subsystem architecture

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Added `claude-agent-sdk>=0.1.48` to `coder` optional deps in pyproject.toml
- Created `CoderSDKSession` in `src/entwine/agents/coder_sdk.py` wrapping Claude Agent SDK `query()`
- Implemented PreToolUse hooks: `_make_bash_sandbox_hook`, `_make_write_sandbox_hook`, `_make_read_sandbox_hook` — all route to E2B sandbox
- Added `SessionBudgetExceeded` event type to `events/models.py`
- Added `max_coder_agents` field to `SimulationConfig` (default 2)
- Created `CoderSemaphore` using `asyncio.Semaphore` for concurrency limiting
- Refactored `CoderAgent._call_llm` to prefer new `CoderSDKSession` over legacy `AgentSDKFactory`, with backward compat
- Duck-typed ResultMessage detection (via `total_cost_usd` attr) to avoid import issues when SDK not installed
- 19 new tests in `test_coder_sdk.py`, all passing
- Full suite: 502 passed, 11 skipped, 88% coverage, lint clean

### File List

- pyproject.toml (modified — added claude-agent-sdk to coder extra)
- src/entwine/agents/coder_sdk.py (new)
- src/entwine/agents/coder.py (modified — added sdk_session_factory, coder_semaphore, _call_llm_sdk_session)
- src/entwine/events/models.py (modified — added SessionBudgetExceeded)
- src/entwine/config/models.py (modified — added max_coder_agents)
- tests/unit/test_coder_sdk.py (new)
