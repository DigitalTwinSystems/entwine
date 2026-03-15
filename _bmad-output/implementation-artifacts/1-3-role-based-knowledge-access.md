# Story 1.3: Role-Based Knowledge Access

Status: done

## Story

As a simulation operator,
I want agents to only retrieve documents their role is permitted to access,
So that a sales agent cannot read engineering-only documents and the simulation reflects realistic information boundaries.

## Acceptance Criteria

1. **Given** documents ingested with `accessible_roles: [engineering, company-wide]` **When** an agent with `rag_access: [engineering]` queries the knowledge store **Then** those documents are returned

2. **Given** the same documents **When** an agent with `rag_access: [marketing]` queries the knowledge store **Then** the engineering-only documents are NOT returned

3. **Given** a `company-wide` document **When** any agent queries the knowledge store **Then** the document is returned regardless of the agent's department

4. **Given** the role filter is applied **When** it is executed **Then** filtering happens server-side in Qdrant via metadata pre-filter (not post-filter in Python)

## Tasks / Subtasks

- [x] Task 1: Wire agent rag_access to knowledge store search (AC: #1, #2)
  - [x] Update `KnowledgeStore.search()` to accept `agent_roles: list[str]` (with backward-compat `agent_role: str`)
  - [x] Build MatchAny filter across all roles plus "company-wide"
  - [x] Add tests: multi-role filtering, backward compat

- [x] Task 2: Handle company-wide access (AC: #3)
  - [x] "company-wide" automatically included in MatchAny filter for all queries
  - [x] Test: company-wide docs returned to any agent role

- [x] Task 3: Verify server-side filtering (AC: #4)
  - [x] Filter passed as `query_filter` param to Qdrant (server-side, not post-processed)
  - [x] Tests assert filter kwargs passed to mock Qdrant client

- [x] Task 4: Update query_knowledge tool
  - [x] Accept comma-separated roles in `role` param
  - [x] Pass as list to `KnowledgeStore.search(agent_roles=...)`
  - [x] Updated metadata key from `source_file` to `source_path`

- [x] Task 5: Verification
  - [x] 455 tests pass, lint clean, 90% coverage

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Completion Notes List

- `KnowledgeStore.search()` now accepts `agent_roles: list[str] | str` with backward-compat `agent_role: str` kwarg
- "company-wide" is automatically added to the MatchAny filter so company-wide docs are always accessible
- `query_knowledge` tool updated to split comma-separated roles and pass as list
- Fixed `source_file` → `source_path` reference in query_knowledge snippets
- 4 new tests for role-based access (multi-role, company-wide inclusion, backward compat, string auto-wrap)

### File List

- `src/entwine/rag/store.py` (modified — search accepts agent_roles list, company-wide auto-included)
- `src/entwine/tools/builtin.py` (modified — passes roles list, uses source_path)
- `tests/unit/test_rag.py` (modified — TestRoleBasedAccess class with 4 tests)
