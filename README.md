# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript + Ant Design with i18n and theme toggle
- `docs/` — requirements, roadmap, and full system-design document set

## Status (as of Week 5 — Active, 2026-05-13)

**Weeks 1–4 — done.** Foundation, CI/CD, security gates (gitleaks + Semgrep + SonarCloud), Auth API, Asset CRUD, the full repair-request workflow (submit → review → approve/reject → in-repair → complete), asset FSM transitions (assign / unassign / dispose), image upload + retrieval, manager + holder pages, audit log + `GET /assets/:id/history`, composite search indexes, optimistic-locking pin tests, rate limiting + CORS tightening, and full i18n parity (212 keys × 2 locales) all shipped. See [docs/roadmap.md](docs/roadmap.md) for the full week-by-week retrospective.

**Currently working on Week 5 — Infra + Testing + Polish (May 12–16).** Goal: production multi-stage Dockerfiles, AWS deployment (EC2 ×2 + ALB + RDS Multi-AZ), CI/CD push-to-deploy, ≥ 80% test coverage with E2E for 6 critical flows, plus the one remaining W4 FE carry-over — multi-dimensional search/filter UI on the asset list.

### Week 4 carry-over into Week 5

W4 closed late on Tuesday May 13. Audit log, composite indexes, optimistic-locking pin tests, full i18n parity, granular 409 surfacing, and — newly merged this morning — the purpose-built conflict-resolution dialog with data refresh (PR [#55](https://github.com/Joshua0209/Asset-Management-System/pull/55)) all shipped. See [docs/roadmap.md](docs/roadmap.md) Week 4 section for the full ledger. **One FE item carries:**

| Task | Owner | Target | Notes |
|------|-------|--------|-------|
| **Multi-dimensional search/filter UI** on `AssetList.tsx` | Dev seat (FE) | Mon–Tue | Filter bar with text search (`q`) + dropdowns (`status`, `category`, `department`, `location`, `responsible_person_id`). Debounced, URL-state-driven. BE filter API + composite indexes already shipped — this is pure FE. Closes the last open M4 outcome |

### Week 5 — Infra + Testing + Polish (May 12–16) — Active

Resource shift this week: 5 devs → **2 dev (W4 search-UI carry-over + two new FE tasks added May 13)** + **2 infra/DevOps (Docker prod, AWS, CI/CD deploy)** + **1 QA (E2E + manual)**.

**Two new FE tasks decided this week (not in the original W5 plan):**

| Task | Why now | Notes |
|------|---------|-------|
| **Unify manager + holder page pairs into role-aware pages** | Today the same surface is built twice — `AssetList`/`MyAssetList`, `Reviews`/`RepairRequestList`, `ReviewDetail`/`RepairRequestDetail`. Each pair carries duplicate logic for filters, columns, and table chrome; only the actions differ. Unifying reduces maintenance surface before the W6 demo polish window and makes the role gates explicit in one place | Merge each pair into a single page where actions/columns/dropdowns are toggled by `useCurrentUser().role`. Reference template: `frontend/src/pages/AssetDetail.tsx` already does this. Touches `App.tsx` routes, three page pairs, and the sidebar nav. Coordinate with the conflict-dialog wiring from PR [#55](https://github.com/Joshua0209/Asset-Management-System/pull/55) — same files |
| **Apply DESIGN.md theme to the UI** | The UI ships Antd defaults today, but the project's design system (`docs/designs/DESIGN.md` — TSMC-inspired: precision, restraint, hierarchy through typography, bilingual parity) has been authoritative since Week 2 and was never wired in. W6 demo is in 10 working days; the theme is the highest-visibility polish item | Wire `docs/designs/design-tokens.json` (W3C Design Tokens format) through Antd's `ConfigProvider` seed tokens. Audit components against the four pillars: 8px grid + tabular-nums; red as accent never surface, no gradients, no emoji; hierarchy through typography weight not decoration; light-mode first with 1px luminance hairline in dark mode. Reference visual: `docs/designs/design-preview.html` |

**In-flight on `feat/cicd-prod-pipeline` (not yet PR'd):** six commits already code-complete most of the W5 infra checklist — production Dockerfiles (BE gunicorn+UvicornWorker, FE nginx:alpine), `/health` liveness + `/ready` DB-readiness, `S3ImageStorage` behind the existing `ImageStorage` Protocol, full SCA gates (pip-audit + npm audit + OWASP Dependency-Check), and a deploy workflow (`.github/workflows/deploy.yml`) that builds → pushes to ECR → renders ECS task defs → rolling update with `wait-for-service-stability`. Auth via GitHub OIDC. **Architecture pivot:** EC2 ×2 → ECS Fargate. Task defs committed under `infra/ecs/` with placeholders documented in `infra/ecs/README.md`. **Pending operator action:** AWS provisioning of ECR + ECS cluster/service + RDS Multi-AZ + S3 bucket + OIDC IAM role.

#### Infra (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Production multi-stage Dockerfiles (FE + BE) | Mon–Tue | ✅ Code-complete on `feat/cicd-prod-pipeline`. PR + merge still required |
| AWS setup: ECS Fargate + ALB + RDS Multi-AZ | Tue–Thu | Pending operator action. ECS task definitions committed; see `infra/ecs/README.md` for required GitHub Actions secrets/vars |
| CI/CD pipeline expansion (deploy to ECR + ECS) | Wed–Thu | ✅ Code-complete on `feat/cicd-prod-pipeline`. OIDC-based deploy, no long-lived AWS keys |
| Zero-downtime rolling deploy | Thu–Fri | ✅ Code-complete on `feat/cicd-prod-pipeline`. `wait-for-service-stability` + `/ready` drains bad targets during RDS failover |
| S3 bucket for images | Wed | ✅ Code-complete on `feat/cicd-prod-pipeline`. `S3ImageStorage` selected via `REPAIR_IMAGE_BACKEND=s3`; storage keys unchanged so cutover needs no DB rewrite |
| Security CI gates (full SCA) | Wed–Thu | ✅ Code-complete on `feat/cicd-prod-pipeline`. `pip-audit` + `npm audit --omit=dev --audit-level=high` + `dependency-check --failOnCVSS 7` |
| Health check endpoints (`/health` + `/ready`) | Mon–Tue | ✅ Code-complete on `feat/cicd-prod-pipeline`. Compose healthcheck already points at `/ready` |

#### Testing (1 QA + all devs contribute)

| Task | Target | Notes |
|------|--------|-------|
| Unit tests: business logic, validation, auth | Mon–Thu | pytest — focus on status transitions, optimistic locking, RBAC |
| Integration tests: all API endpoints | Wed–Fri | httpx + pytest covering all CRUD + workflow + error cases |
| E2E: 6 critical flows | Thu–Fri | Playwright — login, submit repair, approve, complete, search, register asset |

#### Dev (2 people — W4 carry-over, new FE scope, bug fixes)

| Task | Target | Notes |
|------|--------|-------|
| Multi-dim search/filter UI on `AssetList.tsx` | Mon–Tue | W4 FE carry-over described above |
| Unify manager + holder page pairs into role-aware pages | Tue–Thu | New W5 scope. Three page pairs, mechanical refactor against `AssetDetail.tsx` template |
| Apply DESIGN.md theme via `ConfigProvider` + four-pillar audit | Wed–Fri | New W5 scope. Wire `design-tokens.json` and audit components for restraint/precision/hierarchy/bilingual parity |
| Bug fixes from integration testing | Rolling | Prioritize workflow-breaking bugs |
| Edge cases: empty states, validation errors | Mon–Wed | |
| Performance: add DB indexes if queries slow | Thu–Fri | Per `07-database-design.md § Index Strategy` |

#### Week 5 milestone — `M5 — Deployed & Tested`

- [ ] W4 FE carry-over closed: search/filter UI on Asset List
- [ ] Manager/holder page pairs unified into role-aware pages
- [ ] DESIGN.md theme applied (tokens through `ConfigProvider`, four-pillar audit clean)
- [ ] `feat/cicd-prod-pipeline` reviewed, PR'd, merged
- [ ] AWS resources provisioned (ECR + ECS + RDS + S3 + OIDC IAM role)
- [ ] App running on AWS (accessible via public URL)
- [ ] CI/CD: push to main auto-deploys
- [ ] Zero-downtime deploy demonstrated
- [ ] Test coverage ≥ 80% (unit + integration)
- [ ] E2E: 6 flows passing
- [ ] All security CI gates passing (SAST + SCA + secret scan)

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
| `CORS_ALLOWED_METHODS` | No | JSON array of allowed HTTP methods (default `["GET","POST","PATCH","OPTIONS"]` — matches the API's actual surface; broaden when a new verb is needed) |
| `CORS_ALLOWED_HEADERS` | No | JSON array of allowed request headers (default `["Authorization","Content-Type"]`) |
| `RATE_LIMIT_ENABLED` | No | Master kill switch for slowapi rate limiting (default `true`; set `false` for load tests) |
| `RATE_LIMIT_AUTHENTICATED` | No | Default tier applied to all authenticated routes (default `100/minute`) |
| `RATE_LIMIT_ANONYMOUS` | No | Per-IP tier on `POST /auth/login` and `POST /auth/register` (default `30/minute`) |
| `RATE_LIMIT_IMAGES` | No | Higher tier for `GET /api/v1/images/:id` to absorb attachment fan-out (default `300/minute`) |
