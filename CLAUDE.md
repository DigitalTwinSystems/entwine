# entwine — Claude Code Instructions

Start with short, concrete intro.
Work style: telegraph; noun-phrases ok; drop grammar; min tokens.

## Documentation standards

- All documentation must be succinct. Prefer tables and bullet points over prose.
- Reference external information with permalinks (pinned to commit, version, or archive), not mutable URLs.
- ADRs go in `docs/adr/` and follow the format established in `docs/adr/001-programming-language-and-runtime.md`.

## Project conventions

- Language: Python 3.12+ (see ADR-001)
- Package manager: uv
- Linting/formatting: ruff
- Async runtime: asyncio (stdlib)
- LLM integration: LiteLLM Router with Anthropic primary, OpenAI fallback (see ADR-002)

## Code quality gates

Before completing any coding task, ALL must pass:
- `uv run ruff check src/ tests/` — lint clean
- `uv run ruff format --check src/ tests/` — format clean
- `uv run pytest tests/ -q` — all tests green
- Documentation up to date — ADRs, design.md, infrastructure.md reflect current state

Write tests first or alongside code. No untested code merged.

## Flow & Runtime

- Use repo’s package manager/runtime; no swaps w/o approval.

## Agent Protocol

- “Make a note” => edit CLAUDE.md (shortcut; not a blocker).
- Prefer end-to-end verify; if blocked, say what’s missing.
- New deps: quick health check (recent releases/commits, adoption).
- Web: search early; quote exact errors; prefer 2024–2025-2026 sources.
- Style: telegraph. Drop filler/grammar. Min tokens.
