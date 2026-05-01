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
- [ ] Holder can view own assets (frontend list reads from mocks; needs `/assets/mine` wiring)
- [x] Holder can submit a repair request
- [x] Role-based access enforced on FE + BE

---

## Week 3 — Core Features Complete (Apr 28 – May 2)

**Goal:** All CRUD operations and the full repair workflow work end-to-end.

**Resources:** 2 BE + 3 FE

**⚠ Carry-over from Week 2 (current):** Frontend review tasks are complete — login/register (PR #12), repair submit form (PR #13), and auth guard/role routing are done. Asset List still reads from `frontend/src/mocks/assets.ts` and remains pending real `GET /assets` and `GET /assets/mine` wiring.

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
| Wire Asset List to real `GET /assets` API | ⏳ Pending | Mon–Tue | FE-1 → FE-3 reviews | Asset list still uses `frontend/src/mocks/assets.ts`; real `/assets` + `/assets/mine` wiring is outstanding |

### Backend (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Repair Request APIs (full workflow) | Mon–Wed | Complete state machine: `pending_review → under_repair → completed` and `pending_review → rejected`. All FSM transitions validated server-side |
| Image upload endpoint | Wed–Thu | Upload-through-server. Store to local disk for now, abstract with a service layer for future S3 migration |
| Asset assign/unassign/dispose | Thu–Fri | FSM transitions T2 (assign), T5 (unassign), T3 (dispose) |
| API documentation review | Fri | Verify FastAPI auto-docs match `12-api-design.md` contract |

### Frontend — Wed–Fri (compressed scope, audience-split)

#### FE-1 — Manager pages

| Task | Target | Notes |
|------|--------|-------|
| Asset create / edit pages | Wed–Thu | Form validation, category dropdown (2-level flat list), purchase amount + warranty expiry validation matching backend Pydantic schema |
| Asset assign / unassign UI | Thu | FSM transitions T2/T5 — manager picks holder from user list, sets assignment date |
| Asset dispose flow | Thu | FSM transition T3 — confirm dialog with reason; status → `disposed` |
| Repair review/approve/reject UI | Thu–Fri | Approve → fill repair plan form (vendor, planned cost, planned date). Reject → confirm dialog with reason. Drives FSM `pending_review → under_repair` or `pending_review → rejected` |
| Repair complete UI | Fri | Fill repair date, content, actual cost, vendor → mark complete. Drives FSM `under_repair → completed` |

#### FE-2 — Holder pages

| Task | Target | Notes |
|------|--------|-------|
| Asset detail page | Wed | Read-only view of asset metadata; manager view (FE-1) enables edit/assign actions, holder view shows own-asset detail only |
| My assets list (holder view) | Wed | Wraps the same table component as the shared list page but reads from `GET /assets/mine` |
| Repair request list page | Wed–Thu | Status badges, sortable columns. Manager sees all; holder sees own only — same component, role-aware filter |
| Repair request detail page | Thu–Fri | Timeline view of workflow stages, status transitions, manager comments |
| Image display on repair detail page | Fri | Thumbnail grid, click-to-enlarge modal. **Risk:** depends on backend image upload endpoint landing Wed–Thu — fall back to placeholder thumbnails using mock URLs if BE slips, real wiring lands first thing W4 |

#### FE-3 — Integration & quality

| Task | Target | Notes |
|------|--------|-------|
| PR review for FE-1 and FE-2 work | Rolling | Same-day turnaround on PR review to keep FE-1/FE-2 unblocked. Owns the "PR review SLA" for the FE side this week |
| Merge coordination | Rolling | Resolve merge conflicts between FE-1/FE-2 branches (likely on shared layout, routing, i18n keys). Keep `main` green |
| vitest coverage on new pages | Wed–Fri | Each new page ships with at least one render test + one role-gating test. Target: maintain ≥ 80% FE coverage as new pages land |
| i18n keys (zh-TW + en) for all new pages | Rolling | Audit `src/i18n/locales/` after each PR merges; no hardcoded user-facing strings |
| Cross-cutting UX: loading, empty, error states | Thu–Fri | Consistent patterns across manager + holder pages. Hooks into Ant Design's `Spin`, `Empty`, `notification` |
| Optional: integration smoke test against real backend | Fri | If schedule allows, manual run-through of the 3 critical flows (manager registers asset, holder submits repair, manager completes) end-to-end before week close |

### Milestone: `M3 — Feature Complete (Core)`
- [ ] Manager can register asset, assign to holder
- [ ] Holder can view own assets, submit repair request with images
- [ ] Manager can approve/reject repair, fill details, complete repair
- [ ] Status transitions update asset status automatically
- [ ] Images upload and display on repair detail page

---

## Week 4 — Advanced Features & Integration (May 5–9)

**Goal:** All advanced features working. System fully integrated and polished.

**Resources:** 2 BE + 3 FE

### Backend (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Multi-dimensional search & filter API | Mon–Wed | Filter by: asset ID, name, model, location, person, status, department, category. Composite SQL indexes per design.md §5.5 |
| Optimistic locking enforcement | Mon–Wed | `WHERE version = ?` on all update endpoints. Return HTTP 409 on conflict |
| Audit log (event stream) | Wed–Thu | Log every asset/request state change to `asset_action_histories` table. Per design decision Q13 |
| API hardening: rate limiting, CORS | Thu–Fri | `slowapi` for rate limiting at 100 req/min/user |

### Frontend (3 people)

| Task | Target | Notes |
|------|--------|-------|
| Search & filter UI (multi-dimensional) | Mon–Wed | Filter bar with dropdowns + text search. Debounced API calls |
| Optimistic locking conflict UI | Wed–Thu | Show "this record was modified by someone else" dialog on 409 |
| i18n: all pages translated | Thu–Fri | zh-TW primary, en secondary. All user-facing strings externalized |
| UX polish: loading states, empty states, error toasts | Rolling | Consistent patterns across all pages |

### Milestone: `M4 — Feature Complete (Full)`
- [ ] Multi-dimensional search works with all filter combinations
- [ ] Optimistic locking: concurrent edit shows conflict to second user
- [ ] All UI text is i18n-ready (language switcher works)
- [ ] No broken flows end-to-end
- [ ] Rate limiting active on all endpoints

---

## Week 5 — Infra + Testing + Polish (May 12–16)

**Goal:** App is Dockerized, deployed to AWS, CI/CD pipeline green, test coverage ≥ 80%.

**Resources shift:**

| Role | People | Focus |
|------|--------|-------|
| Dev (bug fixes) | 2 | Fix issues found during testing, edge cases |
| Infra / DevOps | 2 | Docker, AWS, CI/CD, monitoring |
| QA / Testing | 1 | E2E tests, manual testing |

### Infra (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Dockerize FE + BE (multi-stage builds) | Mon–Tue | `docker compose` for local dev. Production images optimized |
| AWS setup: EC2 ×2 + ALB + RDS Multi-AZ | Tue–Thu | Per design.md §5.4. Use Terraform or manual setup |
| CI/CD pipeline expansion (deploy) | Wed–Thu | Push to `main` → build → test → deploy to AWS |
| Zero-downtime rolling deploy | Thu–Fri | ALB health checks + rolling update |
| S3 bucket for images | Wed | Migrate from local disk to S3. CloudFront optional |
| Security CI gates (full) | Wed–Thu | Add SonarQube, npm audit, pip-audit, OWASP Dependency-Check (per `09-testing-strategy.md` §SCA) |

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
| Health check endpoint (`/health`) | Mon–Tue | DB connectivity + app readiness |

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
| **3 FE PRs from Week 2 carry into Week 3 (#12, #13, auth guard)** | Active | Medium | Land all three by Tue EOD via Mon–Tue carry-over closure block. If auth guard PR slips past Tue, FE-3's manager UI (Wed–Thu) starts unblocked behind a feature flag and merges after auth guard lands |
| **Image display on repair detail page slips into Week 4** | Medium | Low | Backend image upload depends on Wed–Thu work; FE display task on Fri. If BE slips, FE renders placeholder thumbnails using mock URLs; real wiring lands first thing W4 |
| ~~UI library decision stalls past W2 Mon~~ | ~~Medium~~ Resolved | ~~High~~ | Closed in PR #8 — Ant Design v6 picked, layout shell shipped |
| FastAPI/SQLAlchemy ramp-up slows Week 1 | ~~Medium~~ Resolved | ~~High~~ | Backend landed on schedule (a0dfd95). No further action |
| AWS setup takes longer than expected | Medium | Medium | Start Docker in W5 Mon. If AWS delays, demo on local Docker Compose |
| Integration bugs pile up in W3–W4 | High | Medium | FE/BE pair-test each API as it's built in W2–W3. Don't wait until W4 |
| Presentation spec released late | Medium | Low | Start slides with known rubric (architecture 25%, testing 25%). Adjust layout later |
| Live demo fails during presentation | Low | High | Record backup demo video in Buffer week. Have screenshots as fallback |
| Security CI gates too strict / slow | Low | Medium | Start with minimal gates in W1 (lint + gitleaks), expand progressively in W5 |

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
