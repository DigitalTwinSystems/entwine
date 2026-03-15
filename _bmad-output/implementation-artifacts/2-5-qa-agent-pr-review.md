# Story 2.5: QA Agent PR Review

Status: done

## Story

As a simulation operator,
I want a QA agent that reviews pull requests using read-only GitHub tools,
So that the simulated engineering team has a realistic code review step before merging.

## Acceptance Criteria

1. **Given** the QA agent receives a `PROpened` event
   **When** it processes the event
   **Then** it opens a read-only Claude Agent SDK session with only `Read`, `Glob`, `Grep` tools

2. **Given** the read-only session is active
   **When** the agent reviews the PR diff
   **Then** it analyses code quality, test coverage gaps, and style, then posts review comments via `GitHubLiveAdapter.add_comment()`

3. **Given** the review is complete
   **When** the QA agent decides
   **Then** it either approves the PR or requests changes by publishing a `ReviewComplete` event to the agent bus

4. **Given** no E2B credentials are present
   **When** the QA agent attempts to review
   **Then** it still functions (QA uses read-only tools only; no sandbox required)

## Tasks / Subtasks

- [x]Task 1: Create QAAgent class (AC: #1, #4)
  - [x]Create `src/entwine/agents/qa_agent.py`
  - [x]`QAAgent` subclasses `BaseAgent`
  - [x]Constructor accepts: `platform_adapter` (GitHub), optional `sdk_session_factory`, `event_bus`
  - [x]Override `_call_llm` to use read-only SDK session (Read, Glob, Grep only — no Write, Edit, Bash)
  - [x]No sandbox dependency — QA agent works without E2B

- [x]Task 2: PR review handler (AC: #1, #2)
  - [x]Implement `async handle_pr_opened(event: PROpened)` method
  - [x]Extract PR number, branch, title from event payload
  - [x]Build review prompt including PR context
  - [x]Query SDK session for code review analysis
  - [x]Return review result (approved: bool, comments: list[str])

- [x]Task 3: Post review comments (AC: #2)
  - [x]After review, call `adapter.send("add_comment", {...})` with review findings
  - [x]Format comments as structured review feedback

- [x]Task 4: Publish ReviewComplete event (AC: #3)
  - [x]After posting comments, publish `ReviewComplete` event to event bus
  - [x]Include: pr_number, approved (bool), comments list

- [x]Task 5: Unit tests (AC: #1–#4)
  - [x]Test QAAgent construction without sandbox
  - [x]Test handle_pr_opened processes event correctly
  - [x]Test review comments posted via adapter mock
  - [x]Test ReviewComplete event published
  - [x]Test QA agent works without E2B credentials
  - [x]Test read-only tool restriction (no Write/Edit/Bash in allowed_tools)
  - [x]Verify no regressions

## Dev Notes

### Architecture Compliance

- **BaseAgent**: Subclass from `src/entwine/agents/base.py`. Override `_call_llm` and `_emit_events`.
- **PROpened event**: Created in story 2.4 at `src/entwine/events/models.py`.
- **ReviewComplete event**: Created in story 2.4 at `src/entwine/events/models.py`.
- **GitHubLiveAdapter**: At `src/entwine/platforms/github.py` with `add_comment` action.
- **CoderSDKSession**: At `src/entwine/agents/coder_sdk.py` — can reuse for read-only sessions by restricting `allowed_tools`.
- **EventBus**: Use `await bus.publish(ReviewComplete(...))`.

### Key Design Decision

QA agent does NOT need a sandbox. It uses read-only tools (Read, Glob, Grep) to analyze code. The SDK session can run locally since no Bash/Write/Edit tools are allowed. This means:
- No E2B dependency
- No SandboxManager needed
- Simpler construction
- Always functional regardless of E2B credentials

### Previous Story Learnings (2.1–2.4)

- Conditional import pattern for SDK: `SDK_AVAILABLE` flag
- Duck-type ResultMessage detection via `total_cost_usd` attr
- Event publishing: `await bus.publish(ReviewComplete(source_agent=..., payload={...}))`
- Platform adapter mock: `AsyncMock()` with `.send` returning dict
- `create=True` needed when patching SDK names that don't exist at import time

### Project Structure Notes

- New file: `src/entwine/agents/qa_agent.py`
- Tests: `tests/unit/test_qa_agent.py`

### References

- [Source: src/entwine/agents/base.py] — BaseAgent lifecycle
- [Source: src/entwine/agents/coder_sdk.py] — CoderSDKSession pattern
- [Source: src/entwine/events/models.py] — PROpened, ReviewComplete events
- [Source: src/entwine/platforms/github.py] — GitHubLiveAdapter.add_comment
- [Source: docs/adr/010-agentic-developer-integration.md] — QA agent reads-only

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Created QAAgent subclassing BaseAgent with read-only tool restriction
- No sandbox dependency — works without E2B credentials
- handle_pr_opened: processes PROpened events, builds review prompt, posts comments, publishes ReviewComplete
- Review parsing: detects APPROVED vs CHANGES_REQUESTED, auto-approves on no response
- Posts structured review comments via GitHubLiveAdapter.add_comment
- Publishes ReviewComplete to typed EventBus or fallback asyncio.Queue
- 15 tests covering construction, review flow, comments, events, parsing
- Full suite: 550 passed, 11 skipped, 88% coverage, lint clean

### File List

- src/entwine/agents/qa_agent.py (new)
- tests/unit/test_qa_agent.py (new)
