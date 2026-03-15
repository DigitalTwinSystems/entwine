---
department: engineering
accessible_roles: cto, developer, devops, data analyst
sensitivity: internal
---

# Acme Corp Engineering Standards

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12, FastAPI | Async-first, Pydantic models |
| Frontend | React 19, TypeScript | Component library: internal |
| Database | PostgreSQL 16 | Primary OLTP store |
| Cache | Redis 7 | Session, rate-limiting, pub/sub |
| Search | Qdrant | Vector store for RAG pipeline |
| CI/CD | GitHub Actions | Lint, test, build, deploy |
| Infra | Terraform + AWS | EKS for prod, Docker Compose for dev |
| Observability | Structlog, OpenTelemetry, Grafana | JSON logs, distributed traces |

## Git Workflow

- `main` is always deployable. Protected branch: requires 1 approval plus passing CI.
- Feature branches: `feat/<ticket-id>-short-description`
- Bug fixes: `fix/<ticket-id>-short-description`
- PRs should be under 400 lines. Larger changes need an RFC document submitted to #eng-rfcs for review before implementation begins.
- Commit messages follow Conventional Commits format: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Squash merges are the default. Merge commits are used only for long-lived feature branches with meaningful history.

## Code Review Standards

- Every PR requires at least one approval from a team member outside the author's immediate squad.
- Focus on correctness, security, and maintainability — not style (ruff handles formatting).
- Review within 4 business hours. If blocked, ping in #eng-reviews. Stale reviews (no response after 24 hours) are re-assigned automatically.
- Reviewer checklist: tests cover new behaviour, no credentials in code, error handling covers failure modes, performance impact considered.

## Testing Standards

- Unit tests are mandatory for all business logic. Aim for 80% coverage minimum on new code.
- Integration tests for database, external API, and cross-service interactions go in `tests/integration/` and are marked with `@pytest.mark.integration`.
- End-to-end tests cover critical user flows. Run nightly in CI, not on every PR.
- Test naming: `test_<module>.py` mirroring the source module. Use descriptive test names that read like documentation.
- Mocking: prefer dependency injection over monkey-patching. Use `AsyncMock` for async code. Never call real external services in unit tests.

## Deployment

- Merges to `main` auto-deploy to staging. Staging has production-equivalent data (anonymised).
- Production deploys: manual trigger via GitHub Actions after staging soak (minimum 2 hours).
- Rollback: revert the merge commit and redeploy. Maximum rollback time target: 5 minutes.
- Feature flags: all new features launch behind a flag. Flags are cleaned up within 30 days of full rollout.
- Database migrations: always backwards-compatible. Run `alembic upgrade head` as part of the deploy pipeline. Destructive migrations (drop column, drop table) require a 2-sprint deprecation period.

## On-Call

- Weekly rotation among senior engineers. Pager: PagerDuty. Schedule is published 4 weeks in advance.
- Runbook links in every alert. If no runbook exists, create one during the incident.
- Post-incident review within 48 hours; blameless format. Action items tracked in Linear with SLA of 2 sprints.
- On-call engineer is not expected to deliver sprint work during their rotation. They focus on incident response, flaky test fixes, and operational improvements.

## Security Standards

- No credentials in code or config files. Use environment variables or AWS Secrets Manager.
- All API endpoints require authentication via JWT (issued by Auth0) or API key.
- Rate limiting: 1000 req/min per API key (adjustable per customer tier).
- Dependencies audited weekly via Dependabot. Critical CVEs must be patched within 48 hours.
- Access control follows principle of least privilege. Production database access requires manager approval and is logged.
