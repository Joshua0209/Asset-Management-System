# System Design Index

**Project:** Asset Management System (資產管理系統)
**Version:** 1.0 — 2026-04-13

---

| File | Contents |
|------|----------|
| [00-user-study.md](./00-user-study.md) | Raw user research notes — interviews with asset holders and managers |
| [01-user-story.md](./01-user-story.md) | User stories derived from research — actor goals and acceptance criteria |
| [02-requirements.md](./02-requirements.md) | Functional requirements (FR) and non-functional requirements (NFR) |
| [03-usage-estimates.md](./03-usage-estimates.md) | QPS, storage, and machine count estimates for all three phases |
| [04-phase1-architecture.md](./04-phase1-architecture.md) | Pilot (300 DAU) — monolith on a single EC2, ~$34/mo |
| [05-phase2-architecture.md](./05-phase2-architecture.md) | Growth (30K DAU) — ALB + 2 nodes + RDS Multi-AZ, ~$200/mo |
| [06-phase3-architecture.md](./06-phase3-architecture.md) | SaaS platform (3M DAU) — EKS + SOA + Redis + Elasticsearch, ~$1,729/mo (for reference only, no need to implement) |
| [07-database-design.md](./07-database-design.md) | ER diagram, schema notes, optimistic locking, index strategy |
| [08-deployment-operations.md](./08-deployment-operations.md) | Zero-downtime deployment, monitoring thresholds, backup & recovery |
| [09-testing-strategy.md](./09-testing-strategy.md) | Test pyramid, coverage targets, load/stress/chaos testing |
| [10-design-decisions.md](./10-design-decisions.md) | Resolved team decisions on stack, storage, business logic, scope |
| [11-asset-fsm.md](./11-asset-fsm.md) | Asset finite state machine — state diagram and transition table |
| [12-api-design.md](./12-api-design.md) | REST API contract — endpoints, request/response shapes, RBAC, error codes |
| [13-design-tokens.md](./13-design-tokens.md) | UI design tokens — TSMC-inspired color system, typography, spacing, motion, dark mode |
