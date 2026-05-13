# Asset Management System — Development Roadmap

**Team:** 5 people (2 Backend, 3 Frontend at start)
**Timeline:** Apr 14 – Jun 2 (buffer week: May 26 – Jun 2)
**Scope:** Phase 2 architecture implementation + live demo + slides + report
**Tech Stack:** React + Vite (FE) + FastAPI + SQLAlchemy + MySQL (BE), monorepo

---

## Timeline Overview

```
Week 1  Apr 14–18  ██████████  Foundation & CI Setup           5 dev (2 BE + 3 FE)
Week 2  Apr 21–25  ██████████  Auth & Core Features Start      5 dev (2 BE + 3 FE)
Week 3  Apr 28–02  ██████████  Core Features Complete          5 dev (2 BE + 3 FE)
Week 4  May 05–09  ██████████  Advanced Features & Integration 5 dev (2 BE + 3 FE)
Week 5  May 12–16  ██████████  Infra + Testing + Polish        2 dev + 2 infra/test + 1 QA
Week 6  May 19–23  ██████████  Harden + Demo Prep              1 dev + 2 infra/test + 2 pres
Buffer  May 26–02  ░░░░░░░░░░  Buffer & Presentation           1 dev + 4 pres/polish
        May 26     ▶ Rehearsal
        Jun 02     ▶ Presentation
```

