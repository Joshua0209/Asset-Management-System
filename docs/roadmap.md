# Asset Management System — Development Roadmap

**Team:** 5 people (2 Backend, 3 Frontend at start)
**Timeline:** Apr 14 – May 26 (rehearsal) / Jun 2 (presentation)
**Scope:** Phase 2 architecture implementation + live demo + slides + report
**Tech Stack (recommended):** Next.js (FE) + Express + Prisma + MySQL (BE), monorepo

---

## Timeline Overview

```
Week 1  Apr 14–18  ██████████  Foundation & Setup            5 dev (2 BE + 3 FE)
Week 2  Apr 21–25  ██████████  Core Features                 5 dev (2 BE + 3 FE)
Week 3  Apr 28–02  ██████████  Feature Complete & Integrate  5 dev (2 BE + 3 FE)
Week 4  May 05–09  ██████████  Infra + Testing + Polish      2 dev + 2 infra/test + 1 QA
Week 5  May 12–16  ██████████  Harden + Demo Prep            1 dev + 2 infra/test + 2 pres
Week 6  May 19–23  ██████████  Buffer & Presentation Prep    1 dev + 4 pres/polish
        May 26     ▶ Rehearsal
        Jun 02     ▶ Presentation
```

---

## Week 1 — Foundation & Setup (Apr 14–18)

**Goal:** Everyone can run the project locally and start coding features by Friday.

**Resources:** 2 BE + 3 FE (all 5)

### Backend (2 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Monorepo setup (Turborepo or Nx) | Tue Apr 15 | Shared `packages/types` for FE/BE type sharing |
| Express + Prisma + MySQL schema | Wed Apr 16 | All 4 tables: users, assets, repair_requests, repair_images. Include `version` column for optimistic locking from day 1 |
| Auth API (register, login, JWT) | Fri Apr 18 | RBAC middleware: `holder` vs `manager` roles |
| Seed script with demo data | Fri Apr 18 | ~50 assets, 2 users per role, ~10 repair requests |
| API documentation (Swagger/OpenAPI) | Fri Apr 18 | Auto-generated via express-swagger or tsoa |

### Frontend (3 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Next.js project in monorepo | Tue Apr 15 | App Router, TypeScript strict mode |
| UI library setup (Ant Design / shadcn) | Wed Apr 16 | Pick one; establish component patterns |
| i18n framework (`next-intl`) | Wed Apr 16 | zh-TW + en. Set up early — retrofitting is painful |
| Layout: sidebar nav, header, auth guard | Thu Apr 17 | Role-aware: show different menus for holder vs manager |
| Login / Register pages | Fri Apr 18 | Connected to real auth API |

### Milestone: `M1 — Skeleton Running`
- [ ] `npm run dev` starts both FE and BE
- [ ] Login works end-to-end
- [ ] DB schema deployed with seed data
- [ ] CI pipeline runs lint + type-check on every push

---

## Week 2 — Core Feature Development (Apr 21–25)

**Goal:** All CRUD operations and the repair workflow work end-to-end.

**Resources:** 2 BE + 3 FE

### Backend (2 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Asset CRUD APIs (create, read, update, list) | Wed Apr 23 | Include pagination, basic filtering |
| Repair Request APIs (full workflow) | Fri Apr 25 | State machine: `pending_review → under_repair → completed` and `pending_review → rejected`. Status transitions validated server-side |
| Image upload endpoint | Fri Apr 25 | Upload-through-server (simpler, per design decision Q4). Store to local disk for now, abstract with a service layer for future S3 migration |
| Input validation + error handling | Fri Apr 25 | Use `zod` or `joi` for request validation. Shared schemas in `packages/types` |

### Frontend (3 people)

| Task | Deadline | Owner | Notes |
|------|----------|-------|-------|
| Asset list page (table + pagination) | Wed Apr 23 | FE-1 | Manager view: all assets. Holder view: own assets only |
| Asset detail / create / edit pages | Fri Apr 25 | FE-1 | Form validation, category dropdown (2-level flat list) |
| Repair request: submit form | Wed Apr 23 | FE-2 | Asset ID input, fault description, image upload (max 5) |
| Repair request: list + detail pages | Fri Apr 25 | FE-2 | Status badges, timeline view of workflow stages |
| Manager: review/approve/reject UI | Thu Apr 24 | FE-3 | Approve → fill repair details form. Reject → confirm dialog |
| Manager: complete repair UI | Fri Apr 25 | FE-3 | Fill repair date, content, plan, cost, vendor → mark complete |

### Milestone: `M2 — Feature Complete (Core)`
- [ ] Manager can register asset, assign to holder
- [ ] Holder can view own assets, submit repair request
- [ ] Manager can approve/reject repair, fill details, complete repair
- [ ] Status transitions update asset status automatically
- [ ] Images upload and display on repair detail page

---

## Week 3 — Feature Complete & Integration (Apr 28 – May 2)

**Goal:** All features working, polished, and integrated. Advanced features added.

