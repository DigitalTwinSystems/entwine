# Story 1.2: Sample Company Knowledge Base

Status: done

## Story

As a simulation operator,
I want a ready-to-use sample knowledge base for Acme Corp included in the repository,
So that I can run a realistic simulation immediately without creating documents myself.

## Acceptance Criteria

1. **Given** the repository is cloned **When** I look in `examples/knowledge/` **Then** I find at least 7 documents covering: `company-handbook.md` (company-wide), `engineering-standards.md` (engineering), `marketing-playbook.md` (marketing), `sales-process.md` (sales), `support-runbook.md` (support), `product-roadmap.md` (executive), `onboarding-guide.md` (company-wide)

2. **Given** each sample document **When** it is read **Then** it is 500–1000 words of plausible, internally-consistent Acme Corp content with correct `department` and `accessible_roles` front-matter or metadata

3. **Given** the sample knowledge base **When** I run `entwine ingest --source examples/knowledge/` **Then** all 7 documents ingest without error

## Tasks / Subtasks

- [x] Task 1: Rename existing files to match AC names (AC: #1)
  - [x] Rename `engineering-playbook.md` → `engineering-standards.md`
  - [x] Rename `marketing-content-calendar.md` → `marketing-playbook.md`
  - [x] Rename `sales-playbook.md` → `sales-process.md`
  - [x] Rename `product-roadmap-q2.md` → `product-roadmap.md`

- [x] Task 2: Expand all documents to 500-1000 words (AC: #2)
  - [x] `company-handbook.md`: 579 words
  - [x] `engineering-standards.md`: 595 words
  - [x] `marketing-playbook.md`: 551 words
  - [x] `sales-process.md`: 609 words
  - [x] `support-runbook.md`: 651 words
  - [x] `product-roadmap.md`: 666 words
  - [x] `onboarding-guide.md`: 773 words
  - [x] All content is plausible Acme Corp material, internally consistent

- [x] Task 3: Verify frontmatter and ingestion (AC: #2, #3)
  - [x] Each doc has correct `department` and `accessible_roles` frontmatter
  - [x] Ingestion test passes (test_sample_knowledge_base)

- [x] Task 4: Verification
  - [x] Run `uv run pytest tests/ -q` — all green (451 passed)
  - [x] Word counts verified: all 7 docs in 500-1000 range

## Dev Notes

### Previous Story Intelligence

Story 1.1 added PDF/DOCX support, source_path metadata, sensitivity defaults, and content-hash dedup.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Completion Notes List

- Renamed 4 files to match exact AC names (engineering-playbook→standards, marketing-content-calendar→playbook, sales-playbook→process, product-roadmap-q2→roadmap)
- Expanded all 7 documents from ~250 words to 500-773 words with consistent Acme Corp content
- All documents have proper YAML frontmatter (department, accessible_roles, sensitivity)
- Cross-references updated (onboarding guide references new filenames)
- All 451 tests pass, sample knowledge base ingestion test succeeds

### File List

- `examples/knowledge/company-handbook.md` (expanded to 579 words)
- `examples/knowledge/engineering-standards.md` (renamed + expanded to 595 words)
- `examples/knowledge/marketing-playbook.md` (renamed + expanded to 551 words)
- `examples/knowledge/sales-process.md` (renamed + expanded to 609 words)
- `examples/knowledge/support-runbook.md` (expanded to 651 words)
- `examples/knowledge/product-roadmap.md` (renamed + expanded to 666 words)
- `examples/knowledge/onboarding-guide.md` (expanded to 773 words)
