---
department: executive
accessible_roles: ceo, cto, product manager, head of marketing
sensitivity: confidential
---

# Q2 2026 Product Roadmap

## Theme: Developer Experience 2.0

Our Q2 focus is delivering the core platform improvements that our largest customers have been requesting. The three P0 items represent commitments made during enterprise contract renewals and must ship by end of June. P1 items are strategic bets that position us for H2 growth. P2 items are experimental and will only proceed if engineering capacity allows.

### P0 — Must Ship

1. **Unified Search** — Full-text plus semantic search across all workspace content. Target: 50ms p95 latency on workspaces with up to 500k documents. Dense vector search via Qdrant plus BM25 sparse retrieval with RRF fusion. Owner: David Park. Engineering estimate: 6 weeks.

2. **API v2** — Breaking changes for consistency across all endpoints. Request and response schemas standardised on JSON:API format. 6-month deprecation window for v1, with automatic migration tooling for common patterns. Owner: Ben Muller. Engineering estimate: 8 weeks. Marketing launch coordinated with Sofia's blog series.

3. **SOC 2 Type II** — Audit preparation. All logging, access controls, and incident response documentation must be finalised by May 15. Requires engineering support for audit log completeness and access control reviews. Owner: Rachel Kim. External auditor: Coalfire. Budget: $35,000.

### P1 — Should Ship

4. **Plugin Marketplace** — Third-party integrations via sandboxed WASM modules. Developers can publish plugins that extend workspace functionality without accessing customer data directly. Revenue share model: 80% developer, 20% Acme Corp. Owner: Priya Sharma. Engineering estimate: 10 weeks.

5. **Usage Analytics Dashboard** — Self-serve product metrics for customers. Covers active users, feature adoption, search query volume, and API usage. Data retention: 90 days. Owner: Omar Fahd. Engineering estimate: 4 weeks. Depends on event pipeline refactor (completed in Q1).

6. **Mobile Companion App** — Read-only view of workspace notifications, activity feed, and search. iOS and Android via React Native. No editing capabilities in v1 — intentionally limited scope. Owner: TBD (hiring for this role). Engineering estimate: 8 weeks.

### P2 — Nice to Have

7. **AI Code Review** — Automated PR review suggestions using Claude. Experimental feature behind a flag. Goal: reduce review turnaround by 30%. Owner: David Park. Depends on E2B sandbox integration for safe code execution.

8. **Multi-region Storage** — EU data residency option for enterprise customers requiring GDPR-compliant data handling. Depends on SOC 2 completion. Infrastructure cost: approximately $8,000 per month additional.

## Key Dates

| Date | Milestone | Owner |
|------|-----------|-------|
| Apr 1 | API v2 beta opens to 10 design partners | Ben Muller |
| Apr 15 | Unified Search internal dogfood (all employees) | David Park |
| May 1 | Plugin Marketplace architecture review | Priya Sharma |
| May 15 | SOC 2 documentation freeze | Rachel Kim |
| Jun 1 | Plugin Marketplace beta (invited developers) | Priya Sharma |
| Jun 15 | API v2 GA release candidate | Ben Muller |
| Jun 30 | Q2 release: API v2 GA, Unified Search GA | David Park |

## Success Metrics

- NPS score of 55 or above (current: 48). Measured via quarterly survey.
- API adoption: 40% of customers on v2 by end of Q2. Tracked via API version header.
- Search usage: 3x daily active queries vs Q1. Tracked via analytics pipeline.
- Plugin Marketplace: 5 third-party plugins published during beta.
- Mobile app: 500 downloads in first month (if shipped).

## Risks and Mitigations

- **SOC 2 delay**: If audit prep is not complete by May 15, the external audit timeline shifts to Q3, delaying enterprise deals. Mitigation: Rachel has a weekly checkpoint with engineering to track documentation gaps.
- **API v2 migration complexity**: Some customers have deep v1 integrations. Mitigation: dedicated migration support during beta, automated compatibility checker tool.
- **Hiring for mobile lead**: Position has been open for 6 weeks. Mitigation: if not filled by April 15, David will reassign an internal engineer and reduce scope to iOS only.
