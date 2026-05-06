# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript + Ant Design with i18n and theme toggle
- `docs/` — requirements, roadmap, and full system-design document set

## Status (as of Week 4 — Active, 2026-05-06)

**Weeks 1–3 — done.** Foundation, CI/CD, security gates (gitleaks + Semgrep + SonarCloud), Auth API, Asset CRUD, the full repair-request workflow (submit → review → approve/reject → in-repair → complete), asset FSM transitions (assign / unassign / dispose), image upload + retrieval, manager workflow pages, and holder pages all shipped. See [docs/roadmap.md](docs/roadmap.md) for the full week-by-week retrospective.

**Currently working on Week 4 — Advanced Features & Integration (May 5–9).** Goal: multi-dimensional search, optimistic-locking conflict UI, audit log + asset history endpoint, API hardening (rate limiting, CORS), and i18n coverage across all pages. One M3 carry-over item lands first this week (see below).

### Week 3 leftover (carry-over into Week 4)

M3 is now 5/5 complete on the BE/FE delivery axis — PR [#27](https://github.com/Joshua0209/Asset-Management-System/pull/27) (image display on repair detail, via the new `AuthImage` component) merged 2026-05-06. One holder-flow UX gap surfaced during the W3 smoke test still needs to land first thing in Week 4:

| Task | Owner | Target | Notes |
|------|-------|--------|-------|
| **Resolve [issue #29](https://github.com/Joshua0209/Asset-Management-System/issues/29)** — asset-code dropdown on repair-submit form | FE-2 | Wed–Thu | `POST /repair-requests` requires asset UUID, but holders only know asset codes. Surfaced via the W3 integration smoke test. Fix: fetch the holder's own assets on page load, render `Select` (display `asset_code — name`, value = UUID); switch the `asset_id` field from text input |

### Week 4 — Advanced Features & Integration (May 5–9) — Active

Two server-side capabilities from the original W4 plan **already shipped earlier:**

- Multi-dim asset search — `GET /assets` already accepts `q` (across `asset_code`/`name`/`model`), `status`, `category`, `department`, `location`, `responsible_person_id`. W4 BE narrows to **composite indexes** per design.md §5.5; the FE filter bar is the remaining bulk.
- Optimistic locking is enforced on every update path — 4 endpoints in `assets.py` and 5 transitions in `repair_requests.py` check `version` and emit granular 409 codes (PR [#24](https://github.com/Joshua0209/Asset-Management-System/pull/24)). W4 work narrows to a verification pass + the FE conflict-resolution dialog.

Audit log + `GET /assets/:id/history` was explicitly deferred from Week 3's API contract review (PR [#28](https://github.com/Joshua0209/Asset-Management-System/pull/28)) and lands this week.

#### Backend (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Composite SQL indexes for asset search | Mon–Wed | Search API already shipped; performance-tune per design.md §5.5 |
| Optimistic locking verification pass | Mon | Already enforced server-side; confirm test coverage and document granular 409 codes for FE consumption |
| Audit log (event stream) + `GET /assets/:id/history` | Wed–Thu | New `asset_action_histories` model + migration. Endpoint deferred from Week 3 (PR #28). Per design decision Q13 |
| API hardening: rate limiting, CORS | Thu–Fri | `slowapi` for rate limiting at 100 req/min/user. CORS already wired (`cors_allowed_origins`); audit allowed origins for the AWS rollout |

#### Frontend (3 people)

| Task | Target | Notes |
|------|--------|-------|
| Search & filter UI (multi-dimensional) | Mon–Wed | Filter bar with dropdowns + text search. Debounced API calls |
| Optimistic locking conflict UI | Wed–Thu | Show "this record was modified by someone else" dialog on 409 `version_conflict` |
| i18n: all pages translated | Thu–Fri | zh-TW primary, en secondary. All user-facing strings externalized |
| UX polish: loading states, empty states, error toasts | Rolling | Consistent patterns across all pages |

#### Week 4 milestone — `M4 — Feature Complete (Full)`

- [ ] M3 carry-over closed: issue #29 fixed (PR #27 image display merged 2026-05-06)
- [x] Audit log (`asset_action_histories`) + `GET /assets/:id/history` shipped — every FSM transition writes a history row in the same transaction, manager-only paginated read endpoint exposes the trail
- [ ] Multi-dimensional search works with all filter combinations
- [ ] Optimistic locking: concurrent edit shows conflict to second user
- [ ] All UI text is i18n-ready (language switcher works)
- [ ] No broken flows end-to-end
- [ ] Rate limiting active on all endpoints

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

Two ways to run the stack locally. Pick one — they target the same ports (5173 frontend, 8000 backend, 3306 MySQL), so don't run both at the same time.

### Option A — Full stack in Docker (recommended)

Builds and runs MySQL + backend + frontend with hot-reload via bind mounts. The backend container runs `alembic upgrade head` on each start, then serves with `uvicorn --reload`. The frontend runs `vite --host` so HMR reaches the browser.

```bash
docker compose up --build       # first time: builds backend + frontend images
docker compose up -d             # subsequent runs
docker compose logs -f backend   # tail backend logs
docker compose down              # stop (data persists in named volumes)
docker compose down -v           # stop and wipe MySQL + uploads
```

**Seeding demo data (one-shot, destructive):** the seed script wipes all four tables before re-seeding, so it is not part of the boot command. Run it explicitly when you want a fresh demo dataset:

```bash
docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py
```

Endpoints:
- Frontend: `http://localhost:5173`
- FastAPI docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Source edits on the host flow into the running containers — no rebuild needed unless you change `pyproject.toml` or `package.json`. If you do, run `docker compose build <service>` to refresh the image.

### Option B — Local dev (no Docker for app code)

Use this when you want a native Python venv and Node toolchain — e.g. when an IDE debugger needs in-process attach, or when iterating on the seed script.

#### 0. Start MySQL only

```bash
docker compose up -d mysql
```

#### 1. Backend

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

#### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server: `http://localhost:5173`.

### Asset List data source (current)

The Asset List page is role-aware and mode-aware:

- Real mode (`VITE_USE_MOCK_AUTH=false`):
    - Manager: `GET /api/v1/assets`
    - Holder: `GET /api/v1/assets/mine`
- Mock mode (`VITE_USE_MOCK_AUTH=true`):
    - Uses shared frontend mock runtime state in `frontend/src/mocks/mockBackend.ts`

This keeps the same page behavior across environments while allowing development without a live backend.

### Repair-image storage (local disk, Phase 1–2)

Uploaded repair images are written to `REPAIR_UPLOAD_DIR` (default `uploads/repair-requests/`, git-ignored). The on-disk layout is `<repair-request-id>/<image-id>.<ext>`, and `repair_images.image_url` stores that relative key — **not** a public URL. The public URL `/api/v1/images/<id>` is computed at the schema layer (`RepairImageRead.url`) so the storage backend can be swapped (e.g., S3 in Week 5) without migrating any DB rows.

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

Backend defaults live in [backend/.env.example](backend/.env.example). Update `DATABASE_URL` to point at your MySQL instance before running migrations or the seed script under **Option B**. The bundled [docker-compose.yml](docker-compose.yml) matches the default `DATABASE_URL` for the host-mode flow, and overrides it to `mysql+pymysql://root:password@mysql:3306/asset_management` when running under **Option A** so the backend container can resolve the `mysql` service hostname.

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
