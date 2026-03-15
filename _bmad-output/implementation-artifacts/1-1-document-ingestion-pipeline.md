# Story 1.1: Document Ingestion Pipeline

Status: done

## Story

As a simulation operator,
I want a CLI command that ingests documents from a directory into the Qdrant knowledge base,
So that I can populate the simulation with real company knowledge without writing code.

## Acceptance Criteria

1. **Given** a directory containing `.md`, `.txt`, `.pdf`, or `.docx` files **When** I run `entwine ingest --source <dir> --config <config.yaml>` **Then** all documents are chunked (configurable size + overlap), embedded via `text-embedding-3-small`, and upserted into the `enterprise_knowledge` Qdrant collection

2. **Given** a document is ingested **When** stored in Qdrant **Then** each chunk has metadata: `department`, `sensitivity`, `accessible_roles`, `source_path`, `content_hash`

3. **Given** I run ingest twice on the same file **When** the content has not changed **Then** existing chunks are not re-embedded (idempotent via content hash dedup)

4. **Given** a large directory **When** ingestion runs **Then** progress is reported per-file to stdout and the command exits non-zero on failure

## Tasks / Subtasks

- [x] Task 1: Add PDF/DOCX file support (AC: #1)
  - [x] Add `pypdf>=5.0` and `python-docx>=1.1` as optional deps (`entwine[ingest]`) via `uv add --optional ingest pypdf "python-docx>=1.1"`
  - [x] Extend `_TEXT_EXTENSIONS` in `src/entwine/rag/loaders.py` to include `.pdf`, `.docx`
  - [x] Add `_load_pdf(path: Path) -> str` function using `pypdf.PdfReader`
  - [x] Add `_load_docx(path: Path) -> str` function using `docx.Document`
  - [x] Update `load_file()` to dispatch to new loaders by extension; keep YAML frontmatter extraction for `.md`/`.txt` only
  - [x] For PDF/DOCX: derive metadata from filename convention or pass defaults (no frontmatter in binary formats)
  - [x] Add unit tests mocking file I/O for PDF/DOCX loading

- [x] Task 2: Fix metadata fields (AC: #2)
  - [x] In `loaders.py`: change `source_file` key to `source_path` storing relative path (relative to ingestion root), not just filename
  - [x] In `pipeline.py`: pass root dir to `load_file()` so relative path can be computed
  - [x] Ensure `sensitivity` from frontmatter is always included in metadata (default: `"internal"`)
  - [x] Ensure `content_hash` is stored in chunk metadata (currently used only for ID generation in `chunking.py`)
  - [x] Update `chunks_to_documents()` or `pipeline.py` to add `content_hash` field to each chunk's metadata dict
  - [x] Update existing tests to reflect new metadata keys

- [x] Task 3: Idempotent ingestion via content hash (AC: #3)
  - [x] Before upserting, query Qdrant for existing points with matching IDs (content-hash-based)
  - [x] Skip upsert for chunks whose IDs already exist in the collection
  - [x] Log skipped chunks count per file
  - [x] Add unit tests: ingest same file twice → second run upserts zero new chunks

- [x] Task 4: CLI enhancements (AC: #1, #4)
  - [x] Add `--config` option to `ingest` command in `src/entwine/cli/main.py`
  - [x] Rename existing `directory` param to `source` to match `--source` from AC
  - [x] Add per-file progress output to stdout (file name, chunk count, status)
  - [x] Exit non-zero on any unrecoverable error via `sys.exit(1)`
  - [x] Add `--default-roles` option (comma-separated) for files without frontmatter

- [x] Task 5: Integration verification
  - [x] Run `uv run ruff check src/ tests/` — zero errors
  - [x] Run `uv run ruff format --check src/ tests/` — zero reformats
  - [x] Run `uv run pytest tests/ -q` — all green (451 passed, 6 skipped)
  - [x] Verify coverage ≥80% (90%)

## Dev Notes

### Existing Implementation (M9 — DO NOT REINVENT)

The RAG subsystem is already substantially implemented. **Extend, do not replace.**

| Component | File | Status |
|-----------|------|--------|
| File scanning + frontmatter | `src/entwine/rag/loaders.py` | Complete — extend for PDF/DOCX |
| Text chunking + content hash | `src/entwine/rag/chunking.py` | Complete — no changes needed |
| Embedding service | `src/entwine/rag/embeddings.py` | Complete — no changes needed |
| Qdrant store (upsert, search, hybrid) | `src/entwine/rag/store.py` | Complete — may need scroll/query for dedup |
| Pipeline orchestrator | `src/entwine/rag/pipeline.py` | Complete — extend for metadata/dedup/progress |
| RAG settings | `src/entwine/rag/settings.py` | Complete — no changes needed |
| Data models | `src/entwine/rag/models.py` | Complete — no changes needed |
| CLI ingest command | `src/entwine/cli/main.py` | Exists — enhance params |
| Tests | `tests/unit/test_rag*.py` | 50+ tests — extend, don't break |

### References

- [Source: src/entwine/rag/loaders.py] — file loading, frontmatter extraction
- [Source: src/entwine/rag/chunking.py] — `chunk_text()`, `content_hash()`, `chunks_to_documents()`
- [Source: src/entwine/rag/pipeline.py] — `ingest_directory()` orchestrator
- [Source: src/entwine/cli/main.py] — `ingest` CLI command
- [Source: src/entwine/rag/store.py] — `KnowledgeStore.upsert()`, `get_existing_ids()`
- [Source: docs/adr/003-rag-approaches-and-knowledge-management.md] — architecture decisions

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Extended `loaders.py` with `_load_pdf()` and `_load_docx()` functions using pypdf and python-docx
- Added `_ALL_EXTENSIONS` combining text, PDF, and DOCX extensions; `scan_directory()` now finds all
- Changed `source_file` metadata key to `source_path` with relative path support via `root` parameter
- Added default `sensitivity: "internal"` when not present in frontmatter
- `chunks_to_documents()` now stores `content_hash` in each chunk's metadata dict
- Added `KnowledgeStore.get_existing_ids()` for dedup; pipeline skips already-ingested chunks
- CLI `ingest` command: renamed param to `source`, added `--config`, `--default-roles`, per-file progress output
- Added `_mock_store()` helper for test consistency across pipeline tests
- All 451 tests pass, 90% coverage, zero lint/format issues

### File List

- `src/entwine/rag/loaders.py` (modified — PDF/DOCX support, source_path, sensitivity default)
- `src/entwine/rag/chunking.py` (modified — content_hash in metadata)
- `src/entwine/rag/pipeline.py` (modified — dedup, progress callback, root passthrough)
- `src/entwine/rag/store.py` (modified — get_existing_ids method)
- `src/entwine/cli/main.py` (modified — ingest command params)
- `tests/unit/test_rag_ingestion.py` (modified — new tests, updated metadata assertions)
- `tests/unit/test_rag.py` (modified — get_existing_ids tests)
- `pyproject.toml` (modified — ingest optional deps)
- `uv.lock` (modified — new deps)
