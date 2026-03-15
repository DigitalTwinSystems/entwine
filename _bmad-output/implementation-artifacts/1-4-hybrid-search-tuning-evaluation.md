# Story 1.4: Hybrid Search Tuning & Evaluation

Status: done

## Story

As a simulation operator,
I want hybrid search (dense + sparse + RRF) enabled and its quality measurable,
So that agents retrieve the most relevant knowledge chunks and I can tune retrieval before running a long simulation.

## Acceptance Criteria

1. **Given** the Qdrant collection is configured **When** initialised **Then** it has both dense vectors (1536d, `text-embedding-3-small`) and sparse vectors (BM25/SPLADE) enabled

2. **Given** a query is issued **When** results are retrieved **Then** RRF fusion (k=60 default, configurable) combines dense and sparse rankings

3. **Given** `examples/evaluation/rag_eval_dataset.json` with 20 queries and expected relevant documents **When** I run `entwine evaluate-rag --dataset examples/evaluation/rag_eval_dataset.json` **Then** the command reports precision@5, recall@5, and MRR for dense-only vs hybrid modes

4. **Given** the evaluation results **When** documented **Then** optimal RRF parameters and collection settings are recorded in `docs/configuration.md`

## Tasks / Subtasks

- [x] Task 1: Create evaluation dataset (AC: #3)
  - [x] Created `examples/evaluation/rag_eval_dataset.json` with 20 queries
  - [x] Each query has: query text, relevant doc stems, role

- [x] Task 2: Add evaluate-rag CLI command (AC: #3)
  - [x] Added `evaluate-rag` command to CLI
  - [x] Loads dataset JSON, runs queries in dense-only and hybrid modes
  - [x] Prints metrics table: P@5, R@5, MRR for each mode

- [x] Task 3: Make RRF k configurable (AC: #2)
  - [x] Added `rrf_k` field to `RAGSettings` (default 60)
  - [x] Wired into `KnowledgeStore._rrf_fuse()` via search path
  - [x] Added test for configurable RRF k

- [x] Task 4: Document optimal settings (AC: #4)
  - [x] Added RAG tuning section to `docs/configuration.md` with recommended settings

- [x] Task 5: Verification
  - [x] 456 tests pass, lint clean, 89% coverage

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Completion Notes List

- Created 20-query evaluation dataset covering all 7 Acme Corp KB documents
- Added `evaluate-rag` CLI command comparing dense-only vs hybrid retrieval
- Made RRF k configurable via `RAG_RRF_K` env var (default 60)
- Documented optimal RAG settings in docs/configuration.md
- Added test for custom RRF k value

### File List

- `examples/evaluation/rag_eval_dataset.json` (new — 20 evaluation queries)
- `src/entwine/rag/settings.py` (modified — added rrf_k field)
- `src/entwine/rag/store.py` (modified — configurable RRF k in _rrf_fuse)
- `src/entwine/cli/main.py` (modified — evaluate-rag command)
- `docs/configuration.md` (modified — RAG tuning section)
- `tests/unit/test_rag.py` (modified — custom k test)
