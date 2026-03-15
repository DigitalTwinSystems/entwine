# Story 2.1: E2B Sandbox Integration

Status: done

## Story

As a simulation operator,
I want coder agents to execute code inside isolated E2B Firecracker microVM sandboxes,
So that AI-generated code never runs on the host machine and the simulation is safe to operate.

## Acceptance Criteria

1. **Given** `e2b` is added as optional dep (`entwine[coder]`) in `pyproject.toml`
   **When** E2B credentials are absent
   **Then** the coder subsystem is disabled gracefully and the rest of entwine starts normally

2. **Given** a `SandboxManager` is instantiated with a task
   **When** `create_sandbox()` is called
   **Then** an E2B Firecracker microVM is provisioned with Python 3.12, git, and common dev tools

3. **Given** an active sandbox
   **When** `execute_command(cmd)` is called
   **Then** the command runs inside the VM and returns stdout, stderr, and exit code

4. **Given** a sandbox with `max_session_tokens` or timeout reached
   **When** the limit is exceeded
   **Then** the sandbox is destroyed and a `SandboxTimeout` exception is raised

5. **Given** a task completes or fails
   **When** `destroy_sandbox()` is called
   **Then** the VM is torn down and all resources are released; unit tests mock the E2B client

## Tasks / Subtasks

