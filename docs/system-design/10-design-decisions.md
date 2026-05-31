# Design Decisions

Resolved team discussions on technology and business logic choices.

---

## Category A: Technology Stack

**Q1. Backend language/framework?**
Options: Node.js (Express/Fastify), Python (FastAPI/Django), Go (Gin), Java (Spring Boot)

→ **Python + FastAPI** — chosen for auto-generated OpenAPI docs, Pydantic validation, and async support. ORM: SQLAlchemy + Alembic for migrations.

---

**Q2. Frontend framework?**
Options: React (Next.js / Vite), Vue 3 (Nuxt), Angular, or server-rendered (HTMX)

→ **React + Vite** — plain SPA is sufficient; no SSR needed since the backend is a separate FastAPI service. Routing via `react-router-dom`, i18n via `react-i18next`.

---

**Q3. ORM vs raw SQL?**
Options: Prisma, TypeORM, SQLAlchemy, GORM, raw SQL with query builder

→ **SQLAlchemy ORM** (with Alembic for migrations) — the optimistic locking pattern (`WHERE version = ?`) works via SQLAlchemy's built-in `version_id_col` mapper argument.

---

## Category B: Data & Storage

**Q4. Image upload strategy: client-direct-to-S3 (presigned URL) or upload-through-server?**
- Presigned URL: Lower server load, more complex frontend, requires CORS config
- Through server: Simpler, but server becomes bottleneck for large files

→ **Through server** (simpler for Phase 1-2; presigned URLs considered if Phase 3 is implemented)

---

**Q5. Asset ID format?**
Options: Auto-increment integer, UUID v4, custom business code (e.g., `AST-2026-00001`)

→ **UUID** — opaque, no information leakage; business code (`asset_code`) used as the human-facing identifier.

---

**Q6. Multi-tenancy isolation level for Phase 3?**

→ **Irrelevant** — Phase 3 multi-tenancy will not be implemented for the course project.

---

## Category C: Business Logic

**Q7. What happens to in-progress repair requests when an asset is reassigned to a new holder?**

→ **Forbidden** — cannot reassign an asset that has an active repair request.

---

**Q8. Can a repair request be cancelled by the holder after submission (before review)?**

→ **No** — once submitted, the holder cannot cancel.

---

**Q9. Should managers be able to assign repair requests to specific managers (task assignment)?**

→ **No** — out of scope.

---

**Q10. Asset classification: flat list or hierarchical?**

→ **Two-level flat list** — one level of categories (e.g., Electronics) with a flat item list beneath. No deeper hierarchy.

---

**Q21. Does `assets.department` / `assets.location` represent the asset's current assignment context?**

Context: FR-13 labels these fields as 「使用部門」 and 「存放地點」. The user-study answer says: 「備十台電腦，沒預設給誰，用部門經費才能 assign 給持用者，資產管理員收到申請後會分配給部門」. Issue #97 surfaced that the system must make this lifecycle meaning explicit instead of leaving seeded asset values stale after assignment.

→ **Yes.** `assets.department` and `assets.location` represent the asset's current allocation context:

- `assets.department` is the asset's current owning/responsible department.
- `assets.location` is the asset's current physical location.
- `users.department` and `users.location` are the user's department and regular workplace/site; for assigned assets, the holder department is exposed as `responsible_person.department`.
- T1 (register asset): if the manager omits `department` or `location`, the asset defaults to the current manager's department/location because unassigned stock is managed by the asset-management side.
- T2 (assign): the asset's `department` and `location` are synced to the assigned holder's `department` and `location`.
- T5 (unassign/reclaim): the asset's `department` and `location` are synced back to the current manager's `department` and `location`.
- `PATCH /assets/{id}` may still correct `department` or `location` when a manager needs to fix asset records outside a lifecycle transition.
- UI and API docs describe `assets.department` as the asset owning/responsible department to avoid confusing it with the holder department (`responsible_person.department`).

---

## Category D: Non-Functional Trade-offs

**Q11. Acceptable search consistency window (Elasticsearch eventual consistency)?**

→ **Irrelevant** — Elasticsearch is a Phase 3 concern not being implemented.

---

**Q12. Image retention policy?**

→ **Irrelevant** for the course scope.

---

**Q13. Audit trail requirements?**

→ **Yes** — log changes as event streams.

---

**Q14. Notification strategy?**

→ **Optional, not urgent** — not in scope for the initial implementation.

---

## Category E: Scope & Prioritization

**Q15. Which advanced requirements to implement?**

Priority order: **1, 2, 4 > 3 > 5 > 6**
1. High availability
2. Zero-downtime deployment
3. Concurrency control / optimistic locking
4. Multi-dimensional search
5. i18n
6. Image upload

---

**Q16. Monorepo or polyrepo?**

→ **Monorepo**

---

**Q17. Should Phase 3 multi-tenancy be implemented or only designed?**

→ **Design only** — a well-documented Phase 3 design with Phase 2 implementation is the target.

---

## Category F: Frontend Design System

**Q18. Frontend UI component library?**
Options: Ant Design (`antd`), shadcn/ui + Tailwind, Material UI, Chakra UI, custom

→ **Ant Design v6 (`antd` + `@ant-design/icons`)** — comprehensive component set covering all required UI patterns (tables, forms, modals, navigation); built-in dark/light mode switching via `ConfigProvider` with `theme.darkAlgorithm` / `theme.defaultAlgorithm`; React 18 compatible; chosen in Week 2. Visual direction overrides (TSMC-inspired palette, typography scale, spacing tokens) are documented in `docs/designs/DESIGN.md` and `docs/designs/design-tokens.json` — those constraints apply on top of Ant Design defaults.

---

**Q19. Design token location?**

→ Moved from `docs/system-design/13-design-tokens.md` to `docs/designs/` (dedicated design system directory). `docs/designs/DESIGN.md` is now the normative reference for color, typography, spacing, motion, and the "does this feel TSMC?" checklist. `docs/designs/design-tokens.json` is the machine-readable W3C Design Tokens format file.

---

## Category G: Audit Surface

**Q20. How does `GET /assets/{id}/history` signal that the asset has been soft-deleted?**

Context: the history endpoint intentionally does *not* filter on `Asset.deleted_at` — auditors must be able to read history for disposed/removed assets (sibling of Q13). The companion `GET /assets/{id}` *does* filter and returns 404 on soft-deletes. Without an explicit signal, a frontend rendering an "Asset detail" header on top of the history payload happily renders the tombstone with no visual cue.

Options considered:

1. **Add `asset_deleted_at: datetime | None` to the history response's `meta` block.** Single round-trip; the frontend can show a "Viewing history for a deleted asset" banner with the deletion timestamp directly.
2. Keep history pure and require a second call to fetch tombstone context. Architecturally cleaner (no cross-resource leakage), but forces a new endpoint or a new query param on `get_asset` (which itself filters soft-deletes out), and shifts complexity to the frontend.

→ **Option 1.** The deletion fact is *about the asset whose history is being viewed*, not a separate resource. Putting it next to the events the auditor is already reading minimizes the chance the signal is missed, and avoids inventing a new "give me the tombstone" endpoint. Shape coupling is bounded to one optional field on a dedicated `HistoryMeta` (a subclass of `PaginationMeta`), so the generic pagination meta stays single-purpose for the other list endpoints. If more parent-context fields appear later, revisit.