**Resources:** 2 BE + 3 FE

### Backend (2 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Multi-dimensional search & filter API | Wed Apr 30 | Filter by: asset ID, name, model, location, person, status, department, category. Composite SQL indexes per design.md §5.5 |
| Optimistic locking enforcement | Wed Apr 30 | `WHERE version = ?` on all update endpoints. Return HTTP 409 on conflict |
| Audit log (event stream) | Fri May 2 | Log every asset/request state change to `audit_logs` table. Per design decision Q13 |
| API hardening: rate limiting, CORS, helmet | Fri May 2 | `express-rate-limit` at 100 req/min/user |

### Frontend (3 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Search & filter UI (multi-dimensional) | Wed Apr 30 | Filter bar with dropdowns + text search. Debounced API calls |
| Optimistic locking conflict UI | Thu May 1 | Show "this record was modified by someone else" dialog on 409 |
| i18n: all pages translated | Fri May 2 | zh-TW primary, en secondary. All user-facing strings externalized |
| UX polish: loading states, empty states, error toasts | Fri May 2 | Consistent patterns across all pages |
| Role-based routing guards | Wed Apr 30 | Redirect holder away from manager-only pages |

### Milestone: `M3 — Feature Complete (Full)`
- [ ] Multi-dimensional search works with all filter combinations
- [ ] Optimistic locking: concurrent edit shows conflict to second user
- [ ] All UI text is i18n-ready (language switcher works)
- [ ] No broken flows end-to-end

---

## Week 4 — Infra + Testing + Polish (May 5–9)

**Goal:** App is Dockerized, deployed to AWS, CI/CD pipeline green, test coverage ≥ 80%.

**Resources shift:**

| Role | People | Focus |
|------|--------|-------|
| Dev (bug fixes) | 2 | Fix issues found during testing, edge cases |
| Infra / DevOps | 2 | Docker, AWS, CI/CD, monitoring |
| QA / Testing | 1 | E2E tests, manual testing |

### Infra (2 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Dockerize FE + BE (multi-stage builds) | Tue May 6 | `docker compose` for local dev. Production images optimized |
| AWS setup: EC2 ×2 + ALB + RDS Multi-AZ | Thu May 8 | Per design.md §5.4. Use Terraform or manual setup |
| CI/CD pipeline (GitHub Actions) | Thu May 8 | Push to `main` → build → test → deploy to AWS |
| Zero-downtime rolling deploy | Fri May 9 | ALB health checks + rolling update (ECS or docker on EC2 with blue-green) |
| S3 bucket for images | Wed May 7 | Migrate from local disk to S3. CloudFront optional but nice |

### Testing (1 person + all devs contribute)

| Task | Deadline | Notes |
|------|----------|-------|
| Unit tests: business logic, validation, auth | Thu May 8 | Jest. Focus on: status transitions, optimistic locking, RBAC |
| Integration tests: all API endpoints | Fri May 9 | Supertest. Cover all CRUD + workflow + error cases |
| E2E tests: 6 critical flows | Fri May 9 | Playwright. Login, submit repair, approve, complete, search, register asset |

### Dev (2 people — bug fixes)

| Task | Deadline | Notes |
|------|----------|-------|
| Fix bugs from integration testing | Rolling | Prioritize workflow-breaking bugs |
| Edge cases: empty states, validation errors | Wed May 7 | |
| Performance: add DB indexes if queries slow | Fri May 9 | Per design.md §7.3 index strategy |

### Milestone: `M4 — Deployed & Tested`
- [ ] App running on AWS (accessible via public URL)
- [ ] CI/CD: push to main auto-deploys
- [ ] Zero-downtime deploy demonstrated (deploy during load test)
- [ ] Test coverage ≥ 80% (unit + integration)
- [ ] E2E: 6 flows passing

---

## Week 5 — Harden + Demo Prep (May 12–16)

**Goal:** System is demo-ready. Presentation materials started.

**Resources shift:**

| Role | People | Focus |
|------|--------|-------|
| Dev (final fixes) | 1 | Last bug fixes, demo-critical polish |
| Infra / Monitoring | 2 | Monitoring, alerting, load testing |
| Presentation | 2 | Slides draft, demo script, report writing |

### Infra / Monitoring (2 people)

| Task | Deadline | Notes |
|------|----------|-------|
| CloudWatch metrics + alarms | Wed May 14 | CPU, error rate, latency, health check. Per design.md §5.8 |
| Load test with k6 or Locust | Thu May 15 | Sustain peak QPS for 10 min. Capture metrics for presentation |
| Stress test: find breaking point | Thu May 15 | Document max QPS before P95 > 3s |
| Health check endpoint (`/health`) | Tue May 13 | DB connectivity + app readiness |

### Presentation (2 people)