- [x] Task 1: Add `e2b` optional dependency (AC: #1)
  - [x] Add `e2b>=2.15` to `pyproject.toml` under `[project.optional-dependencies]` as `coder = ["e2b>=2.15"]`
  - [x] Run `uv lock` to update lockfile
  - [x] Verify `import entwine` works without `e2b` installed (graceful degradation)

- [x] Task 2: Create `SandboxManager` class (AC: #2, #3, #5)
  - [x] Create `src/entwine/sandbox/__init__.py`
  - [x] Create `src/entwine/sandbox/manager.py` with `SandboxManager` class
  - [x] Implement `create_sandbox()` → wraps `AsyncSandbox.create()` with `timeout` param
  - [x] Implement `execute_command(cmd)` → wraps `sandbox.commands.run(cmd)` returning `CommandResult`
  - [x] Implement `read_file(path)` and `write_file(path, content)` → delegates to `sandbox.files`
  - [x] Implement `destroy_sandbox()` → calls `sandbox.kill()`, clears reference
  - [x] Add context-manager support (`__aenter__` / `__aexit__`)

- [x] Task 3: Create `SandboxTimeout` exception and timeout enforcement (AC: #4)
  - [x] Add `SandboxTimeout` to `src/entwine/sandbox/manager.py`
  - [x] Track cumulative command execution time
  - [x] On timeout exceeded → call `destroy_sandbox()`, raise `SandboxTimeout`
  - [x] Make `timeout` configurable (default 300s, from config or constructor)

- [x] Task 4: Graceful degradation when E2B unavailable (AC: #1)
  - [x] Use conditional import: `try: from e2b import AsyncSandbox` with `E2B_AVAILABLE = True/False`
  - [x] `SandboxManager.__init__` raises clear error if `e2b` not installed when `create_sandbox()` called
  - [x] Add factory function `create_sandbox_manager()` that returns `None` if no E2B API key (`E2B_API_KEY`)
  - [x] Wire into `CoderAgent`: if `SandboxManager` is `None`, agent logs warning and skips sandbox ops

- [x] Task 5: Unit tests (AC: #1–#5)
  - [x] Test `SandboxManager` with mocked `AsyncSandbox` (mock `e2b.AsyncSandbox.create`)
  - [x] Test `execute_command` returns `CommandResult` with stdout/stderr/exit_code
  - [x] Test `read_file` / `write_file` delegation
  - [x] Test `destroy_sandbox` calls `kill()` and clears state
  - [x] Test timeout enforcement triggers `SandboxTimeout`
  - [x] Test graceful import failure when `e2b` not installed
  - [x] Test context manager cleanup
  - [x] Mark integration tests (real E2B) as `@pytest.mark.integration`

- [x] Task 6: Wire `SandboxManager` into `CoderAgent` (AC: #2)
  - [x] Update `CoderAgent.__init__` to accept `SandboxManager` (satisfies existing `SandboxProvider` protocol)
  - [x] Ensure `SandboxManager` implements `SandboxProtocol` / `SandboxProvider` protocols from `coder.py`

## Dev Notes

### Architecture Compliance

- **Existing protocols**: `coder.py` already defines `SandboxProtocol` and `SandboxProvider` protocols. `SandboxManager` MUST implement these — do NOT create duplicate abstractions.
- **Protocol methods**: `SandboxProtocol` requires: `run_command(cmd) -> CommandResult`, `write_file(path, content)`, `read_file(path) -> str`, `kill()`. All async.
- **Factory pattern**: Follow the platform adapter pattern — conditional import, live vs stub, factory function. See `src/entwine/platforms/factory.py` for reference.
- **CommandResult model**: Already exists at `src/entwine/agents/coder_models.py` — reuse it, do NOT create a new one.
- **SandboxSession model**: Already exists at `src/entwine/agents/coder_models.py` — reuse it for tracking.

### E2B SDK Reference (v2.15.x)

```python
from e2b import AsyncSandbox  # NOT e2b_code_interpreter

# Create sandbox (async)
sbx = await AsyncSandbox.create(timeout=300)  # seconds

# Run commands
result = await sbx.commands.run("echo hello")
# result has: result.stdout, result.stderr, result.exit_code

# File ops
await sbx.files.write("/path/file.txt", "content")
content = await sbx.files.read("/path/file.txt")

# Cleanup
await sbx.kill()

# Extend timeout
await sbx.set_timeout(600)
```

- Auth: `E2B_API_KEY` env var (auto-read by SDK) or `api_key=` kwarg
- Use `e2b` package directly, NOT `e2b-code-interpreter` (we need shell access, not Jupyter)
- AsyncSandbox is native asyncio — no thread pool needed
- Known issue: httpx connection leak on rapid sandbox cycling (#1155) — use explicit `kill()`

### Project Structure Notes

- New module: `src/entwine/sandbox/` (new package)
  - `__init__.py` — export `SandboxManager`, `SandboxTimeout`, `create_sandbox_manager`
  - `manager.py` — implementation
- Tests: `tests/unit/test_sandbox.py`
- Follow existing patterns: structlog for logging, Pydantic for config, async-first

### Testing Standards

- 80% coverage minimum
- Mock `AsyncSandbox.create()` in unit tests — never call real E2B in unit tests
- Use `@pytest.mark.integration` for any test that would call real E2B
- Follow existing test patterns in `tests/unit/test_coder_agent.py`
- Test graceful degradation (missing `e2b` package, missing API key)

### Anti-patterns to Avoid

- Do NOT add synchronous wrappers — everything async
- Do NOT import `e2b` at module level — use conditional/lazy imports for optional deps
- Do NOT create a new `CommandResult` model — reuse from `coder_models.py`
- Do NOT add subprocess/Docker fallback — E2B only per ADR-010
- Do NOT store API keys in code — env var only

### References

- [Source: docs/adr/010-agentic-developer-integration.md] — E2B chosen as sandbox provider
- [Source: src/entwine/agents/coder.py] — SandboxProtocol, SandboxProvider protocols
- [Source: src/entwine/agents/coder_models.py] — CommandResult, SandboxSession models
- [Source: src/entwine/platforms/factory.py] — Factory pattern reference
- [Source: docs/design.md#Section 6] — Coder subsystem architecture

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Added `e2b>=2.15` as optional dep under `coder` extra in pyproject.toml
- Created `src/entwine/sandbox/` package with `SandboxManager` wrapping E2B `AsyncSandbox`
- `SandboxManager` implements both `SandboxProtocol` and `SandboxProvider` from `coder.py`
- Reuses `CommandResult` from `coder_models.py` — no duplicate models
- Conditional import pattern: `E2B_AVAILABLE` flag, factory returns `None` when unavailable
- Timeout enforcement via wall-clock tracking with `SandboxTimeout` exception
- Context manager support for automatic cleanup
- 23 unit tests covering all ACs, 94% coverage on sandbox module
- Full suite: 483 passed, 11 skipped, 88% overall coverage
- Lint and format clean

### File List

- pyproject.toml (modified — added `coder` optional dep)
- uv.lock (modified — added e2b and transitive deps)
- src/entwine/sandbox/__init__.py (new)
- src/entwine/sandbox/manager.py (new)
- tests/unit/test_sandbox.py (new)
