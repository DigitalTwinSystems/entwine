---
department: engineering
accessible_roles: cto, developer, devops, data analyst
sensitivity: internal
---

# Engineering Playbook

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12, FastAPI | Async-first, Pydantic models |
| Frontend | React 19, TypeScript | Component library: internal |
| Database | PostgreSQL 16 | Primary OLTP store |
| Cache | Redis 7 | Session, rate-limiting, pub/sub |
| Search | Qdrant | Vector store for RAG pipeline |
| CI/CD | GitHub Actions | Lint → test → build → deploy |
| Infra | Terraform + AWS | EKS for prod, Docker Compose for dev |
| Observability | Structlog, OpenTelemetry, Grafana | JSON logs, distributed traces |

## Git Workflow

- `main` is always deployable. Protected branch: requires 1 approval + passing CI.
- Feature branches: `feat/<ticket-id>-short-description`
- Bug fixes: `fix/<ticket-id>-short-description`
- PRs should be < 400 lines. Larger changes need an RFC.

## Code Review Standards

- Every PR requires at least one approval from a team member.
- Focus on correctness, security, and maintainability — not style (ruff handles that).
- Review within 4 business hours. If blocked, ping in #eng-reviews.

## Deployment

- Merges to `main` auto-deploy to staging.
- Production deploys: manual trigger via GitHub Actions after staging soak (minimum 2 hours).
- Rollback: revert the merge commit and redeploy. Maximum rollback time target: 5 minutes.

## On-Call

- Weekly rotation among senior engineers. Pager: PagerDuty.
- Runbook links in every alert. If no runbook exists, create one during the incident.
- Post-incident review within 48 hours; blameless format.
