---
department: company-wide
accessible_roles: company-wide
sensitivity: public
---

# New Employee Onboarding Guide

## Week 1: Setup & Orientation

### Day 1
- Laptop setup: follow IT checklist (emailed pre-start)
- Clone the monorepo: `git clone git@github.com:acme-corp/platform.git`
- Install dev tools: `brew install --cask docker && uv install`
- Join Slack channels: #general, #engineering, #your-department
- 1:1 with your manager (30 min)

### Day 2–3
- Complete security training (mandatory, ~2 hours)
- Read the Engineering Playbook (see knowledge base)
- Run the full test suite locally: `uv run pytest tests/ -q`
- Set up pre-commit hooks: `uv run pre-commit install`

### Day 4–5
- Shadow a teammate on their current project
- Pick up your first "good first issue" from GitHub
- Attend your first daily standup

## Week 2: First Contribution

- Ship your first PR (aim for < 100 lines)
- Complete code review training (async, ~1 hour)
- Meet with your onboarding buddy for a codebase walkthrough
- Join your first sprint planning session

## Week 3–4: Ramp Up

- Take ownership of a feature or bug fix
- Present at team demo (5-min lightning talk on what you learned)
- 30-day check-in with manager: feedback, goals, questions

## Key Contacts

| Role | Person | Slack |
|------|--------|-------|
| CEO | Alice Chen | @alice |
| CTO | David Park | @david |
| Head of Marketing | Sofia Reyes | @sofia |
| Head of Ops/HR | Rachel Kim | @rachel |
| Support Lead | Tariq Hassan | @tariq |

## Useful Links

- Engineering Playbook: knowledge base → engineering-playbook
- Product Roadmap: knowledge base → product-roadmap-q2
- Support Runbook: knowledge base → support-runbook
- Company Handbook: knowledge base → company-handbook
