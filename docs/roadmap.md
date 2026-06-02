# Asset Management System — Development Roadmap

**Team:** 5 people (2 Backend, 3 Frontend at start)
**Timeline:** Apr 14 – Jun 2 (buffer week: May 26 – Jun 2)
**Scope:** Phase 2 architecture implementation + live demo + slides
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

**Status (2026-05-27):** W1–W6 done. **Production deploy is live on AWS with TLS on the ALB and Grafana Cloud taking real telemetry; only the k6 sustained-QPS run and the presentation deliverables remain for buffer week.** The W6 work that was mid-pivot on 2026-05-24 merged via PR [#89](https://github.com/Joshua0209/Asset-Management-System/pull/89) (squash of `feat/observability` carrying Phases 1, 2, 4, 5, 8 of the original implementation plan plus Phases 2–4 of the production-migration plan): backend is OTLP-native (no `prometheus_client`, no `/metrics` route, OTel SDK Counter/Tracer/Logger pushing to Grafana Cloud) and ECS task definitions point at the GC OTLP gateway with a cross-account IAM role for GC's hosted CloudWatch integration. Phase 5 k6 load surface plus a per-request structured access log shipped via PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85). The W5 DESIGN.md theme carry-over closed via PR [#80](https://github.com/Joshua0209/Asset-Management-System/pull/80). The ECS rolling deploy reached steady state after PRs [#83](https://github.com/Joshua0209/Asset-Management-System/pull/83) and [#90](https://github.com/Joshua0209/Asset-Management-System/pull/90) (single `DATABASE_URL` secret, `FORWARDED_ALLOW_IPS=*`, automated pre-deploy `alembic upgrade head` one-off task, migrate/seed CI ordering) plus the operator follow-ups: PR [#93](https://github.com/Joshua0209/Asset-Management-System/pull/93) documented the `ecs:RunTask`/`ecs:StopTask` permissions that were missing from the GitHub OIDC role, PR [#109](https://github.com/Joshua0209/Asset-Management-System/pull/109) updated the OIDC trust policy for environment-scoped jobs (`production-destructive` subject claim), PR [#101](https://github.com/Joshua0209/Asset-Management-System/pull/101) fixed the implicit `success()` skip on `migrate-database`, and PR [#102](https://github.com/Joshua0209/Asset-Management-System/pull/102) unblocked parallel ECS rollouts. **TLS on the ALB** is now live (ACM cert + HTTPS:443 listener configured AWS-side; HTTP→HTTPS redirect on :80). The Grafana Cloud cutover is verified end-to-end against real production telemetry: OTLP exporter on HTTP/protobuf instead of gRPC (PR [#100](https://github.com/Joshua0209/Asset-Management-System/pull/100)); dashboard datasource UIDs remapped to the real GC stack (PR [#96](https://github.com/Joshua0209/Asset-Management-System/pull/96)); `http_server_duration_seconds_*` emitted with stable semconv labels (PR [#104](https://github.com/Joshua0209/Asset-Management-System/pull/104)); PromQL panels drop the `environment` matcher because GC OTLP only promotes `service.*` onto metric labels (PR [#103](https://github.com/Joshua0209/Asset-Management-System/pull/103), follow-up PR [#111](https://github.com/Joshua0209/Asset-Management-System/pull/111) on Loki stream selectors + rate-window + zero-fallback hygiene); CloudWatch panels carry explicit `ap-east-2` region + Grafana 10+ required fields (PRs [#105](https://github.com/Joshua0209/Asset-Management-System/pull/105), [#106](https://github.com/Joshua0209/Asset-Management-System/pull/106)); MySQL dashboard points at the real `ams-database` RDS identifier (PR [#110](https://github.com/Joshua0209/Asset-Management-System/pull/110), reverting the failed auto-discovery attempt in PRs [#107](https://github.com/Joshua0209/Asset-Management-System/pull/107)/[#108](https://github.com/Joshua0209/Asset-Management-System/pull/108)); Pyroscope auth switched from Bearer to Basic with the Rust client logger enabled so future regressions surface in Loki (PR [#113](https://github.com/Joshua0209/Asset-Management-System/pull/113)). The end-to-end correlation walk (dashboard → Loki log line → Tempo trace → Pyroscope flamegraph for the same window) has been verified live in GC. Playwright E2E shipped via PR [#99](https://github.com/Joshua0209/Asset-Management-System/pull/99): 25 tests in 16 spec files covering the 6 critical flows (login, holder submit-repair with image, manager approve, complete, register asset, multi-dim search), with a dedicated `demo` Playwright project (holder-journey + manager-journey composed of `test.step()` checkpoints, headed at 500 ms slow-mo) for the live presentation. Backend integration coverage hardened via PR [#112](https://github.com/Joshua0209/Asset-Management-System/pull/112): lifecycle-journey tests chaining submit → approve → complete (plus reject, stale-version 409, concurrent approve race, RBAC negatives, holder polling); asset lifecycle journeys (register → assign → unassign → dispose with reassignment + repair-blocked branches); auth-to-action journeys; an Alembic migration schema-drift detector wired into CI against a real MySQL 8 service container; an OpenAPI contract test; parametrized FSM (20 cases) and RBAC matrices. A new operational landing page shipped via PR [#98](https://github.com/Joshua0209/Asset-Management-System/pull/98) (manager dashboard: `GET /dashboard/manager` aggregation backing KPI cards, asset-category bar chart, repair workload snapshot, and a clickable "recent pending review" list deep-linking into `/reviews?status=pending_review`), and PR [#95](https://github.com/Joshua0209/Asset-Management-System/pull/95) tightened the manager repair-flow modals (amount validation aligned with the repair contract, update-plan required-field gating, copy fixes). Realistic demo seed landed via PR [#87](https://github.com/Joshua0209/Asset-Management-System/pull/87); expanded unit test coverage (backend 484 tests at 97% coverage, frontend 184 tests) via PR [#88](https://github.com/Joshua0209/Asset-Management-System/pull/88); CI throughput via PR [#76](https://github.com/Joshua0209/Asset-Management-System/pull/76) (parallel backend jobs, path-filtered, Trivy in place of OWASP Dependency-Check) and PR [#81](https://github.com/Joshua0209/Asset-Management-System/pull/81) (test+coverage always-on so SonarQube never skips); 37 SonarQube maintainability findings resolved in PR [#92](https://github.com/Joshua0209/Asset-Management-System/pull/92); exact category enum filter on the asset list via PR [#68](https://github.com/Joshua0209/Asset-Management-System/pull/68); docs sync for CI, image storage, and frontend layout in PR [#91](https://github.com/Joshua0209/Asset-Management-System/pull/91). The W6 "alerting" sub-bullet (which had shipped only as written-down thresholds, not as evaluated rules) closed via the alerts pass added to `scripts/sync_grafana_cloud_dashboards.py`: 14 Grafana-managed alert rules (7 thresholds × warning + critical) under `config/grafana/alerts/`, routed to a single email contact point whose recipient list comes from the `GC_ALERT_EMAIL_RECIPIENTS` GitHub secret. The runbook is in `infra/grafana-cloud/README.md` §"Alert provisioning". **Open for buffer week:** run the k6 sustained-QPS test against the deployed ALB and capture screenshots for the testing slide; slides draft; May 26 + May 29 rehearsals.

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
| Image upload + retrieval endpoint | Wed–Thu | ✅ Done (PR #22). Upload bundled into `POST /repair-requests` (multipart, ≤5 files × 5 MB, JPEG/PNG). Retrieval via `GET /api/v1/images/:id` (auth required, FR-31 — any role, but holders are limited to their own requests' images; managers see all, per issue #123). Persistence abstracted behind `ImageStorage` Protocol with `LocalImageStorage` impl; S3 swap in Week 5 only touches `app/services/image_storage.py`. DB column `repair_images.image_url` stores a backend storage key, not a public URL — the public URL is computed in `RepairImageRead.url` |
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
| Optimistic locking conflict UI | Wed–Thu | ✅ Done (PR [#55](https://github.com/Joshua0209/Asset-Management-System/pull/55), merged 2026-05-13). Purpose-built conflict dialog with data refresh — when a 409 `conflict` is returned from an update, the dialog explains the situation and re-fetches the record so the user can re-apply their edit against the latest version. `AssetDetail.tsx`, `ReviewDetail.tsx`, and `SubmitRepairRequest.tsx` all wired up. Granular 409 codes (`duplicate_request`, `invalid_transition`, etc.) still surface through `formatApiError` for non-conflict cases |
| i18n: all pages translated | Thu–Fri | ✅ Done. 212 keys × 2 locales (en, zh-TW), perfect parity. 8 sections: `common`, `auth`, `validation`, `errors`, `assetList`, `reviews`, `repairRequestList`, `repairRequestDetail`. Zero hardcoded user-facing strings |
| UX polish: loading states, empty states, error toasts | Rolling | ✅ Done. Consistent Antd `Spin`/`Empty`/`notification` patterns across manager + holder surfaces, surfaced from FE-3 work in W3 and reinforced by PR #43/#44 |

### Milestone: `M4 — Feature Complete (Full)`
- [x] M3 carry-over closed: issue #29 fixed (PR [#52](https://github.com/Joshua0209/Asset-Management-System/pull/52))
- [x] Audit log (`asset_action_histories`) + `GET /assets/:id/history` shipped (PR [#38](https://github.com/Joshua0209/Asset-Management-System/pull/38))
- [x] Optimistic locking: concurrent edit shows conflict to second user — purpose-built dialog with data refresh shipped in PR [#55](https://github.com/Joshua0209/Asset-Management-System/pull/55), backed by the granular 409 codes pinned in PR [#45](https://github.com/Joshua0209/Asset-Management-System/pull/45)
- [x] All UI text is i18n-ready (language switcher works) — 212-key parity, zh-TW + en, audited 2026-05-13
- [x] Rate limiting active on all endpoints (PR [#39](https://github.com/Joshua0209/Asset-Management-System/pull/39))
- [ ] **Multi-dimensional search works with all filter combinations** — BE shipped (composite indexes + filter API); **FE filter bar carries into W5**
- [ ] No broken flows end-to-end — depends on E2E run in W5

---

## Week 5 — Infra + Testing + Polish (May 12–16) — **Done (DESIGN.md theme carries to W6)**

**Goal:** App is Dockerized, deployed to AWS, CI/CD pipeline green, test coverage ≥ 80%.

**Status (2026-05-20 PM):** Closed at the start of W6. The infra branch landed as PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58) on May 19 (prod multi-stage Dockerfiles, `/ready` probe, `S3ImageStorage`, full SCA gates, ECR + ECS rolling-deploy jobs). The W4 multi-dimensional filter/sort UI shipped as PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61) on May 20, closing the last open M4 outcome. The "unify manager/holder pages" task took a different shape than the original plan: PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59) instead **regrouped pages into `pages/holder/` and `pages/manager/` folders matching the route guards, decomposed the two god-pages (`ReviewDetail` and `AssetDetail`) into folder-modules with a shared `useSubmitAction` hook, and unified the inconsistent status-color constants** — cleaner than collapsing into single role-aware components and avoids regressions on the just-landed conflict-dialog wiring from PR #55. **Operator-side AWS provisioning landed late W6 Tue (PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) merged 2026-05-20 19:51Z)** with hardened `__NAME__` task-def placeholders, escape-safe sed substitution, fail-fast `Settings` validation when DB_* vars are missing, AWSCURRENT version-stage pinning on Secrets Manager refs, ECR image-scan gate at CVSS ≥ 7, identity-policy snippet + deployment circuit breaker docs. **One item carries into W6:** the DESIGN.md theme application (token wiring through Antd `ConfigProvider`). Test coverage and E2E both also slip to W6.

**W4-style hotfixes landed in W5:** PR [#60](https://github.com/Joshua0209/Asset-Management-System/pull/60) (rate-limited auth endpoints returning 500 + CORS blocks on preflight) and PR [#62](https://github.com/Joshua0209/Asset-Management-System/pull/62) (seed-data: DISPOSED transitions, audit-log rows, email collisions, category enum drift).

**Carry-over from W4 (FE) — closed:**

| Task | Owner | Target | Notes |
|------|-------|--------|-------|
| Multi-dimensional search/filter UI on `AssetList.tsx` | Dev seat (FE) | Mon–Tue | ✅ Done (PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61), merged 2026-05-20). Filter bar with text search + dropdowns wired through a shared `listControls` module so both `AssetList` (manager) and `MyAssetList` (holder) share the same filter/sort engine. Closes the last open M4 outcome |

**Resources shift:**

| Role | People | Focus |
|------|--------|-------|
| Dev (bug fixes + W4 carry-over) | 2 | Fix issues found during testing, edge cases, ship the search/filter UI |
| Infra / DevOps | 2 | Docker prod images, AWS, CI/CD, monitoring |
| QA / Testing | 1 | E2E tests, manual testing |

### Infra (2 people) — ✅ Merged (operator AWS provisioning carries to W6)

| Task | Target | Notes |
|------|--------|-------|
| Dockerize FE + BE (multi-stage builds) | Mon–Tue | ✅ Done (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)). `backend/Dockerfile.prod` (gunicorn + UvicornWorker, slim final stage, non-root) and `frontend/Dockerfile.prod` (nginx:alpine serving Vite build with SPA fallback + asset cache headers). Dev compose stack stays separate |
| AWS setup: ECS Fargate + ALB + RDS (Single-AZ) | Tue–Thu | ✅ Done (PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63), merged 2026-05-20 W6 Tue). Architecture pivoted from "EC2 ×2 + manual orchestration" to ECS Fargate. Task definitions in `infra/aws/tasks/` use `__NAME__` sentinel placeholders (no env-var collisions), substituted at deploy time via the new `.github/actions/render-task-def/` composite action with escape-safe sed (`\`, `|`, `&` neutralised) and a post-substitution guard. Operator setup: dedicated `ams/prod/app` Secrets Manager entry for `JWT_SECRET` + `BOOTSTRAP_MANAGER_PASSWORD`, RDS secret `ams/prod/rds` (both pinned to `AWSCURRENT`), three IAM roles (`ams-ecs-task-execution`, `ams-backend-task`, `ams-frontend-task`), GitHub OIDC trust on `StringEquals`, identity policy with `iam:PassRole` scoped via `iam:PassedToService=ecs-tasks.amazonaws.com`. RDS (`ams-database`) + S3 (`ams-repair-images-prod`) + ECR live in `ap-east-2`; `ams-backend` / `ams-frontend` services in the `ams-prod` cluster. **Note:** Multi-AZ deferred to Phase 2. **Operator-side follow-up:** trigger a `workflow_dispatch` to confirm both task defs render correctly against the real GitHub secrets/variables |
| CI/CD pipeline expansion (deploy) | Wed–Thu | ✅ Done (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)). Deploy jobs in `.github/workflows/cd.yml` trigger on push to `main` and manual dispatch after quality/security gates pass: builds both prod images, pushes to ECR, renders task defs, runs ECS rolling update with `wait-for-service-stability`. Auth via GitHub OIDC |
| Zero-downtime rolling deploy | Thu–Fri | ✅ Done (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)). `aws-actions/amazon-ecs-deploy-task-definition` with `wait-for-service-stability: true` blocks until the new task set passes ALB health checks (10-min timeout). `/ready` returns 503 on DB failure so ALB can drain a bad target during future RDS Multi-AZ failover |
| S3 bucket for images | Wed | ✅ Done (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)). `S3ImageStorage` lives next to `LocalImageStorage` behind the existing `ImageStorage` Protocol; selected via `REPAIR_IMAGE_BACKEND=s3`. Storage keys are unchanged so the local→S3 cutover needs no DB rewrite. Bucket itself live per PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) report |
| Security CI gates (full) | Wed–Thu | ✅ Done (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)). SonarQube already shipped W1; the branch added `pip-audit` (Python SCA), `npm audit --omit=dev --audit-level=high`, and `dependency-check --failOnCVSS 7`. Optional `NVD_API_KEY` secret bumps NVD rate limit |
| Health check endpoints (`/health` + `/ready`) | Mon–Tue | ✅ Done (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)). `/health` is liveness (always 200); `/ready` runs `SELECT 1` (503 on DB failure). Compose healthcheck already points at `/ready` |

### Testing (1 person + all devs contribute) — ⚠ Partial (E2E carries)

| Task | Target | Notes |
|------|--------|-------|
| Unit tests: business logic, validation, auth | Mon–Thu | ⚠ Backend test suite grew through W5 (25 test files, including new `test_image_storage_s3.py`, `test_composite_indexes_migration.py`, `test_rate_limit.py`, `test_alembic_migration_chain.py`). Coverage measurement run is the W6 follow-up |
| Integration tests: all API endpoints | Wed–Fri | ✅ Done (PR [#112](https://github.com/Joshua0209/Asset-Management-System/pull/112)). Cross-cutting layer: 3 journey tests, 32-cell FSM matrix, 66-cell RBAC matrix, OpenAPI contract validator (incl. multipart submit + 503 envelope), MySQL-gated migration-drift detector. Strategy in [`backend/tests/README.md`](../backend/tests/README.md) |
| E2E tests: 6 critical flows | Thu–Fri | ❌ **Carries to W6.** Playwright suite not yet authored. Six flows: login, submit repair, approve, complete, search, register asset |

### Dev (2 people — W4 carry-over, new FE scope, bug fixes) — ⚠ Partial (DESIGN.md theme carries)

| Task | Target | Notes |
|------|--------|-------|
| W4 carry-over: multi-dim search/filter UI on `AssetList.tsx` | Mon–Tue | ✅ Done (PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61), merged 2026-05-20). Shared `listControls` module powers both `AssetList` (manager) and `MyAssetList` (holder) |
| Unify manager + holder page pairs into role-aware pages | Tue–Thu | ✅ Done in a different shape (PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59), merged 2026-05-18). Instead of collapsing pairs into single components, the team **regrouped pages by route guard** into `pages/holder/` and `pages/manager/` folders, **decomposed the 594-line `ReviewDetail` and 564-line `AssetDetail`** into folder-modules (`index.tsx` + per-modal components + a `useXxxActions` hook on top of a shared `useSubmitAction`), **unified the inconsistent `REPAIR_REQUEST_STATUS_COLORS` constant** (holder pages had blue/yellow, manager pages had yellow/blue for the same statuses), extracted `formatDateTime` / `formatRepairCost` helpers, and adopted a `@/` path alias across 200 imports in 58 files. Functionally equivalent and keeps the conflict-dialog wiring from PR [#55](https://github.com/Joshua0209/Asset-Management-System/pull/55) intact |
| Apply DESIGN.md theme to UI | Wed–Fri | ❌ **Carries to W6.** Token wiring through Antd `ConfigProvider` + four-pillar audit not started |
| Bug fixes from integration testing | Rolling | ✅ Done. PR [#60](https://github.com/Joshua0209/Asset-Management-System/pull/60) (rate-limited auth endpoints 500 + CORS preflight) and PR [#62](https://github.com/Joshua0209/Asset-Management-System/pull/62) (seed-data: DISPOSED transitions, audit-log rows, email collisions, category enum drift) caught real bugs during the integration smoke pass. Small consistency fix PR [#65](https://github.com/Joshua0209/Asset-Management-System/pull/65) merged 2026-05-20: "Fault Content" → "Fault Description" labels in Reviews + i18n, `formatDateTime` respects `i18n.resolvedLanguage` (dates render as `下午 8:00` in zh-TW, `8:00 PM` in en), and `RepairRequestList` + `Reviews` now share rendering helpers for request ID / asset / status |
| Edge cases: empty states, validation errors | Mon–Wed | ✅ Folded into the PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59) refactor and the bug-fix PRs above |
| Performance: add DB indexes if queries slow | Thu–Fri | Not needed — composite indexes from W4 PR [#46](https://github.com/Joshua0209/Asset-Management-System/pull/46) cover the multi-dim filter surface |

### Milestone: `M5 — Deployed & Tested`
- [x] W4 FE carry-over closed: multi-dim search/filter UI on Asset List (PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61))
- [x] Manager/holder page pairs unified (PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59) regrouped by role + decomposed god-pages + unified shared constants and helpers; functionally equivalent to the original plan)
- [x] DESIGN.md theme applied: tokens wired through `ConfigProvider`, four-pillar audit clean (closed in W6 via PR [#80](https://github.com/Joshua0209/Asset-Management-System/pull/80))
- [x] `feat/cicd-prod-pipeline` reviewed, PR'd, merged (PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58))
- [x] AWS resources provisioned (ECR + ECS + RDS + S3 + OIDC IAM role) — PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) merged 2026-05-20 with operator hydration + hardened placeholder substitution
- [x] App running on AWS (accessible via public URL on HTTPS) — task-def, secrets, IAM, and pre-deploy `alembic upgrade head` automation merged (PRs [#83](https://github.com/Joshua0209/Asset-Management-System/pull/83), [#90](https://github.com/Joshua0209/Asset-Management-System/pull/90)); operator follow-ups in PRs [#93](https://github.com/Joshua0209/Asset-Management-System/pull/93), [#101](https://github.com/Joshua0209/Asset-Management-System/pull/101), [#102](https://github.com/Joshua0209/Asset-Management-System/pull/102), [#109](https://github.com/Joshua0209/Asset-Management-System/pull/109) unblocked the rolling deploy; ALB has an ACM cert + HTTPS:443 listener
- [x] CI/CD: push to main triggers the deploy pipeline and reaches steady state
- [ ] Zero-downtime deploy demonstrated (deploy during k6 load test) — pairs with the buffer-week k6 sustained-QPS run
- [x] Test coverage ≥ 80%: backend 484 tests at 97% coverage, frontend 184 tests (closed in W6 via PR [#88](https://github.com/Joshua0209/Asset-Management-System/pull/88)). SonarQube always-on after PR [#81](https://github.com/Joshua0209/Asset-Management-System/pull/81)
- [x] E2E: 6 flows passing (PR [#99](https://github.com/Joshua0209/Asset-Management-System/pull/99))
- [x] All security CI gates passing (SAST + SCA + secret scan) — SCA stack now uses Trivy in place of OWASP Dependency-Check (PR [#76](https://github.com/Joshua0209/Asset-Management-System/pull/76))

---

## Week 6 — Observability + Demo Prep (May 19–24) — **Essentially Closed (buffer-week tasks listed below)**

**Goal:** System is demo-ready, instrumented end-to-end, and producing real telemetry under load. Presentation materials drafted.

### Current state (2026-05-27): Grafana Cloud is the single backend, prod deploy live on HTTPS, dashboards rendering real telemetry

The W6 work landed in two phases. The first half built the self-hosted Grafana stack described in the historical narrative below (Phases 1–5 of the observability implementation plan). The second half, triggered by seven decisions locked on 2026-05-24, replaced it with a hosted Grafana Cloud stack named `ams` and removed every observability container from local dev. Both halves are now merged to `main` via PR [#89](https://github.com/Joshua0209/Asset-Management-System/pull/89) (the squash-merge of `feat/observability`) plus PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85) (Phase 5 k6 + access log on the post-Phase-3 base). The new shape:

| Signal | Path | Code site |
|---|---|---|
| Traces | OTel SDK OTLP/HTTP-protobuf → GC OTLP gateway | `backend/app/core/observability.py` setup_tracing |
| Metrics | OTel SDK OTLP/HTTP-protobuf → GC OTLP gateway | `backend/app/core/observability.py` setup_metrics_exporter |
| Logs | structlog → stdlib → OTel `LoggingHandler` → GC OTLP gateway → GC Loki | `backend/app/core/observability.py` setup_log_exporter |
| Profiles | `pyroscope-io` (Basic auth) → GC hosted Pyroscope (enabled in prod) | `backend/app/core/observability.py` maybe_setup_profiling |
| AWS metrics + logs | GC's hosted CloudWatch integration → cross-account role `ams-grafana-cloud-reader` | `infra/grafana-cloud/iam-role-*.json` |
| ECS secrets | `ams-grafana-cloud` AWS Secrets Manager secret (3 JSON keys) | `infra/aws/tasks/backend-task-def.json` |
| Dashboards | 6 JSONs in `config/grafana/dashboards/`, synced to GC by the `sync-dashboards` CI job (`scripts/sync_grafana_cloud_dashboards.py`) on every dashboard change | repo is source of truth; the original Phase 6 plan to delete repo JSONs is N/A under this sync model |

`docker compose up` brings up `mysql + backend + frontend` only — zero observability containers.

**M6 status against the current state:**

- [x] Backend OTLP-native (PR [#89](https://github.com/Joshua0209/Asset-Management-System/pull/89), Phase 3 of the migration plan). `prometheus_client` / `prometheus-fastapi-instrumentator` / `/metrics` removed; OTel SDK Counter/Tracer/Logger + Pyroscope-in-prod.
- [x] Per-request structured access log shipping to GC Loki via the OTel logging bridge (PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85)). Every line carries `trace_id`/`span_id` for one-click Loki ↔ Tempo correlation. Excludes `/health` and `/ready`.
- [x] Frontend browser OTLP (PR [#72](https://github.com/Joshua0209/Asset-Management-System/pull/72)).
- [x] ECS production wired to GC OTLP + cross-account IAM (PR [#89](https://github.com/Joshua0209/Asset-Management-System/pull/89), Phase 4 of the migration plan).
- [x] Six dashboards authored against the OTLP metric model + GC CloudWatch panels for ECS/RDS/ALB (PR [#78](https://github.com/Joshua0209/Asset-Management-System/pull/78), dashboard hygiene fixes in PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85), datasource-UID remap in PR [#96](https://github.com/Joshua0209/Asset-Management-System/pull/96), PromQL hygiene in PRs [#103](https://github.com/Joshua0209/Asset-Management-System/pull/103)/[#104](https://github.com/Joshua0209/Asset-Management-System/pull/104)/[#111](https://github.com/Joshua0209/Asset-Management-System/pull/111), CloudWatch region + Grafana 10+ fields in PRs [#105](https://github.com/Joshua0209/Asset-Management-System/pull/105)/[#106](https://github.com/Joshua0209/Asset-Management-System/pull/106), real RDS identifier in PR [#110](https://github.com/Joshua0209/Asset-Management-System/pull/110)). In-prod sync + panel render against real telemetry verified live.
- [x] Phase 5 k6 load surface plus per-VU JWT cache, six scenario scripts, container-run support via `host.docker.internal`, and `K6_PROMETHEUS_RW_*` for remote-write into GC Prom (PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85)). **The sustained-QPS run against the deployed ALB + screenshots for the testing slide still need to happen** (carries into buffer week).
- [N/A] ~~Phase 6: repo-side dashboard JSONs deleted after first GC import is verified in production.~~ Superseded by the `sync-dashboards` CI job — repo `config/grafana/dashboards/*.json` is the source of truth and CI pushes to GC on every dashboard change. Deleting the repo files would also remove the source the sync script reads.
- [x] DESIGN.md theme application (PR [#80](https://github.com/Joshua0209/Asset-Management-System/pull/80)). Design tokens wired through Antd `ConfigProvider`, sidebar copy updated to TSMC, demo-visible surfaces audited against the four-pillar checklist (typography hierarchy, 8px rhythm, tabular asset/date/money cells, restrained red accents, no gradients/emoji).
- [x] Manager dashboard with KPI cards, asset-category bar chart, repair workload snapshot, and recent-pending-review deep-link (PR [#98](https://github.com/Joshua0209/Asset-Management-System/pull/98)). Backed by a single manager-only `GET /dashboard/manager` aggregation; disposed assets excluded from totals, UTC start-of-day buckets for "today" counts.
- [x] Final repair-flow UX polish: amount validation aligned with the repair contract, update-plan required-field gating, manager copy fixes (PR [#95](https://github.com/Joshua0209/Asset-Management-System/pull/95)).
- [x] Playwright E2E suite for the 6 critical flows (PR [#99](https://github.com/Joshua0209/Asset-Management-System/pull/99)). 25 tests in 16 spec files plus a dedicated `demo` Playwright project (holder-journey + manager-journey, headed at 500 ms slow-mo) for the live presentation.
- [x] Cross-cutting backend integration tests (PR [#112](https://github.com/Joshua0209/Asset-Management-System/pull/112)): lifecycle journeys, parametrized FSM + RBAC matrices, Alembic migration schema-drift detector against a real MySQL 8 CI service, and an OpenAPI contract test.
- [x] First production rolling deploy completes cleanly. PR [#83](https://github.com/Joshua0209/Asset-Management-System/pull/83) consolidated the backend task-def around a single `DATABASE_URL` secret, set `FORWARDED_ALLOW_IPS=*`, and added an automated pre-deploy one-off ECS Fargate task that runs `alembic upgrade head`. PR [#90](https://github.com/Joshua0209/Asset-Management-System/pull/90) fixed the migrate/seed CI ordering so one-off task defs register before `run-task`. PR [#101](https://github.com/Joshua0209/Asset-Management-System/pull/101) fixed the implicit `success()` skip on `migrate-database`; PR [#102](https://github.com/Joshua0209/Asset-Management-System/pull/102) unblocked parallel ECS rollouts; PRs [#93](https://github.com/Joshua0209/Asset-Management-System/pull/93) and [#109](https://github.com/Joshua0209/Asset-Management-System/pull/109) added `ecs:RunTask`/`ecs:StopTask` permissions and the `production-destructive` OIDC subject claim to the GitHub Actions role.
- [x] **TLS on the ALB.** ACM certificate + HTTPS:443 listener configured AWS-side; HTTP:80 redirects to HTTPS. Frontend and backend reach the deployed service over `https://`.
- [x] **End-to-end correlation walk verified live in GC.** Dashboard panel → Loki log line → Tempo trace → Pyroscope flamegraph for the same window. Pyroscope auth fix in PR [#113](https://github.com/Joshua0209/Asset-Management-System/pull/113) was the last unblocker for the profile leg.
- [x] Realistic demo seed (PR [#87](https://github.com/Joshua0209/Asset-Management-System/pull/87)). 60 active + 3 disposed assets, 12 repair requests across every FSM state, zh-TW users/departments/factory locations/vendors with storage-key-backed demo images.
- [x] Test coverage measured and expanded (PR [#88](https://github.com/Joshua0209/Asset-Management-System/pull/88)). Backend 484 tests at 97% coverage; frontend 184 tests. New `AssetUpdate` schema validation, `IntegrityError` paths on `assets.py`, `auth/queries.ts` real-API branches, `utils/validators.ts` first-time coverage, and `SubmitRepairRequest` error/upload paths.
- [x] CI throughput improvements (PR [#76](https://github.com/Joshua0209/Asset-Management-System/pull/76) parallelized backend jobs + path-filtered + swapped Trivy for OWASP DC; PR [#81](https://github.com/Joshua0209/Asset-Management-System/pull/81) made test+coverage jobs always run so SonarQube never skips).

---

## Buffer — May 26 – Jun 2

**Goal:** Everything polished. Team rehearsed. Ready for presentation.

**Resources:** 1 dev (on-call for fixes) + 4 on presentation/polish

| Task | Target | Notes |
|------|--------|-------|
| **May 26 — Rehearsal** | May 26 | Full run-through with team |
| k6 sustained-QPS run + screenshots | May 26–28 | Constant-arrival-rate against the deployed ALB; `K6_PROMETHEUS_RW_*` into GC Prom; capture Grafana panels for the testing slide |
| Slides finalized | May 26–28 | Incorporate feedback from rehearsal |
| Full rehearsal (internal, round 2) | May 29 | Time the presentation, practice transitions |
| Demo environment verified | May 30 | AWS instance healthy, data seeded, all flows work |
| Backup demo: screen recording | May 30 | Record the 6 flows as video backup |
| Code quality: lint clean, no warnings | May 28 | Per rubric: 10% on code quality |
| Last-minute bug fixes | Rolling | On-call dev addresses any issues found |
| **Jun 2 — Presentation** | Jun 2 | Final presentation |

### Milestone: `M7 — Presentation Ready`
- [ ] k6 sustained-QPS run executed against the deployed ALB + Grafana screenshots in the testing slide
- [ ] Slides reviewed by all team members
- [ ] Team has rehearsed at least twice (May 26 + May 29)
- [ ] Backup demo video recorded
- [ ] AWS environment stable for 48+ hours

---

## Resource Allocation Summary

```
         W1      W2      W3      W4      W5      W6      Buffer
        Apr14   Apr21   Apr28   May05   May12   May19   May26
        ─────   ─────   ─────   ─────   ─────   ─────   ──────
BE-1    [setup ] [auth ] [APIs ] [search] [infra] [obs  ] [fixes]
BE-2    [CI    ] [CRUD ] [APIs ] [audit ] [infra] [aws  ] [pres ]
FE-1    [setup ] [asset] [mgr  ] [i18n  ] [filter][theme ] [pres ]
FE-2    [setup ] [repair][hold ] [filter] [reorg ] [demo ] [pres ]
FE-3    [i18n  ] [guard] [ops  ] [polish] [bugs ] [QA/e2e][pres ]

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
  reorg  = role-folder reorganization + god-page decomposition (PR #59)
  audit  = audit log + API hardening
  i18n   = internationalization
  polish = UX polish, conflict UI
  infra  = Docker prod, ECS deploy pipeline, CI/CD (PR #58)
  aws    = AWS provisioning (RDS, S3, IAM, OIDC) + PR #63 merge
  obs    = backend instrumentation (Prom + OTLP + Pyroscope + structured logs) + Grafana stack
  theme  = DESIGN.md token wiring through Antd ConfigProvider + four-pillar audit
  test   = unit + integration tests
  QA/e2e = E2E tests + manual QA + coverage measurement
  bugs   = bug fixes (PR #60 rate-limit/CORS, PR #62 seed)
  load   = load/stress testing
  pres   = slides, demo prep
  demo   = demo data + UX polish for the 6 critical flows
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
| ~~**W4 closed late (May 13 instead of May 9)** — eats into W5 capacity~~ | ~~Active~~ Resolved | ~~Medium~~ | W5 still closed on schedule (May 19–20 for the major merges) — the late W4 close did not cascade. Search/filter UI shipped Tue May 20 (PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61)) |
| ~~**Multi-dim search/filter UI is the only thing standing between M4 and "complete"**~~ | ~~Active~~ Resolved | ~~Low~~ | Closed by PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61). M4 complete |
| ~~**AWS setup compresses if W5 dev seat is over-allocated**~~ | ~~Active~~ Partially resolved | ~~High~~ | The compose-stack code shipped via PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58); the operator hydration is in flight in PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63). One W6 day is reserved for the merge + smoke test |
| ~~**Production multi-stage Dockerfiles are net-new W5 work**~~ | ~~Active~~ Resolved | ~~Medium~~ | Merged via PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58) on 2026-05-19 |
| ~~**W5 has 3 FE tasks competing for 2 dev seats**~~ | ~~Active~~ Partially resolved | ~~High~~ | Search UI shipped (PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61)). Page unification reshaped to "regroup + decompose" and shipped via PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59). DESIGN.md theme carries to W6 |
| ~~**Page unification could collide with PR #55's conflict-dialog wiring**~~ | ~~Active~~ Resolved | ~~Medium~~ | PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59) took the "regroup by role folder + decompose god-pages" approach instead of collapsing into single role-aware components, so the PR [#55](https://github.com/Joshua0209/Asset-Management-System/pull/55) conflict-dialog wiring stayed intact. Tests green throughout |
| ~~**DESIGN.md theme carry into W6**~~ | ~~Active~~ Resolved | ~~Medium~~ | Closed by PR [#80](https://github.com/Joshua0209/Asset-Management-System/pull/80) merged 2026-05-25. Design tokens wired through Antd `ConfigProvider`, sidebar copy refreshed to TSMC, demo-visible surfaces audited against the four-pillar checklist (typography hierarchy, 8px rhythm, tabular asset/date/money cells, restrained red accents, no gradients/emoji) |
| ~~**AWS rolling deploy not converging**~~ | ~~Active~~ Resolved | ~~High~~ | Resolved across the operator follow-ups: PR [#93](https://github.com/Joshua0209/Asset-Management-System/pull/93) added the missing `ecs:RunTask`/`ecs:StopTask` permissions on the GitHub Actions role; PR [#109](https://github.com/Joshua0209/Asset-Management-System/pull/109) updated the OIDC trust policy with the `production-destructive` subject claim; PR [#101](https://github.com/Joshua0209/Asset-Management-System/pull/101) fixed the implicit `success()` skip on `migrate-database`; PR [#102](https://github.com/Joshua0209/Asset-Management-System/pull/102) unblocked parallel ECS rollouts. Combined with PRs [#83](https://github.com/Joshua0209/Asset-Management-System/pull/83)/[#90](https://github.com/Joshua0209/Asset-Management-System/pull/90), the ECS rolling deploy now reaches steady state and the live URL is reachable on HTTPS |
| ~~**Backend instrumentation could break rate-limit middleware ordering**~~ | ~~Active~~ Resolved | ~~Medium~~ | Phase 8 regression test landed via PR [#79](https://github.com/Joshua0209/Asset-Management-System/pull/79) and survived the Phase 3 refactor (PR [#89](https://github.com/Joshua0209/Asset-Management-System/pull/89) all 446 backend tests green). With Phase 3 removing the `/metrics` route entirely, the double-count surface is gone; the OTel `FastAPIInstrumentor` injects via a `build_middleware_stack` monkey-patch, so user-middleware call order no longer affects span context for the new access log either (PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85)) |
| ~~**Grafana stack image size on the demo laptop**~~ | ~~Active~~ N/A | ~~Low~~ | Moot. The 2026-05-24 pivot removed all observability containers from local dev; `docker compose up` brings up only `mysql + backend + frontend`. Demo telemetry pushes direct to Grafana Cloud when credentials are supplied |
| ~~**OTLP from the browser needs a reverse proxy in prod**~~ | ~~Active~~ Resolved | ~~Low~~ | Browser OTLP-HTTP now targets the Grafana Cloud OTLP gateway directly (publicly reachable, basic-auth scoped). No internal Alloy endpoint, no extra prod reverse proxy needed |
| ~~**Test coverage measurement might reveal large gaps**~~ | ~~Active~~ Resolved | ~~Medium~~ | Closed by PR [#88](https://github.com/Joshua0209/Asset-Management-System/pull/88). Backend lands at 484 tests / 97% coverage, frontend at 184 tests. New `AssetUpdate` schema validation, `IntegrityError` paths on `assets.py`, `auth/queries.ts` real-API branches, `utils/validators.ts` first-time coverage, and `SubmitRepairRequest` error/upload paths fill the gaps that the W5 suite left open |
| ~~**Playwright E2E suite still not authored as buffer week begins**~~ | ~~Active~~ Resolved | ~~Medium~~ | Closed by PR [#99](https://github.com/Joshua0209/Asset-Management-System/pull/99): 25 specs across the 6 critical flows plus a dedicated `demo` Playwright project (headed, 500 ms slow-mo) composed of `test.step()` checkpoints for the live presentation. Backup demo video still planned per the buffer-week table |
| **k6 sustained-QPS run + screenshots still pending** | Active | Low | Scripts, JWT cache, and remote-write wiring all merged in PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85); deploy is up and reachable on HTTPS. **Mitigation:** run during the buffer week with `K6_PROMETHEUS_RW_*` into GC Prom; capture Grafana panels for the testing slide. If GC remote-write rate-limits the run, fall back to local k6 output JSON + a static screenshot of the same panels populated by the k6 cloud egress |

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

**Parallel track:** Slides writing can begin at M4 (Week 5) since architecture is settled.

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
| SCA | Week 5 ✅ | npm audit + pip-audit | Block on HIGH/CRITICAL CVE (shipped via PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)) |
| Deep SCA | Week 5 ✅ | OWASP Dependency-Check | Block on CVSS ≥ 7 (shipped via PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)) |

---

## Evaluation Rubric Mapping

| Rubric | Weight | Where It's Covered |
|--------|--------|--------------------|
| Requirements → Implementation | 30% | W2–W4: User stories from Requirements.md → working features |
| Code Quality | 10% | W1: CI from day 1 (lint + type-check + security). Buffer: final lint clean |
| Architecture Design | 25% | design.md (done) + slides (W6). System diagrams, ER diagram, sequence diagrams |
| Testing | 25% | W5: unit + integration (80%+). W6: load test, stress test, E2E |
| Ops & Reliability | 10% | W5: Docker, CI/CD, zero-downtime. W6: monitoring, alerting, health checks |
