# ADR-008: Project Conventions and Development Workflow

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#8](https://github.com/DigitalTwinSystems/entwine/issues/8)

## Context

ADR-001 established Python 3.12+, uv, ruff, and mypy/pyright as tooling choices. This ADR locks in the remaining conventions needed before substantive development begins: type checking strategy, testing, git workflow, commit conventions, pre-commit hooks, package structure, and code review process.

## Decision

### Package structure

Src layout with a single top-level package:

```
entwine/
├── pyproject.toml
├── uv.lock
├── .python-version
├── src/
│   └── entwine/
│       ├── __init__.py
│       ├── agents/
│       ├── config/
│       ├── rag/
│       └── web/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
└── docs/
    └── adr/
```

The `src/` layout prevents accidental import of the package from the repo root without installing it, catching packaging bugs early. This is [the recommended layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) for installable packages.

### Type checking

**mypy** with `strict = true`.

| Option | Choice | Rationale |
|--------|--------|-----------|
| Tool | mypy | Established, stable, widest stub coverage; pyright is faster but mypy is battle-tested and integrates well with pre-commit |
| Mode | `strict` | Enables all optional checks: `disallow_untyped_defs`, `warn_return_any`, `disallow_any_generics`, etc. Start strict from day one |
| Stubs | inline + `types-*` from PyPI | Install as dev dependencies via `uv add --dev` |

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_configs = true
```

### Linting and formatting

ruff handles both formatting and linting (replaces black + isort + flake8).

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "B",   # flake8-bugbear
    "I",   # isort
    "UP",  # pyupgrade
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
    "PTH", # flake8-use-pathlib
    "RUF", # ruff-specific
]
ignore = ["E501"]  # line length enforced by formatter

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### Testing

| Area | Choice |
|------|--------|
| Framework | pytest |
| Coverage | pytest-cov (coverage.py backend) |
| Coverage target | 80% overall; 90% for `src/entwine/agents/` and `src/entwine/rag/` |
| Async tests | pytest-anyio |
| Mocking | pytest built-in `monkeypatch` + `unittest.mock` |
| Test layout | `tests/unit/` mirrors `src/entwine/`; `tests/integration/` for external calls |

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src/entwine --cov-report=term-missing --cov-fail-under=80"

[tool.coverage.run]
source = ["src/entwine"]
omit = ["tests/*"]
```

Integration tests that hit real external services (LLM APIs, Qdrant) are skipped in CI by default and gated with a `@pytest.mark.integration` marker:

```toml
[tool.pytest.ini_options]
markers = ["integration: marks tests that require external services (deselect with '-m not integration')"]
```

### Dependency management

uv is the sole tool for all dependency operations. No pip invocations in scripts or CI.

| Command | Purpose |
|---------|---------|
| `uv add <pkg>` | Add runtime dependency |
| `uv add --dev <pkg>` | Add dev/test dependency |
| `uv sync` | Install all deps from lockfile |
| `uv run pytest` | Run tests in project environment |
| `uv lock --upgrade-package <pkg>` | Upgrade a single package |

`uv.lock` is committed to the repository. Dependabot or Renovate can be configured later for automated lockfile updates.

### Pre-commit hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0  # pin to a recent stable release
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.0
    hooks:
      - id: mypy
        additional_dependencies: []  # list any stubs here

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-toml
      - id: check-yaml
      - id: check-merge-conflict
      - id: no-commit-to-branch
        args: [--branch, main]
```

Install with `uv run pre-commit install` after cloning.

### Git workflow

**Trunk-based development** with short-lived feature branches.

| Rule | Detail |
|------|--------|
| Main branch | `main` — always deployable |
| Feature branches | `<type>/<short-description>`, e.g., `feat/agent-memory-layer` |
| Branch lifetime | ≤ 3 days; long-lived work must be feature-flagged |
| Merging | Squash merge to `main` via PR |
| Direct push to `main` | Blocked by `no-commit-to-branch` pre-commit hook and branch protection |

Rationale: trunk-based development reduces merge conflicts and keeps CI fast. GitFlow is too heavyweight for a small team.

### Commit conventions

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) format:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Allowed types:

| Type | Use |
|------|-----|
| `feat` | New feature (triggers MINOR version bump) |
| `fix` | Bug fix (triggers PATCH version bump) |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or fixing tests |
| `chore` | Tooling, CI, dependency updates |
| `perf` | Performance improvement |
| `ci` | CI configuration changes |

Breaking changes: append `!` after type, e.g., `feat!: redesign agent API`, or add `BREAKING CHANGE:` footer.

Commit messages are written in imperative mood: "add agent memory layer" not "added" or "adds".

### Code review

- Every change to `main` requires at least one approval via a PR.
- PR description must reference the issue (e.g., `Closes #8`).
- Review turnaround target: 24 hours on business days.
- Reviewer checklist (not a formal gate, but a mental checklist):
  - Does the code have tests?
  - Are types annotated?
  - Does ruff and mypy pass?
  - Is the PR small enough to review in < 30 minutes? If not, request a split.

### Documentation standards

- All public functions, classes, and modules must have docstrings (Google style).
- ADRs for every significant architectural decision, written before or alongside the implementation.
- No auto-generated API docs for now; add Sphinx or mkdocs-material when the public API stabilises.
- Inline comments explain *why*, not *what*.

## Rationale

- **mypy over pyright:** Both are mature in 2026. mypy has broader community adoption, more stub packages on PyPI, and better pre-commit integration. Pyright (used by Pylance in VS Code) remains available as an editor tool — the two are complementary, not mutually exclusive.
- **80% coverage floor:** High enough to catch regressions, low enough not to encourage test theatre (tests written purely to hit a number). Critical paths (agents, RAG) carry a higher 90% target.
- **Trunk-based over GitFlow:** The team is small; GitFlow's overhead (develop, release, hotfix branches) adds process without value at this scale. Squash merges keep `git log` clean.
- **Conventional Commits:** Enables automated changelogs (e.g., via `git-cliff`) and makes `git log` scannable. Low overhead once habitual.
- **`src/` layout:** Prevents a class of import bugs and makes the packaging boundary explicit. Industry standard for installable Python packages since ~2020.

## Consequences

### Positive
- Consistent, automated code quality from day one (no "we'll add linting later" drift)
- Reproducible environments via committed `uv.lock`
- Clean `git log` supports future changelog automation
- Pre-commit catches issues before CI, reducing wasted CI minutes

### Negative
- `mypy --strict` will require type annotations everywhere; initial setup cost for third-party libraries without stubs
- Pre-commit adds a few seconds to every commit; developers must install it manually after cloning
- Squash merging loses individual commit granularity within a PR (acceptable given Conventional Commits on the squash message)

### Follow-up actions
- [ ] Add `pyproject.toml` with all tool configuration
- [ ] Add `.pre-commit-config.yaml`
- [ ] Configure branch protection on `main` in GitHub
- [ ] Add CI workflow (separate ADR or issue) that runs `uv run pytest`, `uv run mypy`, `uv run ruff check`