**Status (2026-05-13):** W1–W4 done. **W5 active (Tue).** W4 closed with backend fully delivered (audit log, composite indexes, optimistic-locking pin tests, rate limiting + CORS) and FE mostly delivered (issue #29 dropdown, manager review detail page, full i18n parity, granular 409 error surfacing). **One FE item carries into W5:** multi-dimensional search/filter UI on `AssetList.tsx` (backend already shipped).

---

## Week 1 — Foundation & CI Setup (Apr 14–18) — **Mostly Done**

**Goal:** Everyone can run the project locally, CI is green on every push, and scaffolding is ready for feature work next week.

**Resources:** 2 BE + 3 FE (all 5)

**Status summary:** Backend fully delivered. Frontend delivered React+Vite + i18n + CI, but **UI library pick** and **layout shell** slipped to Week 2. Security pipeline exceeded plan: SonarQube (originally Week 5) landed in Week 1 via PR #4.

### Backend (2 people) — ✅ Done

| Task | Status | Notes |
|------|--------|-------|
| Monorepo setup | ✅ Done | `backend/` + `frontend/`, OpenAPI at `/docs` (a0dfd95) |
| FastAPI project scaffold + MySQL schema | ✅ Done | 4 tables via Alembic, `version` column on mutable tables (a0dfd95) |
| Seed script with demo data | ✅ Done | 50 assets, 2 managers + 2 holders, 10 repair requests across all statuses (a0dfd95, hardened in 11c2d43) |
| CI pipeline: backend | ✅ Done | `ruff` + `mypy --strict` + `pytest --cov` on every push/PR (PR #3). **Note:** ruff replaced Flake8 |

### Frontend (3 people) — ⚠ Partial

| Task | Status | Notes |
|------|--------|-------|
| React + Vite project in monorepo | ✅ Done | TypeScript strict, `react-router-dom` v6 (a0dfd95) |
| UI library setup (Ant Design / shadcn) | ❌ Not done | **Carried to Week 2.** Open decision — confirm with team before picking |
| i18n framework (`react-i18next`) | ✅ Done | zh-TW + en, browser language detector, `LanguageSwitcher` component (PR #6) |
| Layout: sidebar nav, header (no auth guard yet) | ❌ Not done | **Carried to Week 2.** `App.tsx` still a placeholder hero card |
| CI pipeline: frontend | ✅ Done | ESLint 9 (flat config) + `tsc --noEmit` + vitest + `vite build` (PR #3) |

### CI & Security Gates (shared effort) — ✅ Done + scope pulled forward

| Task | Status | Notes |
|------|--------|-------|
| GitHub Actions workflow | ✅ Done | 5 jobs: backend, frontend, secrets, sast, sonarqube (PR #3) |
| gitleaks pre-commit hook | ✅ Done | Pre-commit + CI secrets job (PR #3) |
| Semgrep basic SAST | ✅ Done | OWASP top-10 rules in CI (PR #3) |
| SonarQube / SonarCloud quality gate | ✅ Done (pulled from Week 5) | Consumes FE+BE coverage artifacts. BLOCKER/CRITICAL/MAJOR findings resolved (PR #4) |
| Reviewer auto-assignment | ✅ Bonus | Workflow-based round-robin by path ownership (`.github/workflows/assign-reviewers.yml`) |

### Milestone: `M1 — Skeleton Running`
- [x] Local dev scripts start both FE and BE (`docker compose up -d mysql` + `uvicorn` / `npm run dev`)
- [x] DB schema deployed with seed data
- [x] FastAPI auto-generated docs available at `/docs`
- [x] CI pipeline runs lint + type-check + tests + secret scan + SAST + SonarQube on every push
- [x] No auth yet — that's Week 2
- [x] **Carry-over closed:** UI library picked and layout shell rendered

---

## Week 2 — Auth & Core Features Start (Apr 21–25) — **Mostly Done**

**Goal:** Auth works end-to-end. Asset CRUD and repair workflow APIs started. Frontend carry-over (UI library + layout shell) unblocks all feature pages.

**Resources:** 2 BE + 3 FE

**Status summary:** Backend fully delivered (PR #14): Auth + Asset CRUD + Repair Request submit/list, all with FSM validation. Frontend Week 1 carry-overs (UI library + layout shell) closed early (PR #8); asset list page landed against a mock dataset (PR #11). Week 2 FE carry-over reviews are complete in Week 3: login/register, repair submit form, and auth guard are merged. Asset list API wiring remains pending.

### Backend (2 people) — ✅ Done

| Task | Status | Notes |
|------|--------|-------|
| Auth API (register, login, JWT) | ✅ Done | `POST /auth/register` (holder-only), `POST /auth/login`, `GET /auth/me`, `POST /auth/users` (manager-only); JWT HS256; RBAC deps `CurrentUser`/`ManagerUser`/`HolderUser`; 76 tests, 96% coverage |
| Asset CRUD APIs (create, read, update, list) | ✅ Done | Pagination + basic filtering; `POST /assets` registers real assets with server-generated asset codes (replaced 501 stub from 11c2d43). Optimistic locking on update via `version` column |
| Repair Request APIs (submit + list) | ✅ Done | Submit + list endpoints with server-side FSM validation per `11-asset-fsm.md`. Full review/approve/complete workflow rolls into Week 3 |
| Input validation + error handling | ✅ Done | Global `HTTPException` handler returns `{"error": {"code": ..., "message": ...}}` envelope; Pydantic schemas in `app/schemas/` |

### Frontend (3 people) — ⚠ Partial (asset list API wiring pending)

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| **[Carry-over]** UI library setup | ✅ Done | FE-1 | Ant Design v6 (`antd` + `@ant-design/icons`), theme toggle via `ConfigProvider` (PR #8) |
| **[Carry-over]** Layout shell: sidebar nav + header | ✅ Done | FE-1 | Collapsible sidebar + header + theme switch using Ant Design `Layout` (PR #8) |
| Asset list page (table + pagination) | ✅ Done (mock data) | FE-1 | Ant Design table + client-side pagination + status tags (PR #11). **Reads from `frontend/src/mocks/assets.ts`** — wiring to real `GET /assets` API is a Week 3 carry-over |
| Login / Register pages | ✅ Done | FE-2 | PR #12 (`fe/auth`) merged after review; connected to real auth API with zh-TW + en strings |
| Repair request: submit form | ✅ Done | FE-2 | PR #13 (`fe/repair-request-submit-form`) merged after review; asset ID, fault description, image upload (max 5) |
| Auth guard + role-based routing | ✅ Done | FE-3 | Merged after review; holder is redirected away from manager-only pages |

### Milestone: `M2 — Auth + CRUD Basics`
- [x] UI library picked and theme tokens wired (Week 1 carry-over closed)
- [x] Layout shell renders on every route (sidebar + header)
- [x] Manager can register an asset (backend API)
- [x] Login/register works end-to-end
- [x] Holder can view own assets ~~(frontend list reads from mocks; needs `/assets/mine` wiring)~~ — closed in PR #19, AssetList now reads `/assets/mine` for holders
- [x] Holder can submit a repair request
- [x] Role-based access enforced on FE + BE

---

## Week 3 — Core Features Complete (Apr 28 – May 2) — **Done (with bonus scope; image display in flight)**

**Goal:** All CRUD operations and the full repair workflow work end-to-end.

**Resources:** 2 BE + 3 FE

**⚠ Carry-over from Week 2 (current):** Frontend review tasks are complete — login/register (PR #12), repair submit form (PR #13), and auth guard/role routing are done. Asset List still reads from `frontend/src/mocks/assets.ts` and remains pending real `GET /assets` and `GET /assets/mine` wiring.

**Status update (2026-05-06):** All five core M3 outcomes shipped. Week 3 effectively ran through May 6 — seven PRs (#22, #23, #24, #25, #26, #27, #28) merged after the May 2 calendar window, including PR #27 (FE-2 image display on repair detail) which closed the last open M3 outcome. **One item carries into Week 4:** [issue #29](https://github.com/Joshua0209/Asset-Management-System/issues/29) (holders need an asset-code dropdown on the repair-submit form), filed during today's W3 integration smoke test.

**FE task division for Week 3 (new):** the three FE engineers split by audience and responsibility, not by feature.

- **FE-1 — Manager surface owner.** Builds every page a manager interacts with: asset registration/edit, asset assignment, repair review/approve/reject, repair completion.
- **FE-2 — Holder surface owner.** Builds every page a holder interacts with: own-assets view, asset detail, repair request list + detail, image display on repair detail.
- **FE-3 — Integration & quality owner.** Lands the auth guard PR, performs PR review for FE-1 and FE-2, owns vitest coverage on new pages, wires shared concerns (i18n strings, error handling, loading/empty states) across the codebase, and acts as the merge coordinator to keep `main` green.

### Week 2 carry-over closure (Mon–Tue, FE only)

| Task | Status | Target | Owner | Notes |
|------|--------|--------|-------|-------|
| Land PR #12 — Login / Register pages | ✅ Done | Mon | FE-2 → FE-3 reviews | Review complete and merged. Unblocked auth guard work |
| Land PR #13 — Repair request submit form | ✅ Done | Mon | FE-2 → FE-3 reviews | Review complete and merged |
| Open + land PR for auth guard + role-based routing | ✅ Done | Mon–Tue | FE-3 (author) → FE-1 reviews | Review complete and merged; role-based route protection is active |
| Wire Asset List to real `GET /assets` API | ✅ Done (PR #19) | Mon–Tue | FE-1 → FE-3 reviews | ~~Asset list still uses `frontend/src/mocks/assets.ts`; real `/assets` + `/assets/mine` wiring is outstanding~~ Merged; manager reads `/assets`, holder reads `/assets/mine`. Mock runtime kept behind `VITE_USE_MOCK_AUTH` |

### Backend (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Repair Request APIs (full workflow) | Mon–Wed | Complete state machine: `pending_review → under_repair → completed` and `pending_review → rejected`. All FSM transitions validated server-side. **✅ Done (PR #16)** |
| Image upload + retrieval endpoint | Wed–Thu | ✅ Done (PR #22). Upload bundled into `POST /repair-requests` (multipart, ≤5 files × 5 MB, JPEG/PNG). Retrieval via `GET /api/v1/images/:id` (auth required, FR-31 — any role). Persistence abstracted behind `ImageStorage` Protocol with `LocalImageStorage` impl; S3 swap in Week 5 only touches `app/services/image_storage.py`. DB column `repair_images.image_url` stores a backend storage key, not a public URL — the public URL is computed in `RepairImageRead.url` |
| Asset assign/unassign/dispose | Thu–Fri | FSM transitions T2 (assign), T5 (unassign), T3 (dispose). **✅ Done (PR #17)** |
| API documentation review | Fri | Verify FastAPI auto-docs match `12-api-design.md` contract. **✅ Done (PR #28)** — error envelopes on protected routes, 422 envelope on manual validation, UUID format on path params, multipart `requestBody` for `POST /repair-requests`, image content-type for `GET /images/:id`, full pagination + filters on `GET /users`. `GET /assets/:id/history` deferred to Week 4 audit-log scope |

**Bonus scope landed mid-week (not in original plan):**

| Task | PR | Notes |
|------|----|-------|
| Docker compose dev stack | PR #24 | `mysql` + `backend` + `frontend` with bind-mount hot-reload, anonymous `node_modules` volume, named `backend_uploads` volume. Pulled forward from Week 5 |
| Granular 409 error codes | PR #24 | Distinct codes for version conflict vs. state conflict vs. duplicate. `app/main.py` global handler unpacks structured `detail={"code": ..., "message": ...}` payloads into the `{"error": {...}}` envelope |
| Login 500 LookupError fix | PR #23 | Enum value mismatch on legacy seed rows surfaced as a 500 during login; fixed and locked in with regression test |
| Pin Node 22 across local + CI | PR #21 | `package.json#engines` + lockfile + CI workflow all pinned to Node 22 |

### Frontend — Wed–Fri (compressed scope, audience-split)

#### FE-1 — Manager pages

| Task | Target | Notes |
|------|--------|-------|
| Asset create / edit pages | Wed–Thu | Form validation, category dropdown (2-level flat list), purchase amount + warranty expiry validation matching backend Pydantic schema. **✅ Done (PR #20)** — implemented inside `frontend/src/pages/AssetList.tsx` |
| Asset assign / unassign UI | Thu | FSM transitions T2/T5 — manager picks holder from user list, sets assignment date. **✅ Done (PR #20)** |
| Asset dispose flow | Thu | FSM transition T3 — confirm dialog with reason; status → `disposed`. **✅ Done (PR #20)** |
| Repair review/approve/reject UI | Thu–Fri | Approve → fill repair plan form (vendor, planned cost, planned date). Reject → confirm dialog with reason. Drives FSM `pending_review → under_repair` or `pending_review → rejected`. **✅ Done (PR #20)** — `frontend/src/pages/Reviews.tsx` |
| Repair complete UI | Fri | Fill repair date, content, actual cost, vendor → mark complete. Drives FSM `under_repair → completed`. **✅ Done (PR #20)** |

#### FE-2 — Holder pages

| Task | Target | Notes |
|------|--------|-------|
| Asset detail page | Wed | Read-only view of asset metadata; manager view (FE-1) enables edit/assign actions, holder view shows own-asset detail only. **✅ Done (PR #25)** — `AssetDetail.tsx` |
| My assets list (holder view) | Wed | Wraps the same table component as the shared list page but reads from `GET /assets/mine`. **✅ Done (PR #25)** — `MyAssetList.tsx` |
| Repair request list page | Wed–Thu | Status badges, sortable columns. Manager sees all; holder sees own only — same component, role-aware filter. **✅ Done (PR #26)** — `RepairRequestList.tsx` |
| Repair request detail page | Thu–Fri | Timeline view of workflow stages, status transitions, manager comments. **✅ Done (PR #26)** — `RepairRequestDetail.tsx` |
| Image display on repair detail page | Fri | Thumbnail grid, click-to-enlarge modal. **Risk:** depends on backend image upload endpoint landing Wed–Thu — fall back to placeholder thumbnails using mock URLs if BE slips, real wiring lands first thing W4. **✅ Done (PR #27, merged 2026-05-06)** — risk materialized but recovered: new `AuthImage` component fetches protected images via authenticated `apiClient` and manages Blob URL lifecycle. Slipped past Fri but landed on the first day of W4 as planned |

#### FE-3 — Integration & quality

| Task | Target | Notes |
|------|--------|-------|
| PR review for FE-1 and FE-2 work | Rolling | Same-day turnaround on PR review to keep FE-1/FE-2 unblocked. Owns the "PR review SLA" for the FE side this week. **✅ Done** — review chain `#19 → #20`, `#25 → #26 → #27` flagged in PR titles |
| Merge coordination | Rolling | Resolve merge conflicts between FE-1/FE-2 branches (likely on shared layout, routing, i18n keys). Keep `main` green. **✅ Done** |
| vitest coverage on new pages | Wed–Fri | Each new page ships with at least one render test + one role-gating test. Target: maintain ≥ 80% FE coverage as new pages land. **✅ Done** — see `frontend/src/__tests__/` |
| i18n keys (zh-TW + en) for all new pages | Rolling | Audit `src/i18n/locales/` after each PR merges; no hardcoded user-facing strings. **✅ Done** |
| Cross-cutting UX: loading, empty, error states | Thu–Fri | Consistent patterns across manager + holder pages. Hooks into Ant Design's `Spin`, `Empty`, `notification`. **✅ Done** |
| Optional: integration smoke test against real backend | Fri | If schedule allows, manual run-through of the 3 critical flows (manager registers asset, holder submits repair, manager completes) end-to-end before week close. **✅ Done** — surfaced [issue #29](https://github.com/Joshua0209/Asset-Management-System/issues/29) (asset-code dropdown UX gap), exactly the kind of integration bug the smoke test is meant to catch |

### Milestone: `M3 — Feature Complete (Core)`
- [x] Manager can register asset, assign to holder
- [x] Holder can view own assets, submit repair request with images _(submit works; see [issue #29](https://github.com/Joshua0209/Asset-Management-System/issues/29) for the asset-code UX gap that surfaced during smoke testing)_
- [x] Manager can approve/reject repair, fill details, complete repair
- [x] Status transitions update asset status automatically
- [x] Images upload and display on repair detail page _(upload ✅ via PR #22; display ✅ via PR #27, merged 2026-05-06)_

---

## Week 4 — Advanced Features & Integration (May 5–9) — **Done (one FE carry-over)**

**Goal:** All advanced features working. System fully integrated and polished.

**Resources:** 2 BE + 3 FE

**Status (2026-05-13):** Backend fully shipped — audit log + `GET /assets/:id/history`, composite indexes, optimistic-locking pin tests, rate limiting + CORS tightening. FE shipped issue #29 dropdown, the manager review detail page, full i18n parity (212 keys × 2 locales), and granular 409 surfacing via `formatApiError`. **One real carry-over into W5:** multi-dimensional search/filter UI on `AssetList.tsx` (BE filter API already accepts every dimension).

**Carry-over from Week 3 (FE) — closed:**

| Task | Owner | Target | Notes |
|------|-------|--------|-------|
| **Resolve [issue #29](https://github.com/Joshua0209/Asset-Management-System/issues/29)** — asset-code dropdown on repair-submit form | FE-2 | Wed–Thu | ✅ Done (PR [#52](https://github.com/Joshua0209/Asset-Management-System/pull/52), merged 2026-05-13). `SubmitRepairRequest.tsx` now fetches `GET /assets/mine` and renders a `Select` showing `asset_code — name`. Holder happy path is unblocked end-to-end |

### Backend (2 people) — ✅ Done

| Task | Target | Notes |
|------|--------|-------|
| Composite SQL indexes for asset search | Mon–Wed | ✅ Done (PR [#46](https://github.com/Joshua0209/Asset-Management-System/pull/46)). New Alembic migration `20260511_0004_add_composite_indexes.py` adds Phase 2 indexes per `07-database-design.md § Index Strategy`. Backend filter API itself already shipped earlier (`assets.py:140`) — `q`, `status`, `category`, `department`, `location`, `responsible_person_id` |
| Optimistic locking verification pass | Mon | ✅ Done (PR [#45](https://github.com/Joshua0209/Asset-Management-System/pull/45)). 9 pin tests added, granular 409 codes documented per endpoint (4 in `assets.py`, 5 transitions in `repair_requests.py`). Codes consumed by FE via `formatApiError` |
| Audit log + `GET /assets/:id/history` | Wed–Thu | ✅ Done (PR [#38](https://github.com/Joshua0209/Asset-Management-System/pull/38), refined by [#49](https://github.com/Joshua0209/Asset-Management-System/pull/49) discriminated union + [#50](https://github.com/Joshua0209/Asset-Management-System/pull/50) `asset_deleted_at` meta). Every FSM transition writes an `asset_action_histories` row in the same transaction; manager-only paginated read endpoint exposes the trail. Implements design decision Q13; deferred from W3 PR #28 |
| API hardening: rate limiting + CORS | Thu–Fri | ✅ Done (PR [#39](https://github.com/Joshua0209/Asset-Management-System/pull/39), merged 2026-05-13 03:47Z). `slowapi` configured with three tiers — authenticated (100/min), anonymous on auth endpoints (30/min/IP), images (300/min for attachment fan-out). CORS `methods` + `headers` allowlists narrowed to actual surface area; env-driven for prod-vs-dev. Master kill switch via `RATE_LIMIT_ENABLED` for load tests |

**Bonus scope landed mid-week (not in original plan):**

| Task | PR | Notes |
|------|----|-------|
| Assignment dates + `repair_id` field on assets | PR [#37](https://github.com/Joshua0209/Asset-Management-System/pull/37) | Tracks when each assignment/unassignment occurred and which repair currently owns the asset. Migration `20260506_0004_add_assignment_dates_and_repair_id.py` |
| Manager review workflow moved to full detail page | PR [#44](https://github.com/Joshua0209/Asset-Management-System/pull/44) | Replaces inline modal with `ReviewDetail.tsx` route — better for long repair plans + audit context |
| Manager asset actions consolidated on Asset Detail | PR [#43](https://github.com/Joshua0209/Asset-Management-System/pull/43) | Edit/assign/dispose actions all live on `AssetDetail.tsx`; removes Antd deprecation warnings |
| Model registry hardening | PR [#48](https://github.com/Joshua0209/Asset-Management-System/pull/48) | Eagerly registers all model modules in `app/models/__init__.py` to prevent mapper-init failures in scripts |
| Seed-image binary fix | PR [#51](https://github.com/Joshua0209/Asset-Management-System/pull/51) | Replaced placeholder JPEG with valid JFIF binary so seed data passes image-type validation |

### Frontend (3 people) — ⚠ Partial (multi-dim search UI carries)

| Task | Target | Notes |
|------|--------|-------|
| Search & filter UI (multi-dimensional) | Mon–Wed | ❌ Not done — **carries to W5.** `AssetList.tsx` still has no search/filter primitives. BE accepts the full filter set; the FE bar is the entirety of the remaining work. Status filter on `Reviews.tsx` is in place (1-dim) but does not satisfy the M4 multi-dim requirement |
| Optimistic locking conflict UI | Wed–Thu | ✅ Done at envelope level. `utils/apiErrors.ts` maps every granular 409 code (`conflict`, `duplicate_request`, `invalid_transition`, `validation_error`, `payload_too_large`, `unsupported_media_type`, `rate_limit_exceeded`) into translated messages via `formatApiError`. Both locales carry `errors.conflict` = "This record was modified by someone else. Please refresh and try again." The purpose-built refresh-button modal was not built — flagged as a W6 polish item if needed |
| i18n: all pages translated | Thu–Fri | ✅ Done. 212 keys × 2 locales (en, zh-TW), perfect parity. 8 sections: `common`, `auth`, `validation`, `errors`, `assetList`, `reviews`, `repairRequestList`, `repairRequestDetail`. Zero hardcoded user-facing strings |
| UX polish: loading states, empty states, error toasts | Rolling | ✅ Done. Consistent Antd `Spin`/`Empty`/`notification` patterns across manager + holder surfaces, surfaced from FE-3 work in W3 and reinforced by PR #43/#44 |

### Milestone: `M4 — Feature Complete (Full)`
- [x] M3 carry-over closed: issue #29 fixed (PR [#52](https://github.com/Joshua0209/Asset-Management-System/pull/52))
- [x] Audit log (`asset_action_histories`) + `GET /assets/:id/history` shipped (PR [#38](https://github.com/Joshua0209/Asset-Management-System/pull/38))
- [x] Optimistic locking: concurrent edit shows conflict to second user — translated error message via `formatApiError` for every 409 code (PR [#45](https://github.com/Joshua0209/Asset-Management-System/pull/45) pinned + documented the codes). _Note: dedicated refresh-button modal still pending if needed for demo polish_
- [x] All UI text is i18n-ready (language switcher works) — 212-key parity, zh-TW + en, audited 2026-05-13
- [x] Rate limiting active on all endpoints (PR [#39](https://github.com/Joshua0209/Asset-Management-System/pull/39))
- [ ] **Multi-dimensional search works with all filter combinations** — BE shipped (composite indexes + filter API); **FE filter bar carries into W5**
- [ ] No broken flows end-to-end — depends on E2E run in W5

---

## Week 5 — Infra + Testing + Polish (May 12–16) — **Active (Tue)**

**Goal:** App is Dockerized, deployed to AWS, CI/CD pipeline green, test coverage ≥ 80%.

**Status (2026-05-13):** W5 just kicked off after a late W4 close (PR #39 + #52 both merged on May 13). The resource shift now applies — five engineers redistribute into 2 dev seats (bug fixes + W4 search-UI carry-over), 2 infra seats (Docker prod + AWS), and 1 QA seat (E2E + manual testing). Search-UI carry-over from W4 is the only feature gap; everything else is hardening, deployment, and verification.

**In-flight infra work on `feat/cicd-prod-pipeline` (not yet PR'd):** 6 commits already code-complete most of the W5 infra checklist — production multi-stage Dockerfiles (BE: gunicorn + UvicornWorker + non-root; FE: nginx:alpine), `/health` (liveness) + `/ready` (DB `SELECT 1`, 503 on failure), `S3ImageStorage` behind the existing `ImageStorage` Protocol (selected via `REPAIR_IMAGE_BACKEND=s3`), full SCA gates (pip-audit + npm audit + OWASP Dependency-Check), and a deploy workflow (`.github/workflows/deploy.yml`) that builds → pushes to ECR → renders ECS task defs → rolling update with `wait-for-service-stability`. Auth uses GitHub OIDC (no long-lived AWS keys). **Architecture pivot:** EC2 ×2 → ECS Fargate (cheaper, no manual orchestration). Task defs committed under `infra/ecs/` with placeholders documented in `infra/ecs/README.md`. **Pending operator action** (not code): AWS provisioning of ECR repos + ECS cluster/service + RDS Multi-AZ + S3 bucket + OIDC IAM role, and `ACCOUNT_ID` / `REGION` substitution after `terraform apply`.

**Carry-over from W4 (FE):**

| Task | Owner | Target | Notes |
|------|-------|--------|-------|
| **Multi-dimensional search/filter UI** on `AssetList.tsx` | Dev seat (FE) | Mon–Tue | Filter bar with text search (`q`) + dropdowns (`status`, `category`, `department`, `location`, `responsible_person_id`). Debounced; URL-state-driven so refresh preserves filters. BE filter API + composite indexes (PR #46) already in place — this is pure FE. Closes the last open M4 outcome |

**Resources shift:**

| Role | People | Focus |
|------|--------|-------|
| Dev (bug fixes + W4 carry-over) | 2 | Fix issues found during testing, edge cases, ship the search/filter UI |
| Infra / DevOps | 2 | Docker prod images, AWS, CI/CD, monitoring |
| QA / Testing | 1 | E2E tests, manual testing |

### Infra (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Dockerize FE + BE (multi-stage builds) | Mon–Tue | **✅ Code-complete on `feat/cicd-prod-pipeline`.** `backend/Dockerfile.prod` (gunicorn + UvicornWorker, slim final stage, non-root) and `frontend/Dockerfile.prod` (nginx:alpine serving Vite build with SPA fallback + asset cache headers). Dev compose stack (W3 PR #24) stays separate. PR + merge still required |
| AWS setup: ECS Fargate + ALB + RDS Multi-AZ | Tue–Thu | **Pending operator action.** Architecture pivoted from "EC2 ×2 + manual orchestration" to ECS Fargate (cheaper, less ops surface). Task definitions committed on the branch under `infra/ecs/`; ECR repos + ECS cluster/service + RDS Multi-AZ + S3 bucket + OIDC IAM role still need to be provisioned (Terraform skeleton TBD). See `infra/ecs/README.md` for required GitHub Actions secrets/vars |
| CI/CD pipeline expansion (deploy) | Wed–Thu | **✅ Code-complete on `feat/cicd-prod-pipeline`.** `.github/workflows/deploy.yml` triggers on push to `main`: builds both prod images, pushes to ECR (cached layers via `docker/build-push-action`), then renders task defs and runs ECS rolling update with `wait-for-service-stability`. Auth via GitHub OIDC — no long-lived AWS keys |
| Zero-downtime rolling deploy | Thu–Fri | **✅ Code-complete on `feat/cicd-prod-pipeline`.** `aws-actions/amazon-ecs-deploy-task-definition` with `wait-for-service-stability: true` blocks until the new task set passes ALB health checks (10-min timeout). Backend `/ready` endpoint returns 503 on DB failure so ALB can drain a bad target during RDS Multi-AZ failover without killing the container |
| S3 bucket for images | Wed | **✅ Code-complete on `feat/cicd-prod-pipeline`.** `S3ImageStorage` lives next to `LocalImageStorage` behind the existing `ImageStorage` Protocol; selected via `REPAIR_IMAGE_BACKEND=s3`. Storage keys are unchanged so the local→S3 cutover needs no DB rewrite. Bucket creation pending operator action |
| Security CI gates (full) | Wed–Thu | **✅ Code-complete on `feat/cicd-prod-pipeline`.** SonarQube already shipped W1; the branch adds `pip-audit` (Python SCA, fails on any advisory in prod deps), `npm audit --omit=dev --audit-level=high`, and `dependency-check --failOnCVSS 7`. Optional `NVD_API_KEY` secret bumps NVD rate limit |
| Health check endpoints (`/health` + `/ready`) | Mon–Tue | **✅ Code-complete on `feat/cicd-prod-pipeline`.** `/health` is liveness (always 200); `/ready` runs `SELECT 1` (503 on DB failure) so ALB target groups can drain bad backends during RDS failover. Compose healthcheck already points at `/ready` |

### Testing (1 person + all devs contribute)

| Task | Target | Notes |
|------|--------|-------|
| Unit tests: business logic, validation, auth | Mon–Thu | pytest. Focus on: status transitions, optimistic locking, RBAC |
| Integration tests: all API endpoints | Wed–Fri | httpx + pytest. Cover all CRUD + workflow + error cases |
| E2E tests: 6 critical flows | Thu–Fri | Playwright. Login, submit repair, approve, complete, search, register asset |

### Dev (2 people — bug fixes)

| Task | Target | Notes |
|------|--------|-------|
| Fix bugs from integration testing | Rolling | Prioritize workflow-breaking bugs |
| Edge cases: empty states, validation errors | Mon–Wed | |
| Performance: add DB indexes if queries slow | Thu–Fri | Per design.md §7.3 index strategy |

### Milestone: `M5 — Deployed & Tested`
- [ ] App running on AWS (accessible via public URL)
- [ ] CI/CD: push to main auto-deploys
- [ ] Zero-downtime deploy demonstrated (deploy during load test)
- [ ] Test coverage ≥ 80% (unit + integration)
- [ ] E2E: 6 flows passing
- [ ] All security CI gates passing (SAST + SCA + secret scan)

---

## Week 6 — Harden + Demo Prep (May 19–23)

**Goal:** System is demo-ready. Presentation materials started.

**Resources shift:**

| Role | People | Focus |
|------|--------|-------|
| Dev (final fixes) | 1 | Last bug fixes, demo-critical polish |
| Infra / Monitoring | 2 | Monitoring, alerting, load testing |
| Presentation | 2 | Slides draft, demo script, report writing |

### Infra / Monitoring (2 people)

| Task | Target | Notes |
|------|--------|-------|
| CloudWatch metrics + alarms | Mon–Wed | CPU, error rate, latency, health check. Per design.md §5.8 |
| Load test with k6 or Locust | Wed–Thu | Sustain peak QPS for 10 min. Capture metrics for presentation |
| Stress test: find breaking point | Thu | Document max QPS before P95 > 3s |
| Health check endpoints (`/health` + `/ready`) | Mon–Tue | Liveness `/health` shipped W1 (`a0dfd95`); readiness `/ready` (DB `SELECT 1`, 503 on failure) **✅ code-complete on `feat/cicd-prod-pipeline`** and pulled into W5 scope. **Remaining W6 work:** configure ALB target-group health checks against `/ready` once the ECS cluster is provisioned |

### Presentation (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Architecture slides (system diagram, ER diagram, sequence diagrams) | Mon–Fri | Per rubric: 25% on architecture design |
| Demo script: rehearse the 6 critical flows | Wed–Fri | Prepare fallback plan if live demo fails (screenshots/video) |
| Testing strategy slides (pyramid, coverage report, load test results) | Thu–Fri | Per rubric: 25% on testing |
| Report draft (if format known) | Fri | Start with what you know; refine later |

### Dev (1 person)

| Task | Target | Notes |
|------|--------|-------|
| Demo data: realistic seed for presentation | Mon–Wed | Real-looking company names, asset names, repair histories |
| Final UX polish for demo flow | Wed–Fri | Make the 6 demo flows buttery smooth |

### Milestone: `M6 — Demo Ready`
- [ ] Live demo runs without errors for all 6 flows
- [ ] Monitoring dashboard shows real metrics
- [ ] Load test report with charts
- [ ] Slides first draft complete

---

## Buffer — May 26 – Jun 2

**Goal:** Everything polished. Team rehearsed. Ready for presentation.

**Resources:** 1 dev (on-call for fixes) + 4 on presentation/polish

| Task | Target | Notes |
|------|--------|-------|
| **May 26 — Rehearsal** | May 26 | Full run-through with team |
| Slides finalized | May 26–28 | Incorporate feedback from rehearsal |
| Report finalized | May 26–28 | PDF, A4 format per spec |
| Full rehearsal (internal, round 2) | May 29 | Time the presentation, practice transitions |
| Demo environment verified | May 30 | AWS instance healthy, data seeded, all flows work |
| Backup demo: screen recording | May 30 | Record the 6 flows as video backup |
| Code quality: lint clean, no warnings | May 28 | Per rubric: 10% on code quality |
| Last-minute bug fixes | Rolling | On-call dev addresses any issues found |
| **Jun 2 — Presentation** | Jun 2 | Final presentation |

### Milestone: `M7 — Presentation Ready`
- [ ] Slides reviewed by all team members
- [ ] Report PDF submitted (if deadline falls here)
- [ ] Team has rehearsed at least twice (May 26 + May 29)
- [ ] Backup demo video recorded
- [ ] AWS environment stable for 48+ hours

---

## Resource Allocation Summary

```
         W1      W2      W3      W4      W5      W6      Buffer
        Apr14   Apr21   Apr28   May05   May12   May19   May26
        ─────   ─────   ─────   ─────   ─────   ─────   ──────
BE-1    [setup ] [auth ] [APIs ] [search] [infra] [monit] [fixes]
BE-2    [CI    ] [CRUD ] [APIs ] [audit ] [infra] [load ] [pres ]
FE-1    [setup ] [asset] [mgr  ] [i18n  ] [test ] [pres ] [pres ]
FE-2    [setup ] [repair][hold ] [filter] [bugs ] [pres ] [pres ]
FE-3    [i18n  ] [guard] [ops  ] [polish] [QA/e2e][demo] [pres ]

Legend:
  setup  = project setup, scaffold
  CI     = CI pipeline, security gates
  auth   = auth API (register, login, JWT, RBAC)
  CRUD   = asset CRUD endpoints
  APIs   = repair workflow + image upload + remaining endpoints
  asset  = asset management pages (W2: list page)
  repair = repair request pages (W2: submit form)
  mgr    = manager pages (asset create/edit/assign/dispose, repair review/approve/complete)
  hold   = holder pages (asset detail, my-assets, repair list/detail, image display)
  ops    = integration & quality (PR review, merge coord, vitest coverage, i18n, UX states)
  guard  = auth guard, role-based routing
  search = multi-dimensional search API
  filter = search/filter UI
  audit  = audit log + API hardening
  i18n   = internationalization
  polish = UX polish, conflict UI
  infra  = Docker, AWS, CI/CD
  test   = unit + integration tests
  QA/e2e = E2E tests + manual QA
  bugs   = bug fixes
  monit  = monitoring, alerting
  load   = load/stress testing
  pres   = slides, report, demo prep
  demo   = demo data + UX polish
  fixes  = last-minute fixes
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| ~~**3 FE PRs from Week 2 carry into Week 3 (#12, #13, auth guard)**~~ | ~~Active~~ Resolved | Medium | ~~Land all three by Tue EOD via Mon–Tue carry-over closure block.~~ All three landed Apr 28 – May 1; asset list wiring (PR #19) followed |
| ~~**Image display on repair detail page slips into Week 4**~~ | ~~Medium~~ Materialized | Low | Backend image upload landed in W3 (PR #22) but FE display (PR #27) did slip into W4. Carry-over plan worked — first item to land in W4 |
| ~~UI library decision stalls past W2 Mon~~ | ~~Medium~~ Resolved | ~~High~~ | Closed in PR #8 — Ant Design v6 picked, layout shell shipped |
| FastAPI/SQLAlchemy ramp-up slows Week 1 | ~~Medium~~ Resolved | ~~High~~ | Backend landed on schedule (a0dfd95). No further action |
| AWS setup takes longer than expected | Medium | Medium | Start Docker in W5 Mon. If AWS delays, demo on local Docker Compose. **De-risked:** dev compose stack already shipped in W3 (PR #24); only production multi-stage images remain for W5 Mon |
| Integration bugs pile up in W3–W4 | ~~High~~ Medium | Medium | FE/BE pair-test each API as it's built in W2–W3. Don't wait until W4. **One real bug surfaced** ([issue #29](https://github.com/Joshua0209/Asset-Management-System/issues/29)) and was caught by the W3 smoke test — exactly the intended early-detection pattern |
| Presentation spec released late | Medium | Low | Start slides with known rubric (architecture 25%, testing 25%). Adjust layout later |
| Live demo fails during presentation | Low | High | Record backup demo video in Buffer week. Have screenshots as fallback |
| Security CI gates too strict / slow | Low | Medium | Start with minimal gates in W1 (lint + gitleaks), expand progressively in W5 |
| ~~**PR #27 (image display) holds Wednesday**~~ | ~~Active~~ Resolved | Low | Merged 2026-05-06 (W4 Wed) — first day of W4 as planned. M3 image-display outcome closed |
| ~~**Issue #29 (asset-code dropdown UX) blocks the holder happy path**~~ | ~~Active~~ Resolved | Medium | Closed by PR [#52](https://github.com/Joshua0209/Asset-Management-System/pull/52) merged 2026-05-13. Holders now pick assets from a dropdown sourced from `GET /assets/mine` |
| **W4 closed late (May 13 instead of May 9)** — eats into W5 capacity | Active | Medium | PR #39 (rate limiting) and PR #52 (issue #29) both merged on the first morning of W5. Effective W5 length is ~4 working days, not 5. **Mitigation:** the only W4 feature carry-over (search/filter UI) lands Mon–Tue of W5, before AWS work starts in earnest |
| **Multi-dim search/filter UI is the only thing standing between M4 and "complete"** | Active | Low | Pure FE work; BE is fully ready. One dev seat picks it up Mon–Tue of W5 |
| **AWS setup compresses if W5 dev seat is over-allocated** | Active | High | 2 dev seats absorb both bug fixes + the search-UI carry-over. If integration testing surfaces lots of edge cases, the search bar could slip to mid-week and trigger a cascade. **Mitigation:** ship search UI Mon–Tue (small, well-scoped); push edge-case fixes to Wed–Fri. If still slipping by Wed EOD, swap one infra seat onto bug fixes for half a day |
| **Production multi-stage Dockerfiles are net-new W5 work** | Active | Medium | Dev compose stack already exists (PR #24) but prod multi-stage builds (non-root user, no dev deps in final layer) have not been written. Infra seat owns Mon–Tue |

---

## Dependency Map

```
M1 (Skeleton + CI) ──► M2 (Auth + CRUD) ──► M3 (Core Features)
                                                   │
                                                   ├──► M4 (Advanced Features)
                                                   │         │
                                                   │         ├──► M5 (Deployed & Tested)
                                                   │         │         │
                                                   │         │         ├──► M6 (Demo Ready)
                                                   │         │         │         │
                                                   │         │         │         ▼
                                                   │         │         │    M7 (Presentation Ready)
                                                   │         │         │         │
                                                   │         │         │         ▼
                                                   │         │         │    Rehearsal (May 26)
                                                   │         │         │         │
                                                   │         │         │         ▼
                                                   │         │         │    Presentation (Jun 2)
                                                   │
                                                   └──► Slides/Report can start in parallel from M4
```

**Critical path:** M1 → M2 → M3 → M4 → M5 → M6 → M7 → Presentation

**Parallel track:** Slides/report writing can begin at M4 (Week 5) since architecture is settled.

---

## Security CI Pipeline (Progressive Rollout)

Per `09-testing-strategy.md`, security gates are added progressively:

| Stage | When Added | Tools | Gate |
|-------|-----------|-------|------|
| Secrets | Week 1 ✅ | gitleaks (pre-commit + CI) | Block on any finding |
| SAST | Week 1 ✅ | Semgrep (OWASP top-10 rules) | Block on ERROR severity |
| Lint | Week 1 ✅ | ESLint (FE) + ruff (BE) | Zero errors |
| Type check | Week 1 ✅ | `tsc --noEmit` (FE) + `mypy --strict` (BE) | Zero errors |
| Quality Gate | Week 1 ✅ (pulled from Week 5) | SonarCloud | Quality Gate must pass |
| SCA | Week 5 | npm audit + pip-audit | Block on HIGH/CRITICAL CVE |
| Deep SCA | Week 5 | OWASP Dependency-Check | Block on CVSS ≥ 7 |

---

## Evaluation Rubric Mapping

| Rubric | Weight | Where It's Covered |
|--------|--------|--------------------|
| Requirements → Implementation | 30% | W2–W4: User stories from Requirements.md → working features |
| Code Quality | 10% | W1: CI from day 1 (lint + type-check + security). Buffer: final lint clean |
| Architecture Design | 25% | design.md (done) + slides (W6). System diagrams, ER diagram, sequence diagrams |
| Testing | 25% | W5: unit + integration (80%+). W6: load test, stress test, E2E |
| Ops & Reliability | 10% | W5: Docker, CI/CD, zero-downtime. W6: monitoring, alerting, health checks |
