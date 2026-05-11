# Database Design

---

## Entity-Relationship Overview

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    users     │     │     assets       │     │ repair_requests  │
├──────────────┤     ├──────────────────┤     ├──────────────────┤
│ id (PK)      │◄────│ responsible_     │     │ id (PK)          │
│ tenant_id    │     │   person_id (FK) │     │ tenant_id        │
│ email        │     │ id (PK)          │◄────│ asset_id (FK)    │
│ password_hash│     │ tenant_id        │     │ requester_id(FK) │──►users
│ name         │     │ asset_code       │     │ reviewer_id (FK) │──►users
│ role         │     │ name             │     │ status           │
│ department   │     │ model            │     │ fault_description│
│ created_at   │     │ specs            │     │ repair_date      │
│ updated_at   │     │ category         │     │ fault_content    │
│ deleted_at   │     │ supplier         │     │ repair_plan      │
│ version      │     │ purchase_date    │     │ repair_cost      │
└──────────────┘     │ purchase_amount  │     │ repair_vendor    │
                     │ location         │     │ rejection_reason │
                     │ department       │     │ completed_at     │
                     │ activation_date  │     │ created_at       │
                     │ warranty_expiry  │     │ updated_at       │
                     │ status           │     │ deleted_at       │
                     │ disposal_reason  │     │ version          │
                     │ created_at       │     └──────────────────┘
                     │ updated_at       │              │
                     │ deleted_at       │              │ 1:N
                     │ version          │              ▼
                     └──────────────────┘     ┌──────────────────┐
                                              │ repair_images    │
                                              ├──────────────────┤
                                              │ id (PK)          │
                                              │ repair_request_id│
                                              │ image_url        │
                                              │ uploaded_at      │
                                              └──────────────────┘

┌─────────────────────────┐
│  asset_action_histories │
├─────────────────────────┤
│ id (PK)                 │
│ tenant_id               │
│ asset_id (FK)           │──►assets
│ actor_id (FK)           │──►users
│ action                  │
│ from_status             │
│ to_status               │
│ metadata (JSONB)        │
│ created_at              │
└─────────────────────────┘
```

---

## Key Design Notes

- **`version` column:** On `assets`, `repair_requests`, and `users`. Enables optimistic locking. Every UPDATE includes `WHERE version = ?` and increments version. If 0 rows affected, the client receives a conflict error (HTTP 409).
- **`tenant_id`:** Added in Phase 3 for multi-tenancy. In Phase 1-2, this column can be omitted or set to a default value.
- **`deleted_at` (soft delete):** Present on `assets`, `repair_requests`, and `users`. NULL means active; a timestamp means logically deleted. All queries must include `WHERE deleted_at IS NULL`. Hard deletes are never performed on business data.
- **`status` enum values (aligned to FSM in `10-asset-fsm.md`):**
  - Asset: `in_stock`, `in_use`, `pending_repair`, `under_repair`, `disposed`
  - Repair request: `pending_review`, `under_repair`, `completed`, `rejected`
- **`asset_code`:** Business-facing unique identifier (e.g., `AST-2026-00001`). Separate from internal `id` (auto-increment or UUID).
- **Numeric types:**
  - `purchase_amount`: `NUMERIC(15, 2)` — exact decimal, avoids floating-point rounding for financial values.
  - `repair_cost`: `NUMERIC(15, 2)` — same rationale.
  - Use `NUMERIC`/`DECIMAL` (SQL standard synonyms) for any monetary or measurement column. Never `FLOAT` or `DOUBLE` for money.

---

## `asset_action_histories` Table

Append-only audit log. One row per FSM transition, written atomically in the same transaction as the state change.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `BIGSERIAL` / `UUID` | Primary key |
| `tenant_id` | `BIGINT` | Phase 3; nullable in Phase 1-2 |
| `asset_id` | `BIGINT` | FK → `assets.id` |
| `actor_id` | `BIGINT` | FK → `users.id` — who performed the action |
| `action` | `VARCHAR(64)` | e.g. `assign`, `submit_repair`, `approve_repair`, `complete_repair`, `scrap` |
| `from_status` | `VARCHAR(32)` | Asset status before transition |
| `to_status` | `VARCHAR(32)` | Asset status after transition |
| `metadata` | `JSONB` | Optional context (e.g. `{ "repair_request_id": 42, "reason": "..." }`) |
| `created_at` | `TIMESTAMP` | Immutable insert time; no `updated_at` or `deleted_at` (audit rows are never modified) |

> **Why JSONB for metadata?** Repair approvals, rejections, and completions each carry different supplementary fields. JSONB avoids nullable columns for each case while keeping the table schema stable.

---

## Soft Delete Strategy

```sql
-- Filter active records (all normal queries)
SELECT * FROM assets WHERE deleted_at IS NULL;

-- Soft delete
UPDATE assets SET deleted_at = NOW(), version = version + 1 WHERE id = ? AND version = ?;

-- Recover (admin only)
UPDATE assets SET deleted_at = NULL, version = version + 1 WHERE id = ? AND version = ?;
```

Partial unique index to ensure `asset_code` uniqueness only among active rows:

```sql
CREATE UNIQUE INDEX idx_assets_code_active ON assets(asset_code) WHERE deleted_at IS NULL;
```

---

## Index Strategy

> **MySQL 8.0 limitation:** MySQL does not support partial indexes (`CREATE INDEX ... WHERE ...`).
> The `WHERE deleted_at IS NULL` filter shown in early drafts has been removed from all index
> definitions. Queries apply `deleted_at IS NULL` at query time, so the indexes remain effective;
> soft-deleted rows are included in the index at a small storage cost but are never returned to
> callers. If the database is migrated to PostgreSQL in the future, partial indexes can be
> reinstated for improved write performance and index size.

```sql
-- Phase 1: Basic indexes (created in migration 20260417_0001)
CREATE INDEX ix_assets_responsible_person_id ON assets(responsible_person_id);
CREATE INDEX ix_assets_status ON assets(status);
CREATE INDEX ix_repair_requests_asset_id ON repair_requests(asset_id);
CREATE INDEX ix_repair_requests_requester_id ON repair_requests(requester_id);
CREATE INDEX ix_repair_requests_status ON repair_requests(status);

-- History table (created in migration 20260506_0003)
CREATE INDEX idx_history_asset ON asset_action_histories(asset_id);
CREATE INDEX idx_history_actor ON asset_action_histories(actor_id);
CREATE INDEX idx_history_created ON asset_action_histories(created_at);

-- Phase 2: Multi-dimensional search support (added in migration 20260511_0004)
CREATE INDEX idx_assets_dept_loc ON assets(department, location);
CREATE INDEX idx_assets_category_status ON assets(category, status);
CREATE INDEX idx_repair_status_date ON repair_requests(status, created_at);

-- Phase 3: Tenant-prefixed indexes (future — single-tenant until Phase 3 rollout)
CREATE INDEX idx_assets_tenant_search ON assets(tenant_id, category, status);
CREATE INDEX idx_assets_tenant_person ON assets(tenant_id, responsible_person_id);
CREATE INDEX idx_repair_tenant_status ON repair_requests(tenant_id, status, created_at);
CREATE INDEX idx_history_tenant ON asset_action_histories(tenant_id, asset_id, created_at);
```
