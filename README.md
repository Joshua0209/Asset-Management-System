# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript + Ant Design with i18n and theme toggle
- `docs/` — requirements, roadmap, and full system-design document set

## Open before the Jun 2 presentation

- **k6 sustained-QPS run against the deployed ALB.** Six scenario scripts under `load/`, the per-VU JWT cache, and the per-request OTel-bridged access log are merged (PR [#85](https://github.com/Joshua0209/Asset-Management-System/pull/85)); the prod deploy is up. The sustained run with `K6_PROMETHEUS_RW_*` into Grafana Cloud Prom and the screenshots for the testing slide still need to happen.
- **Presentation:** slides first draft, demo script, May 26 + May 29 rehearsals.

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
├── infra
│   ├── ecs               # ECS task definitions + IAM/OIDC notes
│   └── grafana-cloud     # Dashboard JSONs + sync script
├── load                  # k6 scripts (smoke, load, stress, spike, soak, consistent)
└── docs
    ├── designs
    ├── plans             # observability implementation + prod migration plans
    └── system-design
```

## Quick start

Two ways to run the stack locally. Pick one — they target the same ports (5173 frontend, 8000 backend, 3306 MySQL), so don't run both at the same time.

### Option A — Full stack in Docker (recommended)

Builds and runs MySQL + backend + frontend with hot-reload via bind mounts. The backend container runs `alembic upgrade head` on each start, then serves with `uvicorn --reload`. The frontend runs `vite --host` so HMR reaches the browser.

```bash
cp backend/.env.example backend/.env  # first time: create local backend secrets
docker compose up --build       # first time: builds backend + frontend images
docker compose up -d             # subsequent runs
docker compose logs -f backend   # tail backend logs
docker compose down              # stop (data persists in named volumes)
docker compose down -v           # stop and wipe MySQL + uploads
```

The backend service reads `backend/.env` through `env_file`; keep that file
local and untracked. Compose still overrides `DATABASE_URL` to use the `mysql`
service hostname inside the Docker network.

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

### Repair-image storage (local disk in dev, S3 in production)

Uploaded repair images go through a small `ImageStorage` Protocol in `app/services/image_storage.py` with two implementations:

- **Local disk** (default in dev / docker compose). Files land under `REPAIR_UPLOAD_DIR` (default `uploads/repair-requests/`, git-ignored) with on-disk layout `<repair-request-id>/<image-id>.<ext>`.
- **S3** (production). Selected by `REPAIR_IMAGE_BACKEND=s3` + `REPAIR_S3_BUCKET=<name>` (optional `REPAIR_S3_PREFIX`). Enabled by default in `infra/aws/tasks/backend-task-def.json`. Boto3 is lazy-imported, so dev environments do not need it.

`repair_images.image_url` stores a backend storage key (the same `<rr-id>/<image-id>.<ext>` shape for both backends), **not** a public URL or filesystem path. The public URL `/api/v1/images/<id>` is computed at the schema layer (`RepairImageRead.url`), so cutting over from local to S3 needs no DB rewrite.

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

### Frontend e2e tests

Run the frontend e2e suite after the app stack is already running in another terminal.

1. In terminal A (repository root), reset and seed the demo data before e2e:

    ```bash
    docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py
    ```

2. In terminal A, start the app stack from the repository root:

    ```bash
    docker compose up --build
    ```

3. In terminal B, install the frontend dependencies and Playwright browsers:

    ```bash
    cd frontend
    npm install
    npx playwright install
    ```

4. Run the e2e tests from `frontend/` in this order:

    ```bash
    npm run test:e2e
    npm run test:e2e:demo
    ```

`npm run test:e2e` should run first. Use `npm run test:e2e:demo` after that when you want the headed demo project run.

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

`.github/workflows/ci.yml` runs quality and security gates on PRs. `.github/workflows/cd.yml` runs the same quality gates plus deploy jobs on pushes to `main`. A `changes` job (dorny/paths-filter) inside the quality workflow emits `backend` / `frontend` / `dashboards` booleans that path-filtered downstream jobs gate on.

On pull requests and pushes to `main`, it runs:

| Job | Tool(s) | Path-filtered |
|-----|---------|---------------|
| `backend-lint` | ruff | backend |
| `backend-typecheck` | mypy `--strict` | backend |
| `backend-test` | pytest + coverage (uploads `backend-coverage`) | backend |
| `frontend-test` | vitest + coverage (uploads `frontend-coverage`) | frontend |
| `frontend` | ESLint + tsc + vite build | frontend |
| `secrets` | gitleaks | no |
| `sast` | Semgrep (OWASP top-10 ruleset) | no |
| `pip-audit` | Python production dependency audit, HIGH+ | backend |
| `npm-audit` | Node production dependency audit, HIGH+ | frontend |
| `trivy` | Filesystem CVE scan, HIGH+CRITICAL (no `ignore-unfixed`) | backend or frontend |
| `sonarqube` | SonarCloud quality gate; needs both `backend-test` and `frontend-test` to succeed | no |
| `dashboards-validate` | Dry-run parse + UID/structure check on Grafana Cloud dashboard JSONs | dashboards |

On pushes to `main` and manual dispatch, after those gates pass, it also runs:

| Job | Purpose | Trigger |
|-----|---------|---------|
| `build-and-push` | Build backend/frontend production images from `Dockerfile.prod` and push to ECR via OIDC | push to main / dispatch |
| `migrate-database` | Run `alembic upgrade head` as a one-off Fargate task before any new task set boots; gates `deploy-backend` | backend changes only |
| `deploy-backend` | Render the backend ECS task definition and perform a rolling update with `wait-for-service-stability` | backend changes only |
| `deploy-frontend` | Render the frontend ECS task definition and perform a rolling update | frontend changes only |
| `sync-dashboards` | Sync dashboard JSONs to Grafana Cloud after `dashboards-validate` | dashboards changes |

Destructive demo-data seeding is a separate manual workflow, [`seed.yml`](.github/workflows/seed.yml): `workflow_dispatch` only, gated behind typing `SEED` to confirm plus the `production-destructive` environment reviewers. It seeds against the backend service's already-running task definition, so it does not rebuild or redeploy.

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
| `BOOTSTRAP_MANAGER_EMAIL` | Yes | Email for the seeded first manager |
| `BOOTSTRAP_MANAGER_PASSWORD` | Yes | Password for the seeded first manager — **change before exposing outside the team** |
| `BOOTSTRAP_MANAGER_NAME` | No | Display name for the seeded manager |
| `BOOTSTRAP_MANAGER_DEPARTMENT` | No | Department for the seeded first manager |
| `BOOTSTRAP_MANAGER_LOCATION` | No | Regular workplace/site for the seeded first manager |
| `CORS_ALLOWED_ORIGINS` | No | JSON array of allowed origins (default `["http://localhost:5173"]`) |
| `CORS_ALLOWED_METHODS` | No | JSON array of allowed HTTP methods (default `["GET","POST","PATCH","OPTIONS"]` — matches the API's actual surface; broaden when a new verb is needed) |
| `CORS_ALLOWED_HEADERS` | No | JSON array of allowed request headers (default `["Authorization","Content-Type"]`) |
| `RATE_LIMIT_ENABLED` | No | Master kill switch for slowapi rate limiting (default `true`; set `false` for load tests) |
| `RATE_LIMIT_AUTHENTICATED` | No | Default tier applied to all authenticated routes (default `100/minute`) |
| `RATE_LIMIT_ANONYMOUS` | No | Per-IP tier on `POST /auth/login` and `POST /auth/register` (default `30/minute`) |
| `RATE_LIMIT_IMAGES` | No | Higher tier for `GET /api/v1/images/:id` to absorb attachment fan-out (default `300/minute`) |
