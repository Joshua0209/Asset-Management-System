# API Design

**Base URL:** `/api/v1`
**Auth:** Bearer token (JWT) in `Authorization` header for all endpoints except login/register.
**Content-Type:** `application/json` (except image upload: `multipart/form-data`).

---

## Endpoint Summary

### Auth

| Method | Path | Description | Access | FR |
|--------|------|-------------|--------|-----|
| POST | `/auth/register` | Self-register as a holder | Public | FR-01 |
| POST | `/auth/login` | Login | Public | FR-02 |
| GET | `/auth/me` | Get current user | Auth | FR-02 |
| POST | `/auth/users` | Create a user of any role | Manager | FR-01 |
| POST | `/auth/password-reset` | Request password reset *(not implemented — not required by `requirements.md`)* | Public | — |
| POST | `/auth/password-reset/confirm` | Confirm password reset *(not implemented — not required by `requirements.md`)* | Public | — |

### Assets

| Method | Path | Description | Access | FR | FSM |
|--------|------|-------------|--------|-----|-----|
| GET | `/assets` | List/search assets | Manager | FR-17 | — |
| GET | `/assets/mine` | My assigned assets | Holder | FR-18 | — |
| GET | `/assets/:id` | Get asset details | Manager/Owner | FR-17 | — |
| POST | `/assets` | Register new asset | Manager | FR-10–13 | T1 |
| PATCH | `/assets/:id` | Update asset info | Manager | FR-15 | — |
| POST | `/assets/:id/assign` | Assign to holder | Manager | FR-16 | T2 |
| POST | `/assets/:id/unassign` | Reclaim asset | Manager | FR-16 | T5 |
| POST | `/assets/:id/dispose` | Scrap asset | Manager | — | T3 |
| GET | `/assets/:id/history` | View audit trail | Manager | — | — |

### Repair Requests

| Method | Path | Description | Access | FR | FSM |
|--------|------|-------------|--------|-----|-----|
| POST | `/repair-requests` | Submit request + images | Holder | FR-20,21,30 | T4 |
| GET | `/repair-requests` | List requests | Both | FR-27,28 | — |
| GET | `/repair-requests/:id` | Get request details | Both | FR-31 | — |
| POST | `/repair-requests/:id/approve` | Approve request | Manager | FR-22,23 | T6 |
| POST | `/repair-requests/:id/reject` | Reject request | Manager | FR-22,24 | T7 |
| PATCH | `/repair-requests/:id/repair-details` | Fill repair details | Manager | FR-25 | — |
| POST | `/repair-requests/:id/complete` | Mark repair done | Manager | FR-26 | T8 |

### Images

| Method | Path | Description | Access | FR |
|--------|------|-------------|--------|-----|
| GET | `/images/:id` | Retrieve image | Auth | FR-31 |

### Users

| Method | Path | Description | Access | FR |
|--------|------|-------------|--------|-----|
| GET | `/users` | List users | Manager | FR-16 |

---

## Rate Limiting

Per NFR-12, all endpoints are rate-limited at **100 requests/minute per authenticated user** (configurable). Anonymous endpoints (`POST /auth/login`, `POST /auth/register`) are limited to **30 requests/minute per IP**. The image endpoint (`GET /images/:id`) gets a higher tier (300 req/min) because a holder browsing several repair requests with attachments can legitimately fan-out beyond the default.

`GET /health` is exempt — it serves liveness probes (compose healthcheck, ALB) that would otherwise DoS themselves under tight defaults.

Response headers on every request:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1744742400
```

When the budget is exhausted the response is the project error envelope with a `Retry-After` header:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/json

{"error": {"code": "rate_limit_exceeded", "message": "Rate limit exceeded: 100 per 1 minute"}}
```

### Implementation notes