| Task | Deadline | Notes |
|------|----------|-------|
| Architecture slides (system diagram, ER diagram, sequence diagrams) | Fri May 16 | Per rubric: 25% on architecture design |
| Demo script: rehearse the 6 critical flows | Fri May 16 | Prepare fallback plan if live demo fails (screenshots/video) |
| Testing strategy slides (pyramid, coverage report, load test results) | Fri May 16 | Per rubric: 25% on testing |
| Report draft (if format known) | Fri May 16 | Start with what you know; refine after spec release |

### Dev (1 person)

| Task | Deadline | Notes |
|------|----------|-------|
| Demo data: realistic seed for presentation | Wed May 14 | Real-looking company names, asset names, repair histories |
| Final UX polish for demo flow | Fri May 16 | Make the 6 demo flows buttery smooth |

### Milestone: `M5 — Demo Ready`
- [ ] Live demo runs without errors for all 6 flows
- [ ] Monitoring dashboard shows real metrics
- [ ] Load test report with charts
- [ ] Slides first draft complete

---

## Week 6 — Buffer & Presentation Prep (May 19–23)

**Goal:** Everything polished. Team rehearsed. Ready for May 26 rehearsal.

**Resources:** 1 dev (on-call for fixes) + 4 on presentation/polish

| Task | Deadline | Notes |
|------|----------|-------|
| Slides finalized | Wed May 21 | Incorporate feedback from team review |
| Report finalized | Wed May 21 | PDF, A4 format per spec |
| Full rehearsal (internal) | Thu May 22 | Time the presentation, practice transitions |
| Demo environment verified | Fri May 23 | AWS instance healthy, data seeded, all flows work |
| Backup demo: screen recording | Fri May 23 | Record the 6 flows as video backup |
| Code quality: lint clean, no warnings | Wed May 21 | Per rubric: 10% on code quality |

### Milestone: `M6 — Presentation Ready`
- [ ] Slides reviewed by all team members
- [ ] Report PDF submitted (if deadline falls here)
- [ ] Team has rehearsed at least twice
- [ ] Backup demo video recorded
- [ ] AWS environment stable for 48+ hours

---

## May 26 — Rehearsal

## Jun 2 — Presentation

---

## Resource Allocation Summary

```
         W1      W2      W3      W4      W5      W6
        Apr14   Apr21   Apr28   May05   May12   May19
        ─────   ─────   ─────   ─────   ─────   ─────
BE-1    [setup ] [APIs ] [search] [infra] [monit] [pres ]
BE-2    [setup ] [APIs ] [audit ] [infra] [load ] [pres ]
FE-1    [setup ] [asset] [i18n ] [test ] [pres ] [pres ]
FE-2    [setup ] [repair][filter] [bugs ] [pres ] [pres ]
FE-3    [setup ] [mgr  ] [polish][QA/e2e][fixes] [fixes]

Legend:
  setup  = project setup, skeleton, auth
  APIs   = core CRUD + workflow endpoints
  asset  = asset management pages
  repair = repair request pages
  mgr    = manager approval/completion UI
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
  fixes  = last-minute fixes
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Backend framework ramp-up slows Week 1 | Medium | High | Use Express (team knows JS). Seed script + Swagger by Fri W1 is the early warning |
| AWS setup takes longer than expected | Medium | Medium | Start Docker in W4 Mon. If AWS delays, demo on local Docker Compose |
| Integration bugs pile up in W3 | High | Medium | FE/BE pair-test each API as it's built in W2. Don't wait until W3 |
| Presentation spec released late | Medium | Low | Start slides with known rubric (architecture 25%, testing 25%). Adjust layout later |
| Live demo fails during presentation | Low | High | Record backup demo video in W6. Have screenshots as fallback |

---

## Dependency Map

```
M1 (Skeleton) ──► M2 (Core Features) ──► M3 (Feature Complete)
                                              │
                                              ├──► M4 (Deployed & Tested)
                                              │         │
                                              │         ├──► M5 (Demo Ready)
                                              │         │         │
                                              │         │         ▼
                                              │         │    M6 (Presentation Ready)
                                              │         │         │
                                              │         │         ▼
                                              │         │    Rehearsal (May 26)
                                              │         │         │
                                              │         │         ▼
                                              │         │    Presentation (Jun 2)
                                              │
                                              └──► Slides/Report can start in parallel from M3
```

**Critical path:** M1 → M2 → M3 → M4 → M5 → M6 → Rehearsal

**Parallel track:** Slides/report writing can begin at M3 (Week 4) since architecture is settled.

---

## Evaluation Rubric Mapping

| Rubric | Weight | Where It's Covered |
|--------|--------|--------------------|
| Requirements → Implementation | 30% | W1–W3: User stories from Requirements.md → working features |
| Code Quality | 10% | W1: ESLint + Prettier from day 1. W6: final lint clean |
| Architecture Design | 25% | design.md (done) + slides (W5). System diagrams, ER diagram, sequence diagrams |
| Testing | 25% | W4: unit + integration (80%+). W5: load test, stress test, E2E |
| Ops & Reliability | 10% | W4: Docker, CI/CD, zero-downtime. W5: monitoring, alerting, health checks |
