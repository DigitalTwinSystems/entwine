---
department: company-wide
accessible_roles: company-wide
sensitivity: public
---

# New Employee Onboarding Guide

Welcome to Acme Corp. This guide walks you through your first 30 days. By the end of week 4, you should be shipping code, participating in sprint ceremonies, and feeling like part of the team.

## Week 1: Setup and Orientation

### Day 1

- Laptop setup: follow the IT checklist (emailed pre-start). If anything is missing, ping #it-support on Slack.
- Clone the monorepo: `git clone git@github.com:acme-corp/platform.git`
- Install dev tools: `brew install --cask docker && uv install`. Verify: `uv run pytest tests/unit/ -q` should show all tests passing.
- Join Slack channels: #general, #engineering, #your-department, #standup, #random.
- 1:1 with your manager (30 minutes): discuss role expectations, team structure, and your first-week goals.
- Meet your onboarding buddy: they are your go-to person for questions during the first month.

### Day 2 to 3

- Complete security training (mandatory, approximately 2 hours). Covers access policies, credential management, and incident reporting. Access via the LMS link in your welcome email.
- Read the Engineering Standards document in the knowledge base. Pay attention to git workflow, testing standards, and code review expectations.
- Run the full test suite locally: `uv run pytest tests/ -q`. If tests fail, check that Docker is running (required for integration tests).
- Set up pre-commit hooks: `uv run pre-commit install`. This runs linting and formatting automatically before each commit.
- Set up your development environment: IDE of choice (most of the team uses VS Code or PyCharm), configure ruff extension for auto-formatting.

### Day 4 to 5

- Shadow a teammate on their current project. Observe how they work through a PR, handle code review feedback, and communicate decisions.
- Pick up your first "good first issue" from GitHub. These are specifically tagged for new team members and have detailed descriptions.
- Attend your first daily standup (09:00 UTC, 15 minutes). Format: what I did, what I am doing, any blockers.
- Review the product roadmap to understand what the company is building and why.

## Week 2: First Contribution

- Ship your first PR (aim for under 100 lines). Your onboarding buddy will review it.
- Complete code review training (async, approximately 1 hour). Covers the reviewer checklist, how to give constructive feedback, and when to approve vs request changes.
- Meet with your onboarding buddy for a codebase walkthrough. Key areas: project structure, configuration loading, agent lifecycle, event bus, platform adapters.
- Join your first sprint planning session. Observe how stories are estimated and prioritised.
- Introduce yourself in #general with a short bio and fun fact.

## Week 3 to 4: Ramp Up

- Take ownership of a feature or bug fix. Your manager will assign something appropriately scoped.
- Present at team demo (5-minute lightning talk on what you learned or built). Demo day is every other Friday.
- 30-day check-in with manager: feedback on your ramp-up, initial goals for next quarter, questions or concerns.
- Complete your onboarding feedback form (sent via email at day 28). This helps us improve the process for future hires.
- By end of week 4, you should be comfortable with: the codebase structure, the PR workflow, running tests locally, and participating in sprint ceremonies.

## Key Contacts

| Role | Person | Slack Handle |
|------|--------|-------------|
| CEO | Alice Chen | @alice |
| CTO | David Park | @david |
| Head of Marketing | Sofia Reyes | @sofia |
| Head of Ops/HR | Rachel Kim | @rachel |
| Support Lead | Tariq Hassan | @tariq |
| Senior Engineer | Ben Muller | @ben |
| DevOps Lead | James Rodriguez | @james |

## Useful Links

- Engineering Standards: knowledge base, engineering-standards
- Product Roadmap: knowledge base, product-roadmap
- Support Runbook: knowledge base, support-runbook
- Company Handbook: knowledge base, company-handbook
- Internal wiki: wiki.acme.dev (login with your SSO credentials)
- CI/CD dashboard: github.com/acme-corp/platform/actions

## FAQ

**Q: How do I get access to production systems?**
A: Production access requires manager approval. Submit a request via #it-support with your manager's confirmation. Access is granted for a specific duration and logged for audit purposes.

**Q: What if I break something?**
A: Do not panic. Our CI/CD pipeline catches most issues before they reach production. If something does break in production, alert the on-call engineer via PagerDuty. We have a blameless culture — mistakes are learning opportunities, not career-ending events.

**Q: How do I request time off?**
A: Submit PTO requests via BambooHR. Manager approval required for absences longer than 5 business days. See the Company Handbook for the full PTO policy.