- Library: [`slowapi`](https://slowapi.readthedocs.io/) (FastAPI-friendly, no Redis dependency). Storage is in-process memory per `docs/system-design/05-phase2-architecture.md` — Phase 2's ~4 QPS target makes per-worker counters acceptable.
- Bucket key: the limiter's `key_func` (`backend/app/core/rate_limit.py`) decodes the JWT inline so authenticated requests bucket as `user:<sub>`; anonymous requests fall back to `get_remote_address(request)`.
- The decoder runs *before* `get_current_user`, on purpose — slowapi middleware fires before route dependencies, so we can't read `request.state.user` here.
- 429 responses are rewrapped into the project error envelope by `register_rate_limit_handler` in `backend/app/main.py`. The handler must remain a **synchronous** `def`; `SlowAPIMiddleware.sync_check_limits` falls back to slowapi's plaintext default if the registered handler is `async`.

### Configuration

| Env var | Default | Effect |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Master kill switch. Set `false` in CI / load tests. |
| `RATE_LIMIT_AUTHENTICATED` | `100/minute` | Default tier (applied via `default_limits`). |
| `RATE_LIMIT_ANONYMOUS` | `30/minute` | Per-IP limit on `/auth/login` + `/auth/register`. |
| `RATE_LIMIT_IMAGES` | `300/minute` | Higher tier for `/images/:id`. |

---

## RBAC Summary

| Capability | Holder | Manager |
|-----------|--------|---------|
| View own assets | ✓ | — |
| View all assets | — | ✓ |
| Register/edit/assign assets | — | ✓ |
| Submit repair request | ✓ | — |
| View own repair requests | ✓ | — |
| View all repair requests | — | ✓ |
| Approve/reject/complete repairs | — | ✓ |
| View images on any request | ✓ | ✓ |

---

## Conventions

### Response Envelope

All responses use a consistent envelope:

```jsonc
// Success (single resource)
{
  "data": { /* resource object */ }
}

// Success (collection)
{
  "data": [ /* resource objects */ ],
  "meta": {
    "total": 142,
    "page": 1,
    "per_page": 20,
    "total_pages": 8
  }
}

// Error
{
  "error": {
    "code": "validation_error",       // machine-readable code
    "message": "Human-readable text",
    "details": [                      // optional, for field-level errors
      { "field": "email", "message": "Must be a valid email", "code": "invalid_format" }
    ]
  }
}
```

### Common Error Codes

| HTTP Status | `error.code` | When |
|-------------|-------------|------|
| 400 | `bad_request` | Bad request that is not a schema-validation failure |
| 401 | `unauthorized` | Missing or expired token |
| 403 | `forbidden` | Valid token but insufficient role |
| 404 | `not_found` | Resource does not exist (or soft-deleted) |
| 409 | `conflict` | Optimistic locking version mismatch |
| 409 | `duplicate_request` | Repair request already exists for this asset |
| 409 | `invalid_transition` | FSM transition not allowed from current state |
| 413 | `payload_too_large` | Request body exceeds the allowed upload size |
| 415 | `unsupported_media_type` | Content-Type is not one of the supported formats |
| 422 | `validation_error` | Malformed JSON, missing required field, or semantically invalid input |
| 429 | `rate_limit_exceeded` | Too many requests |
| 500 | `internal_server_error` | Unexpected server condition (e.g., corrupted asset code sequence) |
| 503 | `service_unavailable` | Transient backend failure (e.g., database error) |

### Optimistic Locking

Any request that modifies `assets`, `repair_requests`, or `users` **must** include the current `version` in the request body. The server checks `WHERE id = :id AND version = :version`. If 0 rows affected, the server returns:

```
HTTP/1.1 409 Conflict
{
  "error": {
    "code": "conflict",
    "message": "Resource was modified by another user. Please refresh and try again."
  }
}
```

### Pagination

Offset-based pagination for all list endpoints (sufficient for Phase 1-2 scale):

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `page` | 1 | — | Page number (1-indexed) |
| `per_page` | 20 | 100 | Items per page |

### Soft Delete

All queries filter by `deleted_at IS NULL` server-side. Deleted resources return `404`. There is no public "undelete" endpoint (admin-only operation).

### ID Format

- Internal IDs: UUID v4 (opaque, no information leakage)
- Asset business code: `asset_code` field (e.g., `AST-2026-00001`) — auto-generated by the server

### Timestamps

All timestamps are ISO 8601 in UTC: `2026-04-15T10:30:00Z`

---

## 1. Authentication (`/api/v1/auth`)

### 1.1 Register (Public Self-Registration — Holder Only)

```
POST /api/v1/auth/register
```

**Access:** Public

**Role policy:** The server always creates the new user with `role = "holder"`. Any `role` field in the request body is silently ignored. Managers are created by an existing manager via [1.6 Admin Create User](#16-admin-create-user).

**Bootstrap:** A constant-identity manager is seeded by `scripts/seed_demo_data.py` using the `BOOTSTRAP_MANAGER_*` env vars (see `backend/.env.example`). This solves the chicken-and-egg problem — at least one manager always exists after seeding.

**Request:**

```json
{
  "email": "alice@example.com",
  "password": "securePassword123",
  "name": "Alice Chen",
  "department": "IT"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | string | yes | Valid email, globally unique (a soft-deleted user still occupies the address) |
| `password` | string | yes | 8–128 chars, at least 1 letter + 1 digit |
| `name` | string | yes | 1–100 chars |
| `department` | string | yes | 1–100 chars |

**Response:** `201 Created`

```json
{
  "data": {
    "id": "a1b2c3d4-...",
    "email": "alice@example.com",
    "name": "Alice Chen",
    "department": "IT",
    "role": "holder",
    "version": 1,
    "created_at": "2026-04-15T10:30:00Z",
    "updated_at": "2026-04-15T10:30:00Z"
  }
}
```

**Errors:** `422` (malformed JSON or validation), `409` (email taken)

---

### 1.2 Login

```
POST /api/v1/auth/login
```

**Access:** Public

**Request:**

```json
{
  "email": "alice@example.com",
  "password": "securePassword123"
}
```

**Response:** `200 OK`

```json
{
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_at": "2026-04-15T22:30:00Z",
    "user": {
      "id": "a1b2c3d4-...",
      "email": "alice@example.com",
      "name": "Alice Chen",
      "role": "holder"
    }
  }
}
```

**Errors:** `401` (invalid credentials)

---

### 1.3 Get Current User

```
GET /api/v1/auth/me
```

**Access:** Authenticated

**Response:** `200 OK`

```json
{
  "data": {
    "id": "a1b2c3d4-...",
    "email": "alice@example.com",
    "name": "Alice Chen",
    "department": "IT",
    "role": "holder",
    "version": 1,
    "created_at": "2026-04-15T10:30:00Z",
    "updated_at": "2026-04-15T10:30:00Z"
  }
}
```

---

### 1.4 Password Reset — Request *(deferred — not in `requirements.md`)*

*Password reset is not an explicit requirement and is out of scope for the current build. This section is retained as a future-work placeholder.*

~~`POST /api/v1/auth/password-reset` — Public — always `202 Accepted` to prevent enumeration.~~

---

### 1.5 Password Reset — Confirm *(deferred — not in `requirements.md`)*

~~`POST /api/v1/auth/password-reset/confirm` — Public (with valid reset token).~~

---

### 1.6 Admin Create User

```
POST /api/v1/auth/users
```

**Access:** Manager

This endpoint is how managers promote/add other managers (since [1.1 Register](#11-register-public-self-registration--holder-only) is holder-only). Also usable to create holders with a pre-set password without going through self-registration.

**Request:**

```json
{
  "email": "newmanager@example.com",
  "password": "securePassword123",
  "name": "New Manager",
  "department": "Operations",
  "role": "manager"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | string | yes | Valid email, globally unique (a soft-deleted user still occupies the address) |
| `password` | string | yes | 8–128 chars, at least 1 letter + 1 digit |
| `name` | string | yes | 1–100 chars |
| `department` | string | yes | 1–100 chars |
| `role` | string | yes | `"holder"` or `"manager"` |

**Response:** `201 Created` with the same `UserRead` shape as [1.1 Register](#11-register-public-self-registration--holder-only).

**Errors:** `401` (no token), `403` (caller is not a manager), `409` (email taken), `422` (validation)

---

## 2. Assets (`/api/v1/assets`)

### 2.1 List Assets

```
GET /api/v1/assets
```

**Access:** Manager

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `per_page` | int | Items per page (default: 20, max: 100) |
| `q` | string | Full-text search across asset_code, name, model |
| `status` | string | Filter by status: `in_stock`, `in_use`, `pending_repair`, `under_repair`, `disposed` |
| `category` | string | Filter by category |
| `department` | string | Filter by department |
| `location` | string | Filter by location |
| `responsible_person_id` | uuid | Filter by assigned holder |
| `sort` | string | Sort field. Prefix `-` for descending. Default: `-created_at`. Allowed: `created_at`, `name`, `asset_code`, `purchase_date`, `status` |

**Response:** `200 OK`

```json
{
  "data": [
    {
      "id": "uuid-1",
      "asset_code": "AST-2026-00001",
      "name": "MacBook Pro 16\"",
      "model": "A2991",
      "category": "computer",
      "status": "in_use",
      "location": "Building A, Floor 3",
      "department": "Engineering",
      "responsible_person": {
        "id": "user-uuid",
        "name": "Alice Chen"
      },
      "assignment_date": "2026-02-01",
      "unassignment_date": null,
      "purchase_date": "2026-01-15",
      "purchase_amount": "79900.00",
      "warranty_expiry": "2029-01-15",
      "created_at": "2026-01-20T08:00:00Z",
      "version": 3
    }
  ],
  "meta": {
    "total": 87,
    "page": 1,
    "per_page": 20,
    "total_pages": 5
  }
}
```

---

### 2.2 Get Asset

```
GET /api/v1/assets/:id
```

**Access:** Manager, or Holder if they are the `responsible_person`

**Response:** `200 OK`

```json
{
  "data": {
    "id": "uuid-1",
    "asset_code": "AST-2026-00001",
    "name": "MacBook Pro 16\"",
    "model": "A2991",
    "specs": "M4 Max, 64GB RAM, 1TB SSD",
    "category": "computer",
    "supplier": "Apple Taiwan",
    "purchase_date": "2026-01-15",
    "purchase_amount": "79900.00",
    "location": "Building A, Floor 3",
    "department": "Engineering",
    "responsible_person": {
      "id": "user-uuid",
      "name": "Alice Chen",
      "email": "alice@example.com"
    },
    "assignment_date": "2026-02-01",
    "unassignment_date": null,
    "activation_date": "2026-01-20",
    "warranty_expiry": "2029-01-15",
    "status": "in_use",
    "disposal_reason": null,
    "created_at": "2026-01-20T08:00:00Z",
    "updated_at": "2026-03-10T14:22:00Z",
    "version": 3
  }
}
```

**Errors:** `404` (not found or soft-deleted)

**Field notes:**
- `assignment_date` (date, nullable) — supplied by the manager when assigning a holder (FSM T2), so the recorded date matches the real hand-off day rather than the API call timestamp. Reflects the **current** assignment only; reassigning overwrites it.
- `unassignment_date` (date, nullable) — supplied by the manager when reclaiming the asset (FSM T5). Must not be earlier than `assignment_date`. Cleared back to `null` on the next assign so it always pairs with the most recent unassignment.

---

### 2.3 Register New Asset (FSM T1: → `in_stock`)

```
POST /api/v1/assets
```

**Access:** Manager

**Request:**

```json
{
  "name": "MacBook Pro 16\"",
  "model": "A2991",
  "specs": "M4 Max, 64GB RAM, 1TB SSD",
  "category": "computer",
  "supplier": "Apple Taiwan",
  "purchase_date": "2026-01-15",
  "purchase_amount": "79900.00",
  "location": "Building A, Floor 3",
  "department": "Engineering",
  "activation_date": "2026-01-20",
  "warranty_expiry": "2029-01-15"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `name` | string | yes | 1–120 chars |
| `model` | string | yes | 1–120 chars |
| `specs` | string | no | Max 500 chars |
| `category` | string | yes | One of: `phone`, `computer`, `tablet`, `monitor`, `printer`, `network_equipment`, `other` |
| `supplier` | string | yes | 1–120 chars |
| `purchase_date` | string (date) | yes | ISO 8601 date, not in future |
| `purchase_amount` | string (decimal) | yes | Positive number, max 15 digits, max 2 decimal places |
| `location` | string | no | Max 120 chars |
| `department` | string | no | Max 100 chars |
| `activation_date` | string (date) | no | ISO 8601 date |
| `warranty_expiry` | string (date) | no | ISO 8601 date, must be after `purchase_date` |

> **Schema note:** the string-length caps mirror the underlying `assets` table column widths (`VARCHAR(120)` for `name` / `model` / `supplier` / `location`; `VARCHAR(100)` for `department`). Bumping any of these requires an Alembic migration on the matching column.

**Response:** `201 Created` with `Location: /api/v1/assets/:id`

```json
{
  "data": {
    "id": "new-uuid",
    "asset_code": "AST-2026-00042",
    "status": "in_stock",
    "version": 1,
    "...": "...all fields..."
  }
}
```

**Side effects:**
- `asset_code` auto-generated (format `AST-YYYY-NNNNN`, see [`backend/app/api/v1/endpoints/assets.py`](../../backend/app/api/v1/endpoints/assets.py))
- `status` set to `in_stock`
- `responsible_person_id` is `null`
- Audit log entry written to `asset_action_histories` 
**Errors:** `409 conflict` (asset_code collision after retry budget exhausted; FE should surface "please retry"), `422` (validation)

---

### 2.4 Update Asset Info

```
PATCH /api/v1/assets/:id
```

**Access:** Manager

**Request:** Partial update — only include fields to change plus `version`.

```json
{
  "location": "Building B, Floor 1",
  "department": "Marketing",
  "version": 3
}
```

| Field | Type | Required |
|-------|------|----------|
| `version` | int | **yes** (optimistic locking) |
| All other asset fields | various | no (only changed fields) |

**Constraints:**
- Cannot change `status` via this endpoint (use FSM action endpoints below)
- Cannot change `asset_code` (immutable after creation)
- Cannot change `responsible_person_id` via this endpoint (use assign/unassign)

**Response:** `200 OK`

```json
{
  "data": {
    "id": "uuid-1",
    "version": 4,
    "...": "...updated fields..."
  }
}
```

**Errors:** `409 conflict` (version mismatch), `422` (validation)

---

### 2.5 Assign Asset to Holder (FSM T2: `in_stock` → `in_use`)

```
POST /api/v1/assets/:id/assign
```

**Access:** Manager

**Request:**

```json
{
  "responsible_person_id": "holder-user-uuid",
  "assignment_date": "2026-04-15",
  "version": 1
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `responsible_person_id` | uuid | yes | Must reference an active user with role `holder` |
| `assignment_date` | string (date) | yes | ISO 8601 date, not in the future. Client-supplied so managers can backdate to the actual hand-off day. |
| `version` | int | yes | Current asset version |

**Preconditions (FSM T2):**
- Asset status is `in_stock`
- `responsible_person_id` is currently `null`

**Response:** `200 OK`

```json
{
  "data": {
    "id": "uuid-1",
    "status": "in_use",
    "responsible_person": {
      "id": "holder-user-uuid",
      "name": "Bob Lin"
    },
    "assignment_date": "2026-04-15",
    "unassignment_date": null,
    "version": 2
  }
}
```

**Side effects:**
- `assignment_date` stored from the request body
- `unassignment_date` cleared to `null`
- Audit log entry written 
**Errors:** `409 invalid_transition` (wrong state), `409 conflict` (version mismatch), `422` (invalid holder, missing/future `assignment_date`)

---

### 2.6 Unassign / Reclaim Asset (FSM T5: `in_use` → `in_stock`)

```
POST /api/v1/assets/:id/unassign
```

**Access:** Manager

**Request:**

```json
{
  "reason": "Employee transfer to another department",
  "unassignment_date": "2026-04-20",
  "version": 2
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `reason` | string | yes | 1–500 chars |
| `unassignment_date` | string (date) | yes | ISO 8601 date, not in the future, **and not earlier than the asset's current `assignment_date`**. Violations return `422` with `code: "invalid_unassignment_date"`. |
| `version` | int | yes | Current asset version |

**Preconditions (FSM T5):**
- Asset status is `in_use`
- No active repair requests (`pending_review` or `under_repair`)

**Response:** `200 OK`

```json
{
  "data": {
    "id": "uuid-1",
    "status": "in_stock",
    "responsible_person": null,
    "assignment_date": "2026-02-01",
    "unassignment_date": "2026-04-20",
    "version": 3
  }
}
```

**Side effects:**
- `unassignment_date` stored from the request body; `assignment_date` is preserved so the pair records the most recent assignment window
- Audit log entry written 
**Errors:** `409 invalid_transition` (active repair exists or wrong state), `409 conflict` (version mismatch), `422 invalid_unassignment_date` (date in future or earlier than `assignment_date`)

---

### 2.7 Scrap Asset (FSM T3: `in_stock` → `disposed`)

```
POST /api/v1/assets/:id/dispose
```

**Access:** Manager

**Request:**

```json
{
  "disposal_reason": "End of life — exceeded warranty by 2 years, repair cost exceeds replacement",
  "version": 3
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `disposal_reason` | string | yes | 1–500 chars |
| `version` | int | yes | Current asset version |

**Preconditions (FSM T3):**
- Asset status is `in_stock`
- No active repair requests
- `responsible_person_id` is `null`

**Response:** `200 OK`

```json
{
  "data": {
    "id": "uuid-1",
    "status": "disposed",
    "disposal_reason": "End of life — exceeded warranty by 2 years, repair cost exceeds replacement",
    "version": 4
  }
}
```

**Side effects:** Audit log entry written. Asset can no longer transition to any other state.

**Errors:** `409 invalid_transition` (asset not in_stock, has assigned holder, or active repair exists), `409 conflict` (version mismatch), `404` (not found or soft-deleted), `422` (validation)

---

### 2.8 My Assets (Holder View)

```
GET /api/v1/assets/mine
```

**Access:** Holder (returns only assets where `responsible_person_id = current_user.id`)

**Query Parameters:** Same as [2.1 List Assets](#21-list-assets) except `responsible_person_id` is fixed to the current user.

**Response:** Same shape as [2.1](#21-list-assets).

---

### 2.9 Asset Action History

`GET /api/v1/assets/:id/history`

**Access:** Manager

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number (default: 1) |
| `per_page` | int | Items per page (default: 20, max: 100) |

**Response:** `200 OK`

```json
{
  "data": [
    {
      "id": "history-uuid",
      "action": "assign",
      "from_status": "in_stock",
      "to_status": "in_use",
      "actor": {
        "id": "manager-uuid",
        "name": "Manager Wang"
      },
      "metadata": {
        "responsible_person_id": "holder-uuid",
        "responsible_person_name": "Alice Chen"
      },
      "created_at": "2026-02-01T09:00:00Z"
    }
  ],
  "meta": { "total": 5, "page": 1, "per_page": 20, "total_pages": 1 }
}
```

---

## 3. Repair Requests (`/api/v1/repair-requests`)

### 3.1 Submit Repair Request (FSM T4: asset `in_use` → `pending_repair`)

```
POST /api/v1/repair-requests
```

**Access:** Holder

**Request:** `multipart/form-data`, `application/json`, or `application/x-www-form-urlencoded` (the endpoint dispatches on `Content-Type`; only `multipart/form-data` accepts files).

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `asset_id` | uuid | yes | Must be an asset assigned to the current user |
| `fault_description` | string | yes | 1–1000 chars |
| `version` | int | no | Optional optimistic-lock token for the **asset** (not the repair request). When present, must match the asset's current `version`; a mismatch returns `409 conflict`. Omit this on first submit. |
| `images` | file[] | no | Max 5 files, each ≤ 5 MB, JPEG/PNG only. Magic-byte signature is verified against the declared `Content-Type` (PNG: `\x89PNG…`, JPEG: starts `\xff\xd8`, ends `\xff\xd9`); a mismatch returns `422`. |

**Preconditions (FSM T4):**
- Asset status is `in_use`
- Asset's `responsible_person_id` matches the current user
- No existing `pending_review` or `under_repair` request for this asset

**Response:** `201 Created` with `Location: /api/v1/repair-requests/:id`

```json
{
  "data": {
    "id": "repair-uuid",
    "repair_id": "REP-2026-00001",
    "asset": {
      "id": "asset-uuid",
      "asset_code": "AST-2026-00001",
      "name": "MacBook Pro 16\""
    },
    "requester": {
      "id": "holder-uuid",
      "name": "Alice Chen"
    },
    "status": "pending_review",
    "fault_description": "Screen flickering when connected to external monitor",
    "images": [
      {
        "id": "img-uuid-1",
        "url": "/api/v1/images/img-uuid-1",
        "uploaded_at": "2026-04-15T10:30:00Z"
      }
    ],
    "created_at": "2026-04-15T10:30:00Z",
    "version": 1
  }
}
```

**Side effects:**
- `repair_id` auto-generated by the server (format `REP-YYYY-NNNNN`, monotonically increasing within the calendar year — mirrors the `asset_code` scheme). Immutable after creation; provided primarily for human-readable display in the UI.
- Asset status changes to `pending_repair`
- Asset version incremented
- Images written via `ImageStorage`; on any DB failure after files were written, the endpoint's `finally` block cleans up the saved storage keys to avoid orphans
- Audit log entry written 
**Errors:** `404` (asset not found), `409 duplicate_request` (active request exists), `409 invalid_transition` (asset not in `in_use`), `409 conflict` (asset version mismatch), `413` (request body exceeds the multipart budget), `415` (unsupported `Content-Type`), `422` (validation, including image signature mismatch)

---

### 3.2 List Repair Requests

```
GET /api/v1/repair-requests
```

**Access:**
- **Manager:** sees all requests
- **Holder:** sees only own requests (server-side filter)

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number |
| `per_page` | int | Items per page |
| `status` | string | `pending_review`, `under_repair`, `completed`, `rejected` |
| `asset_id` | uuid | Filter by asset |
| `requester_id` | uuid | Filter by requester (manager only) |
| `sort` | string | Default: `-created_at`. Allowed: `created_at`, `status` |

**Response:** `200 OK`

```json
{
  "data": [
    {
      "id": "repair-uuid",
      "repair_id": "REP-2026-00001",
      "asset": {
        "id": "asset-uuid",
        "asset_code": "AST-2026-00001",
        "name": "MacBook Pro 16\""
      },
      "requester": {
        "id": "holder-uuid",
        "name": "Alice Chen"
      },
      "reviewer": null,
      "status": "pending_review",
      "fault_description": "Screen flickering when connected to external monitor",
      "created_at": "2026-04-15T10:30:00Z",
      "version": 1
    }
  ],
  "meta": { "total": 12, "page": 1, "per_page": 20, "total_pages": 1 }
}
```

---

### 3.3 Get Repair Request

```
GET /api/v1/repair-requests/:id
```

**Access:** Manager, or Holder if they are the requester

**Note:** Repair-request response bodies (here and in §3.4–3.7) include both
the embedded `asset`/`requester`/`reviewer` objects AND sibling
`asset_id`/`requester_id`/`reviewer_id` scalars for client convenience. Clients
that only need the foreign keys can use the scalars without unpacking the
embedded objects.

**Response:** `200 OK`

```json
{
  "data": {
    "id": "repair-uuid",
    "repair_id": "REP-2026-00001",
    "asset": {
      "id": "asset-uuid",
      "asset_code": "AST-2026-00001",
      "name": "MacBook Pro 16\""
    },
    "requester": {
      "id": "holder-uuid",
      "name": "Alice Chen"
    },
    "reviewer": {
      "id": "manager-uuid",
      "name": "Manager Wang"
    },
    "status": "under_repair",
    "fault_description": "Screen flickering when connected to external monitor",
    "rejection_reason": null,
    "repair_date": "2026-04-16",
    "fault_content": "GPU connector loose due to drop impact",
    "repair_plan": "Replace GPU ribbon cable and re-seat connector",
    "repair_cost": "3500.00",
    "repair_vendor": "Apple Authorized Service — Taipei",
    "completed_at": null,
    "images": [
      {
        "id": "img-uuid-1",
        "url": "/api/v1/images/img-uuid-1",
        "uploaded_at": "2026-04-15T10:30:00Z"
      }
    ],
    "created_at": "2026-04-15T10:30:00Z",
    "updated_at": "2026-04-16T09:00:00Z",
    "version": 3
  }
}
```

---

### 3.4 Approve Repair Request (FSM T6: asset `pending_repair` → `under_repair`)

```
POST /api/v1/repair-requests/:id/approve
```

**Access:** Manager

**Request:**

```json
{
  "version": 1
}
```

**Preconditions (FSM T6):**
- Repair request status is `pending_review`
- Associated asset status is `pending_repair`

**Response:** `200 OK`

```json
{
  "data": {
    "id": "repair-uuid",
    "status": "under_repair",
    "reviewer": {
      "id": "manager-uuid",
      "name": "Manager Wang"
    },
    "version": 2
  }
}
```

**Side effects:**
- Repair request status → `under_repair`
- Asset status → `under_repair`
- Both versions incremented
- `reviewer_id` set to current user
- Audit log entry written 

**Errors:** `409 conflict` (version mismatch), `409 invalid_transition` (request not pending_review or asset not pending_repair), `404` (not found)

---

### 3.5 Reject Repair Request (FSM T7: asset `pending_repair` → `in_use`)

```
POST /api/v1/repair-requests/:id/reject
```

**Access:** Manager

**Request:**

```json
{
  "rejection_reason": "Issue could not be reproduced. Please provide more details.",
  "version": 1
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `rejection_reason` | string | yes | 1–500 chars |
| `version` | int | yes | Current repair request version |

**Preconditions (FSM T7):**
- Repair request status is `pending_review`

**Response:** `200 OK`

```json
{
  "data": {
    "id": "repair-uuid",
    "status": "rejected",
    "rejection_reason": "Issue could not be reproduced. Please provide more details.",
    "reviewer": {
      "id": "manager-uuid",
      "name": "Manager Wang"
    },
    "version": 2
  }
}
```

**Side effects:**
- Repair request status → `rejected`
- Asset status → `in_use` (returns to normal)
- Audit log entry written 

**Errors:** `409 conflict` (version mismatch), `409 invalid_transition` (request not pending_review or asset not pending_repair), `404` (not found)

---

### 3.6 Fill Repair Details

```
PATCH /api/v1/repair-requests/:id/repair-details
```

**Access:** Manager

**Request:**

```json
{
  "repair_date": "2026-04-16",
  "fault_content": "GPU connector loose due to drop impact",
  "repair_plan": "Replace GPU ribbon cable and re-seat connector",
  "repair_cost": "3500.00",
  "repair_vendor": "Apple Authorized Service — Taipei",
  "version": 2
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `repair_date` | string (date) | no | ISO 8601 date |
| `fault_content` | string | no | Max 1000 chars |
| `repair_plan` | string | no | Max 1000 chars |
| `repair_cost` | string (decimal) | no | Non-negative, max 15 digits, max 2 decimal places |
| `repair_vendor` | string | no | Max 200 chars |
| `version` | int | yes | Current repair request version |

**Preconditions:** Repair request status is `under_repair`. The associated asset must also be in status `under_repair`.

**At-least-one rule:** The body **must** carry at least one repair-detail field in addition to `version`. A body of just `{"version": N}` is rejected with `422` — otherwise no columns would change, the row version would not advance, and the client's optimistic lock would silently stay current.

**Response:** `200 OK` with updated repair request.

**Note:** This endpoint only updates metadata. It does **not** change status. Use [3.7 Complete Repair](#37-complete-repair) to mark as done.

**Errors:** `409 conflict` (version mismatch), `409 invalid_transition` (request not under_repair or asset not under_repair), `404` (not found), `422` (no updatable field provided)

---

### 3.7 Complete Repair (FSM T8: asset `under_repair` → `in_use`)

```
POST /api/v1/repair-requests/:id/complete
```

**Access:** Manager

**Request:**

```json
{
  "repair_date": "2026-04-20",
  "fault_content": "GPU connector loose due to drop impact",
  "repair_plan": "Replaced GPU ribbon cable",
  "repair_cost": "3500.00",
  "repair_vendor": "Apple Authorized Service — Taipei",
  "version": 3
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `repair_date` | string (date) | yes | ISO 8601 date |
| `fault_content` | string | yes | 1–1000 chars |
| `repair_plan` | string | yes | 1–1000 chars |
| `repair_cost` | string (decimal) | yes | Non-negative, max 15 digits, max 2 decimal places |
| `repair_vendor` | string | yes | 1–200 chars |
| `version` | int | yes | Current repair request version |

**Preconditions (FSM T8):**
- Repair request status is `under_repair`
- All required repair detail fields provided

**Response:** `200 OK`

```json
{
  "data": {
    "id": "repair-uuid",
    "status": "completed",
    "completed_at": "2026-04-20T15:00:00Z",
    "version": 4
  }
}
```

**Side effects:**
- Repair request status → `completed`, `completed_at` set
- Asset status → `in_use`
- `responsible_person_id` unchanged
- Audit log entry written 

**Errors:** `409 conflict` (version mismatch), `409 invalid_transition` (request not under_repair, or associated asset not under_repair), `404` (not found), `422` (validation)

---

## 4. Images (`/api/v1/images`)

### 4.1 Get Image

```
GET /api/v1/images/:id
```

**Access:** Authenticated (any role — images are viewable by all authenticated users per FR-31)

**Response:** `200 OK` — binary image data with appropriate `Content-Type` header (`image/jpeg` or `image/png`). Sets `Cache-Control: private, max-age=3600`.

**Errors:** `401` (unauthenticated), `404` (image not found, owning repair-request soft-deleted, or backing file missing).

**Note:** Image upload is handled as part of repair request submission ([3.1](#31-submit-repair-request)). There is no standalone upload endpoint.

**Storage abstraction (implementation note).** Repair images are persisted via `app.services.image_storage.ImageStorage` — a Protocol with a `LocalImageStorage` implementation rooted at `REPAIR_UPLOAD_DIR`. The `repair_images.image_url` column stores a **backend storage key** (`"<rr-id>/<img-id>.<ext>"`), not a public URL; the public URL `/api/v1/images/<id>` is derived at the schema layer (`RepairImageRead.url`). A future S3 backend can drop in by swapping the storage implementation without migrating any DB rows.

---

## 5. Users (`/api/v1/users`)

### 5.1 List Users

```
GET /api/v1/users
```

**Access:** Manager (used for asset assignment — look up holders)

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | int | Page number |
| `per_page` | int | Items per page |
| `role` | string | Filter by `holder` or `manager` |
| `department` | string | Filter by department |
| `q` | string | Search by name or email |

**Response:** `200 OK`

```json
{
  "data": [
    {
      "id": "user-uuid",
      "email": "alice@example.com",
      "name": "Alice Chen",
      "department": "Engineering",
      "role": "holder",
      "version": 1,
      "created_at": "2026-04-15T10:30:00Z",
      "updated_at": "2026-04-15T10:30:00Z"
    }
  ],
  "meta": { "total": 45, "page": 1, "per_page": 20, "total_pages": 3 }
}
```
