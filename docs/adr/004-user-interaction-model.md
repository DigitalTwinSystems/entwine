# ADR-004: User Interaction Model

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#4](https://github.com/DigitalTwinSystems/entwine/issues/4)

## Context

Users need to configure, monitor, and control the entwine simulation. The target audience is developers (initially). FastAPI is already the chosen HTTP framework (ADR-001). The system runs ~12 concurrent asyncio agents whose activity must be observable in real time.

We evaluated five approaches: TUI (Textual), Web UI (HTMX, SvelteKit, Next.js), Desktop (Tauri, Electron), GitOps/config-as-code, and hybrid combinations.

## Decision

### Hybrid: Config-as-code + FastAPI + HTMX + SSE

| Layer | Choice | Role |
|-------|--------|------|
| Configuration | TOML + YAML, validated by [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Define enterprise structure, agent roles, simulation params |
| Monitoring | [HTMX](https://htmx.org/) + [SSE via `sse-starlette`](https://pypi.org/project/sse-starlette/) | Real-time agent activity dashboard in browser |
| Control | HTMX form posts to FastAPI | Pause/resume/step/configure simulation |
| CLI | Python CLI (`click` or `typer`) | `entwine start`, `entwine pause`, `entwine export` |

### Config file layout

- **TOML** for flat simulation parameters (timing, LLM settings, feature flags) — Python stdlib `tomllib` support
- **YAML** for hierarchical definitions (org chart, agent personas, role relationships) — more readable for nested structures
- Both validated via Pydantic models at load time

## Rationale

### Why FastAPI + HTMX + SSE

| Criterion | Textual TUI | FastAPI + HTMX + SSE | SvelteKit | Tauri |
|-----------|-------------|---------------------|-----------|-------|
| Dev effort | Low | Low-medium | Medium-high | High |
| Python-only | Yes | Yes (HTML templates) | No (JS/TS) | No (Rust/JS) |
| asyncio alignment | [Native](https://textual.textualize.io/guide/workers/) | Good (SSE is async) | Client-side | Sidecar |
| Browser accessible | [Beta (textual-web)](https://github.com/Textualize/textual-web) | Yes | Yes | No |
| Shareability | Low | High | High | Low |
| Upgrade path | Rebuild for web | Add SvelteKit frontend | Already rich | N/A |

- **FastAPI is already chosen** — the monitoring UI is an extension, not a new runtime.
- **HTMX keeps the stack Python-only**: server-rendered HTML fragments, no JS build pipeline, no npm. [HTMX + FastAPI patterns](https://johal.in/htmx-fastapi-patterns-hypermedia-driven-single-page-applications-2025/) are well-documented.
- **SSE handles the monitoring feed**: `sse-starlette` is [production-ready](https://pypi.org/project/sse-starlette/), W3C-compliant, and natively async. Agent events stream to the browser as HTML fragments swapped by HTMX (`hx-ext="sse"`). Unidirectional push covers the dominant use case (watching agent activity).
- **Browser-accessible immediately**: works on headless servers, shareable on local networks, no terminal requirement.
- **WebSocket endpoints** can be added later for bidirectional interactive control (agent injection, real-time parameter tuning) without architecture changes.

### Why not Textual TUI as primary

Textual has [ideal asyncio integration](https://textual.textualize.io/guide/workers/) and lowest initial effort. However:
- Not browser-accessible without [textual-web](https://github.com/Textualize/textual-web) (still beta as of March 2026).
- Upgrading to a web UI later requires a full rebuild — the rendering model is fundamentally different.
- Starting with HTMX is only marginally more effort and provides a strictly better upgrade path.

### Why not SvelteKit / Next.js

- Both introduce a JavaScript build pipeline and a separate frontend project.
- [SvelteKit](https://svelte.dev/docs/kit/introduction) is the stronger choice of the two (smaller bundles, simpler reactivity, [growing ecosystem](https://dev.to/paulthedev/sveltekit-vs-nextjs-in-2026-why-the-underdog-is-winning-a-developers-deep-dive-155b)), but the added complexity isn't justified for an initial developer tool.
- If HTMX proves insufficient for richer interactivity, SvelteKit can be added as a frontend against the existing FastAPI API — the backend stays stable.

### Why not Tauri desktop

- [Tauri + FastAPI sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar) works but adds significant packaging complexity (PyInstaller + Tauri build pipeline).
- [pytauri](https://github.com/pytauri/pytauri) (Python bindings) is pre-1.0 with evolving APIs.
- Developers already have Python installed — a packaged desktop app solves a problem that doesn't exist yet.

### Why config-as-code

- Enterprise definitions (org chart, roles, personas) are naturally declarative and benefit from version control, diffing, and branching for scenario experiments.
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) supports layered config: file defaults < env vars < CLI overrides. Catches invalid configs at startup with clear error messages.
- Config files are the "what to simulate"; the web UI shows "what is happening" — complementary, not competing.

## Consequences

### Positive

- Entire stack stays in Python — no JS/TS build toolchain
- FastAPI serves both agent coordination and monitoring UI — single server process
- Config-as-code enables reproducible simulation experiments via git
- Browser-accessible monitoring works on headless servers and across machines
- Clear upgrade path: HTMX → SvelteKit frontend if richer interactivity needed

### Negative

- HTMX limits interactivity compared to a full JS framework (no complex client-side state management)
- HTML templates add a small amount of non-Python code to maintain
- SSE is unidirectional — if frequent bidirectional control is needed, WebSocket endpoints must be added
- Two config formats (TOML + YAML) add minor cognitive overhead vs. a single format
