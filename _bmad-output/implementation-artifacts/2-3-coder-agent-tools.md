# Story 2.3: Coder Agent Tools

Status: done

## Story

As a coder agent,
I want file I/O, shell execution, and git tools routed through my sandbox,
So that I can read, write, and commit code safely without accessing the host filesystem.

## Acceptance Criteria

1. **Given** the following tools are registered in `ToolDispatcher` for coder agents: `read_file`, `write_file`, `run_command`, `search_code`, `git_commit`, `git_push`
   **When** any tool is called
   **Then** it delegates to `SandboxManager` with configurable timeout and output size limits

2. **Given** `git_commit` is called with a message
   **When** it executes
   **Then** staged changes are committed inside the sandbox repo with the given message

3. **Given** `git_push` is called
   **When** it executes
   **Then** the branch is pushed to the remote GitHub repository via the sandbox's git credentials

4. **Given** a `run_command` call produces output exceeding the size limit
   **When** the limit is hit
   **Then** output is truncated and a warning is included in the tool result

## Tasks / Subtasks

- [x] Task 1: Create coder tool functions (AC: #1, #2, #3)
  - [x] Create `src/entwine/tools/coder_tools.py`
  - [x] Implement `async read_file(path: str) -> str` — delegates to `SandboxManager.read_file()`
  - [x] Implement `async write_file(path: str, content: str) -> str` — delegates to `SandboxManager.write_file()`
  - [x] Implement `async run_command(command: str) -> str` — delegates to `SandboxManager.run_command()`
  - [x] Implement `async search_code(pattern: str, path: str = ".") -> str` — runs `grep -rn` via sandbox
  - [x] Implement `async git_commit(message: str) -> str` — runs `git add -A && git commit -m` via sandbox
  - [x] Implement `async git_push(branch: str = "") -> str` — runs `git push` via sandbox

- [x] Task 2: Output truncation (AC: #4)
  - [x] Add `max_output_size: int = 10_000` configurable constant (chars)
  - [x] `run_command` truncates stdout+stderr if combined exceeds limit
  - [x] Append `[output truncated: {total} chars, showing first {max_output_size}]` warning

- [x] Task 3: Tool registration function (AC: #1)
  - [x] Create `register_coder_tools(dispatcher: ToolDispatcher, sandbox: SandboxManager)` function
  - [x] Register all 6 tools with proper name, description, and parameter schemas
  - [x] Use closure to capture `sandbox` reference — tools are stateful (bound to a sandbox instance)

- [x] Task 4: Unit tests (AC: #1–#4)
  - [x] Test each tool function with mocked `SandboxManager`
  - [x] Test `read_file` returns file content
  - [x] Test `write_file` delegates and returns confirmation
  - [x] Test `run_command` returns stdout, handles nonzero exit
  - [x] Test `search_code` runs grep and returns results
  - [x] Test `git_commit` runs correct git commands
  - [x] Test `git_push` runs correct git commands
  - [x] Test output truncation at limit boundary
  - [x] Test `register_coder_tools` registers all 6 tools in dispatcher
  - [x] Verify full test suite: 521 passed, 11 skipped, 88% coverage

## Dev Notes

### Architecture Compliance

- **ToolDispatcher**: Already exists at `src/entwine/tools/dispatcher.py`. Register tools using `dispatcher.register(name, handler, description, parameters)`.
- **ToolCall/ToolResult**: Models at `src/entwine/tools/models.py`. Tools are plain async functions that return strings.
- **SandboxManager**: Created in story 2.1 at `src/entwine/sandbox/manager.py`. Use `run_command()`, `read_file()`, `write_file()`.
- **CommandResult**: From `src/entwine/agents/coder_models.py` — `stdout`, `stderr`, `exit_code`.
- **Existing builtin tools**: Pattern in `src/entwine/tools/builtin.py` — async functions returning strings, registered by name.

### Tool Specifications

| Tool | Parameters | Sandbox Command |
|------|-----------|-----------------|
| `read_file` | `path: str` | `sandbox.read_file(path)` |
| `write_file` | `path: str, content: str` | `sandbox.write_file(path, content)` |
| `run_command` | `command: str` | `sandbox.run_command(command)` |
| `search_code` | `pattern: str, path: str = "."` | `sandbox.run_command(f"grep -rn {pattern} {path}")` |
| `git_commit` | `message: str` | `sandbox.run_command("git add -A && git commit -m ...")` |
| `git_push` | `branch: str = ""` | `sandbox.run_command("git push origin {branch}")` |

### Previous Story Learnings (2.1, 2.2)

- `SandboxManager` methods are all async, return `CommandResult` for commands
- Use conditional import pattern for optional deps, but sandbox tools don't need it — they take a `SandboxManager` instance at registration time
- Test with mocked `SandboxManager` (use `AsyncMock` for its methods)
- `CommandResult` has `.stdout`, `.stderr`, `.exit_code`

### Project Structure Notes

- New file: `src/entwine/tools/coder_tools.py`
- Tests: `tests/unit/test_coder_tools.py`

### Anti-patterns to Avoid

- Do NOT shell-escape by hand — use shlex.quote for git commit messages
- Do NOT import SandboxManager at module level if it requires e2b
- Do NOT create new ToolResult models — tools return plain strings

### References

- [Source: src/entwine/tools/dispatcher.py] — ToolDispatcher registration
- [Source: src/entwine/tools/builtin.py] — Existing tool patterns
- [Source: src/entwine/tools/models.py] — ToolCall, ToolResult models
- [Source: src/entwine/sandbox/manager.py] — SandboxManager API
- [Source: src/entwine/agents/coder_models.py] — CommandResult

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Created 6 sandbox-routed coder tools: read_file, write_file, run_command, search_code, git_commit, git_push
- All tools use closure pattern to capture SandboxManager instance
- Output truncation at MAX_OUTPUT_SIZE (10,000 chars) with warning
- shlex.quote used for safe shell escaping of git commit messages and grep patterns
- register_coder_tools() registers all 6 with full OpenAI function-calling parameter schemas
- 19 tests covering all tools, error handling, truncation, and registration
- Full suite: 521 passed, 11 skipped, 88% coverage, lint clean

### File List

- src/entwine/tools/coder_tools.py (new)
- tests/unit/test_coder_tools.py (new)
