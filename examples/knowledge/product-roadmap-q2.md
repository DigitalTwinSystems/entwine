---
department: executive
accessible_roles: ceo, cto, product manager, head of marketing
sensitivity: confidential
---

# Q2 2026 Product Roadmap

## Theme: Developer Experience 2.0

### P0 — Must Ship

1. **Unified Search** — Full-text + semantic search across all workspace content. Target: 50ms p95 latency. Owner: David Park.
2. **API v2** — Breaking changes for consistency. 6-month deprecation window for v1. Owner: Ben Müller.
3. **SOC 2 Type II** — Audit prep. All logging, access controls, and incident response docs must be finalized by May 15. Owner: Rachel Kim.

### P1 — Should Ship

4. **Plugin Marketplace** — Third-party integrations via sandboxed WASM modules. Owner: Priya Sharma.
5. **Usage Analytics Dashboard** — Self-serve product metrics for customers. Owner: Omar Fahd.
6. **Mobile Companion App** — Read-only view of workspace notifications and activity feed. Owner: TBD.

### P2 — Nice to Have

7. **AI Code Review** — Automated PR review suggestions using Claude. Experimental. Owner: David Park.
8. **Multi-region Storage** — EU data residency option. Depends on SOC 2 completion.

## Key Dates

| Date | Milestone |
|------|-----------|
| Apr 1 | API v2 beta opens |
| Apr 15 | Unified Search internal dogfood |
| May 15 | SOC 2 docs freeze |
| Jun 1 | Plugin Marketplace beta |
| Jun 30 | Q2 release (API v2 GA, Unified Search GA) |

## Success Metrics

- NPS ≥ 55 (current: 48)
- API adoption: 40% of customers on v2 by EOQ
- Search usage: 3x daily active queries vs. Q1
