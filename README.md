# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript + Ant Design with i18n and theme toggle
- `docs/` — requirements, roadmap, and full system-design document set

## Status (as of Wed of Week 3, 2026-04-29)

**Weeks 1 & 2 — done.** Foundation, CI/CD, security gates (gitleaks + Semgrep + SonarCloud), Auth API, Asset CRUD, Repair Request submit/list, Ant Design UI shell, asset list page (mock data), and the i18n framework all shipped. See [docs/roadmap.md](docs/roadmap.md) for the full retrospective.

**Currently working on Week 3 — Core Features Complete (Apr 28 – May 2).** Goal: full repair workflow + all CRUD pages working end-to-end. Week 2 frontend carry-over entered Week 3; PR #12, PR #13, and auth guard/routing are completed after review, while Asset List API wiring remains open.

### Week 3 carry-over closure (Mon–Tue, FE only)

| Task | Status | Owner | Notes |
|------|--------|-------|-------|
| Land PR [#12](https://github.com/Joshua0209/Asset-Management-System/pull/12) — Login / Register pages | ✅ Done | FE-2 → FE-3 reviews | Merged after review; connected to real auth API |
| Land PR [#13](https://github.com/Joshua0209/Asset-Management-System/pull/13) — Repair request submit form | ✅ Done | FE-2 → FE-3 reviews | Merged after review; holder submit form available at `/repairs/new` |
| Open + land PR for auth guard + role-based routing | ✅ Done | FE-3 → FE-1 reviews | Merged after review; role-based route protection active |
| Wire Asset List to real `GET /assets` API | ⏳ Pending | FE-1 → FE-3 reviews | `frontend/src/pages/AssetList.tsx` still reads `frontend/src/mocks/assets.ts` (real `/assets` + `/assets/mine` wiring not landed) |

- [x] Login / Register pages landed and routed in app shell
- [x] Repair request submit form landed (holder route: `/repairs/new`)
- [x] Auth guard + role-based routing landed (`ProtectedRoute` + role landing redirect)
- [ ] Asset list wired to real `GET /assets` and `GET /assets/mine` (still mock-backed)

### Week 3 — Wed–Fri (compressed scope)

The team adopts a new FE division for Week 3: **split by audience, not by feature.** FE-1 owns every manager page, FE-2 owns every holder page, FE-3 owns integration & quality (PR review, merge coordination, vitest coverage, i18n keys, cross-cutting UX states).

#### Backend (2 people)

| Track | Owner | Target | Notes |
|-------|-------|--------|-------|
| Repair Request APIs (full workflow) | BE-1 | Mon–Wed | FSM `pending_review → under_repair → completed` and `pending_review → rejected`, all server-validated |
| Image upload endpoint | BE-2 | Wed–Thu | Upload-through-server, local disk for now, abstracted behind a service layer for future S3 migration |
| Asset assign / unassign / dispose | BE-2 | Thu–Fri | FSM transitions T2 (assign), T3 (unassign), T5 (dispose) |
| API documentation review | BE-1/BE-2 | Fri | Verify FastAPI auto-docs match `12-api-design.md` contract |

#### FE-1 — Manager pages

| Page | Target | Notes |
|------|--------|-------|
| Asset create / edit | Wed–Thu | Form validation, category dropdown (2-level flat list), purchase amount + warranty expiry validation matching backend Pydantic schema |
| Asset assign / unassign | Thu | FSM T2/T3 — manager picks holder from user list, sets assignment date |
| Asset dispose | Thu | FSM T5 — confirm dialog with reason; status → `disposed` |
| Repair review / approve / reject | Thu–Fri | Approve → fill repair plan form (vendor, planned cost, planned date). Reject → confirm dialog with reason. Drives `pending_review → under_repair` or `pending_review → rejected` |
| Repair complete | Fri | Fill repair date, content, actual cost, vendor → mark complete. Drives `under_repair → completed` |

#### FE-2 — Holder pages

| Page | Target | Notes |
|------|--------|-------|
| Asset detail | Wed | Read-only view of asset metadata; manager view (FE-1) layers in edit/assign actions |
| My assets list (holder view) | Wed | Reuses the shared list table component but reads from `GET /assets/mine` |
| Repair request list | Wed–Thu | Status badges, sortable columns. Manager sees all; holder sees own only — same component, role-aware filter |
| Repair request detail | Thu–Fri | Timeline view of workflow stages, status transitions, manager comments |
| Image display on repair detail | Fri | Thumbnail grid, click-to-enlarge modal. **Risk:** depends on backend image upload landing Wed–Thu. Fallback: placeholder thumbnails using mock URLs if BE slips, real wiring lands first thing W4 |

#### FE-3 — Integration & quality

| Responsibility | Cadence | Notes |
|----------------|---------|-------|
| PR review for FE-1 and FE-2 work | Rolling | Same-day SLA on review to keep FE-1/FE-2 unblocked |
| Merge coordination | Rolling | Resolve conflicts between FE-1/FE-2 branches (likely on shared layout, routing, i18n keys). Keep `main` green |
| vitest coverage on new pages | Wed–Fri | Each new page ships with at least one render test + one role-gating test. Maintain ≥ 80% FE coverage |
| i18n keys (zh-TW + en) | Rolling | Audit `src/i18n/locales/` after each PR merges; no hardcoded user-facing strings |
| Cross-cutting UX (loading, empty, error) | Thu–Fri | Consistent patterns across manager + holder pages via Ant Design's `Spin`, `Empty`, `notification` |
| Optional: integration smoke test | Fri | Manual end-to-end run of the 3 critical flows (manager registers asset, holder submits repair, manager completes) before week close |

### Week 3 milestone (`M3 — Feature Complete (Core)`)

Manager registers + assigns assets · holder submits repair with images · manager approves/rejects/completes · status transitions update asset status automatically · images upload and display.

> Full weekly plan, risks, resource allocation, and rubric mapping live in [docs/roadmap.md](docs/roadmap.md).

## Repository layout

```text
.
├── backend
│   ├── alembic
│   ├── app
│   └── scripts
├── frontend
│   ├── public
│   └── src
│       ├── components
│       │   └── layout
│       ├── i18n
│       │   └── locales
│       └── pages
└── docs
    ├── designs
    └── system-design
```

## Quick start

### 0. Start MySQL

```bash
docker compose up -d mysql
```

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
python scripts/seed_demo_data.py
uvicorn app.main:app --reload
```

FastAPI docs: `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server: `http://localhost:5173`.

### Asset List data source (current)

The Asset List page is implemented and currently runs in a frontend-only mode:

- Data source: local dummy dataset in `frontend/src/mocks/assets.ts`
- UI: table + pagination + status tags in `frontend/src/pages/AssetList.tsx`
- Role behavior: manager/holder view simulated in page controls until auth + `/assets/mine` API are completed

This lets the team continue frontend work even when backend asset APIs or DB seed data are unavailable.

## Scripts reference

### Backend (run from `backend/`)

| Command | Description |
|---------|-------------|
| `ruff check .` | Lint |
| `mypy app` | Strict type-check |
| `pytest --cov=app --cov-report=term --cov-report=xml` | Tests with coverage |
| `alembic upgrade head` | Apply migrations |
| `python scripts/seed_demo_data.py` | Load demo data |
| `uvicorn app.main:app --reload` | Dev server |

### Frontend (run from `frontend/`)

| Command | Description |
|---------|-------------|
| `npm run dev` | Vite dev server (HMR) |
| `npm run build` | `tsc && vite build` — production build with type check |
| `npm run preview` | Preview production build |
| `npm run lint` | ESLint |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest (run once) |
| `npm run test:coverage` | Vitest with V8 coverage |

Asset List focused test: `src/__tests__/AssetList.test.tsx`.

## Pre-commit hooks

```bash
pip install pre-commit
pre-commit install           # one-time per clone
pre-commit run --all-files   # optional: scan everything once
```

Hooks in [.pre-commit-config.yaml](.pre-commit-config.yaml):
- **gitleaks** — secret scan
- **ruff** — lint + autofix on backend Python files
- standard hygiene (trailing whitespace, EOF newline, merge-conflict markers, large files)

## CI pipeline

`.github/workflows/ci.yml` runs five jobs on every push and PR:

| Job | Tool(s) |
|-----|---------|
| `backend` | ruff → mypy → pytest (uploads `coverage.xml`) |
| `frontend` | ESLint → tsc → vitest (uploads `lcov.info`) → vite build |
| `secrets` | gitleaks |
| `sast` | Semgrep (OWASP top-10 ruleset) |
| `sonarqube` | SonarCloud quality gate (consumes coverage artifacts) |

### SonarQube / SonarCloud

Config: [sonar-project.properties](sonar-project.properties). Host is hardcoded to `https://sonarcloud.io` in the workflow.

Required GitHub Actions secret:
- `SONAR_TOKEN` — user token from SonarCloud → My Account → Security

## Reviewer auto-assignment

Round-robin assignment runs on PR open/reopen via [.github/workflows/assign-reviewers.yml](.github/workflows/assign-reviewers.yml):
- Touches `backend/**` → one of @Joshua0209, @jnes0824
- Touches `frontend/**` → one of @chueh0000, @emma3617, @Mimi94Mimi
- The PR author is excluded from their own pool
- Selection is deterministic (`pr_number % eligible.length`)

[.github/CODEOWNERS](.github/CODEOWNERS) only covers `/.github/` changes; team review is workflow-driven.

## Environment

Backend defaults live in [backend/.env.example](backend/.env.example). Update `DATABASE_URL` to point at your MySQL instance before running migrations or the seed script. The bundled [docker-compose.yml](docker-compose.yml) matches the default `DATABASE_URL`.

Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | MySQL connection string |
| `JWT_SECRET` | Yes | 32+ byte random secret — generate with `python -c 'import secrets; print(secrets.token_urlsafe(48))'` |
| `JWT_ALGORITHM` | No | Default `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | No | Default `720` (12 h) |
| `BOOTSTRAP_MANAGER_EMAIL` | No | Email for the seeded first manager (default `admin@example.com`) |
| `BOOTSTRAP_MANAGER_PASSWORD` | No | Password for the seeded first manager — **change before exposing outside the team** |
| `BOOTSTRAP_MANAGER_NAME` | No | Display name for the seeded manager |
| `BOOTSTRAP_MANAGER_DEPARTMENT` | No | Department for the seeded manager |
| `CORS_ALLOWED_ORIGINS` | No | JSON array of allowed origins (default `["http://localhost:5173"]`) |
