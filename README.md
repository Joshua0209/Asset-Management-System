# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript + Ant Design with i18n and theme toggle
- `docs/` — requirements, roadmap, and full system-design document set

## Status (as of Week 6 — Observability migration, 2026-05-24)

**Weeks 1–5 — done.** Foundation, CI/CD, security gates (gitleaks + Semgrep + SonarCloud + pip-audit + npm audit + OWASP Dependency-Check), Auth API, Asset CRUD, the full repair-request workflow, asset FSM transitions, image upload + retrieval (now backed by `S3ImageStorage` in prod), manager + holder pages reorganized by role with the two largest pages decomposed into folder-modules, audit log + `GET /assets/:id/history`, composite search indexes + multi-dimensional asset filter/sort UI, optimistic-locking pin tests + conflict-resolution dialog, rate limiting + CORS tightening, full i18n parity (212 keys × 2 locales), production multi-stage Dockerfiles, `/health` + `/ready` probes, and the OIDC-based ECR → ECS Fargate rolling-deploy pipeline. See [docs/roadmap.md](docs/roadmap.md) for the full week-by-week retrospective.

**W6 status (2026-05-24): observability migrated to Grafana Cloud.** The original W6 plan (self-hosted Prometheus + Loki + Tempo + Pyroscope + Alloy + cAdvisor via `docker-compose.observability.yml`) was retired in favour of **Grafana Cloud as the single telemetry backend for both local dev and AWS production**. Phases 2–4 of [docs/plans/observability-prod-migration-plan.md](docs/plans/observability-prod-migration-plan.md) have landed on `feat/observability-phase4-aws`. Remaining: Phase 5 (k6 load-test rebase) and Phase 6 (delete repo-side dashboard JSONs once GC import is verified in production).

### Week 5 — Infra + Testing + Polish (May 12–16) — Closed

Major merges:

- **PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)** — prod CI/CD pipeline (ECS Fargate, multi-stage Dockerfiles, `S3ImageStorage`, `/ready` probe, OIDC deploy, full SCA gates).
- **PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59)** — frontend reorganized by role into `pages/holder/` + `pages/manager/`, the 594-line `ReviewDetail` and 564-line `AssetDetail` decomposed into folder-modules sharing a `useSubmitAction` hook, inconsistent `REPAIR_REQUEST_STATUS_COLORS` unified, `@/` path alias adopted across 200 imports.
- **PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61)** — multi-dimensional asset list filter + sort UI on a shared `listControls` module (closes the last open M4 outcome).
- **PR [#60](https://github.com/Joshua0209/Asset-Management-System/pull/60)** — rate-limited auth endpoints no longer 500 on the third failed login, CORS preflight unblocked.
- **PR [#62](https://github.com/Joshua0209/Asset-Management-System/pull/62)** — seed-data hardening: DISPOSED transitions, audit-log rows, email collisions, category enum drift.

**Carries into W6:** DESIGN.md theme application (token wiring through Antd `ConfigProvider`), the Playwright E2E suite, and a coverage measurement run. **Operator-side AWS provisioning landed on W6 Tue (PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) merged 2026-05-20)** with hardened `__NAME__` task-def placeholder substitution, fail-fast `require_var` guard against unset/empty GitHub `vars.*`, escape-safe sed (`\`, `|`, `&` neutralised), Secrets Manager refs pinned to `AWSCURRENT`, ECR image-scan gate at CVSS ≥ 7, identity-policy snippet, and deployment circuit breaker docs. The first `workflow_dispatch` smoke test is the only remaining piece. The smaller frontend consistency PR [#65](https://github.com/Joshua0209/Asset-Management-System/pull/65) also merged today: "Fault Content" → "Fault Description", `formatDateTime` follows the i18n locale, shared rendering helpers across `RepairRequestList` + `Reviews`.

### Week 6 — Observability + Demo Prep (May 19–24) — Migrated to Grafana Cloud

Resource shift this week: 5 devs → **1 dev (DESIGN.md theme + demo polish)** + **2 infra (backend instrumentation + observability + AWS provisioning)** + **1 QA (Playwright E2E + coverage)** + **1 presentation (slides + script)**.

**What changed mid-week (2026-05-24).** W6 began with a self-hosted Grafana stack (Prometheus + Loki + Tempo + Pyroscope + Alloy + cAdvisor) on a `docker-compose.observability.yml` overlay, with a planned CloudWatch datasource alongside. After Phase 1–5 of the original implementation plan landed (backend `/metrics`, OTLP traces, structured logs, Pyroscope profiles, browser OTLP, the Alloy collector, the compose overlay, and 6 provisioned dashboards), the team locked seven decisions on 2026-05-24 and pivoted to **Grafana Cloud as the single telemetry backend** for both local dev and AWS production. The compose overlay, Alloy config, Loki/Tempo/Prom/Pyroscope configs, cAdvisor, mysqld-exporter, and `make obs-*` targets were deleted. The backend was refactored OTLP-native — `prometheus_client` / `prometheus-fastapi-instrumentator` / the `/metrics` route are gone, replaced by OTel SDK Counter/Meter/Tracer/Logger that pushes direct to GC's hosted OTLP gateway. CloudWatch read-back runs through GC's hosted integration via a cross-account IAM role. Full plan in [docs/plans/observability-prod-migration-plan.md](docs/plans/observability-prod-migration-plan.md).

#### Observability stack (current — Grafana Cloud)

| Signal | Path | Notes |
|---|---|---|
| Traces | Backend OTel SDK → GC OTLP gateway (gRPC) | FastAPI + SQLAlchemy auto-instrumentation. `trace_id` stamped on every log record via the OTel logging bridge so GC Tempo ↔ Loki correlation works natively |
| Metrics | Backend OTel SDK → GC OTLP gateway | OTel `Counter`s for FSM transitions + optimistic-locking conflicts; HTTP server histograms via `FastAPIInstrumentor`. No scrape surface |
| Logs | structlog → stdlib root logger → OTel `LoggingHandler` → GC OTLP gateway → GC Loki | One transport for all three signals; ENVIRONMENT is a resource attribute, not an endpoint switch |
| Profiles | `pyroscope-io` SDK → GC hosted Pyroscope | Enabled in production (reverses the original W6 "off in prod" decision); `WEB_CONCURRENCY=1` keeps the sampling thread alive post-fork |
| AWS-side signals | GC hosted CloudWatch integration → cross-account role `ams-grafana-cloud-reader` | Pulls ALB / RDS / ECS Container Insights every 60s. Read-only IAM role, externalId from the GC console |
| Browser traces | `@opentelemetry/sdk-trace-web` → GC OTLP-HTTP | Page-load + fetch spans for the asset-list → repair-detail click path |
| Dashboards | 6 JSONs in `config/grafana/dashboards/` | Synced to the Grafana Cloud stack via `scripts/sync_grafana_cloud_dashboards.py --stack-url https://<stack>.grafana.net`. Phase 6 deletes them from the repo once GC import is verified |
| Load gen (Phase 5) | k6 → GC remote-write | PR [#84](https://github.com/Joshua0209/Asset-Management-System/pull/84) being rebased onto the post-Phase-3 branch |

Local `docker compose up` runs only `mysql + backend + frontend`. No observability containers. `OTEL_ENABLED` defaults off locally, so a credential-less boot is silent; supply GC credentials via `backend/.env` to push from a laptop.

#### Week 6 milestone — `M6 — Observed & Demo Ready`

- [ ] DESIGN.md theme applied (W5 carry)
- [x] AWS provisioning code merged (PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) merged 2026-05-20)
- [ ] App reachable on public URL — pending `workflow_dispatch` smoke test + first successful rolling deploy
- [x] Backend instrumented: OTLP traces, OTel metrics, OTel-bridged structured JSON logs, Pyroscope profiles (Phase 3 commit `1d3deef`)
- [x] Frontend instrumented: browser OTLP for the asset-list → repair-detail click path
- [x] Telemetry path wired to Grafana Cloud from both local dev and production (Phase 3 backend refactor + Phase 4 ECS task-def secrets/env)
- [x] Six dashboards provisioned in the repo and ready to sync to GC (Operations Overview, Service Drilldown, Repair Journey, Logs/Traces/Profiles correlation, MySQL, Start Here)
- [ ] End-to-end correlation demo verified in GC (dashboard → log line → trace → flamegraph) — operator-side work after the first prod deploy
- [ ] k6 load test report — Phase 5 (PR [#84](https://github.com/Joshua0209/Asset-Management-System/pull/84) rebase pending)
- [ ] Playwright: 6 flows passing locally + in CI
- [ ] Test coverage ≥ 80% (unit + integration), measured + SonarQube green
- [ ] Slides first draft complete

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

`.github/workflows/ci.yml` runs quality, security, and deploy gates.

On pull requests and pushes to `main`, it runs:

| Job | Tool(s) |
|-----|---------|
| `backend` | ruff → mypy → pytest (uploads `coverage.xml`) |
| `frontend` | ESLint → tsc → vitest (uploads `lcov.info`) → vite build |
| `secrets` | gitleaks |
| `sast` | Semgrep (OWASP top-10 ruleset) |
| `pip-audit` | Python production dependency audit |
| `npm-audit` | Node production dependency audit, HIGH+ |
| `dependency-check` | OWASP Dependency-Check, CVSS ≥ 7 |
| `sonarqube` | SonarCloud quality gate (consumes coverage artifacts) |

On pushes to `main` and manual dispatch, after those gates pass, it also runs:

| Job | Purpose |
|-----|---------|
| `build-and-push` | Build backend/frontend production images and push to ECR |
| `deploy-backend` | Render the backend ECS task definition and perform a rolling update |
| `deploy-frontend` | Render the frontend ECS task definition and perform a rolling update |

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
| `BOOTSTRAP_MANAGER_DEPARTMENT` | No | Department for the seeded manager |
| `CORS_ALLOWED_ORIGINS` | No | JSON array of allowed origins (default `["http://localhost:5173"]`) |
| `CORS_ALLOWED_METHODS` | No | JSON array of allowed HTTP methods (default `["GET","POST","PATCH","OPTIONS"]` — matches the API's actual surface; broaden when a new verb is needed) |
| `CORS_ALLOWED_HEADERS` | No | JSON array of allowed request headers (default `["Authorization","Content-Type"]`) |
| `RATE_LIMIT_ENABLED` | No | Master kill switch for slowapi rate limiting (default `true`; set `false` for load tests) |
| `RATE_LIMIT_AUTHENTICATED` | No | Default tier applied to all authenticated routes (default `100/minute`) |
| `RATE_LIMIT_ANONYMOUS` | No | Per-IP tier on `POST /auth/login` and `POST /auth/register` (default `30/minute`) |
| `RATE_LIMIT_IMAGES` | No | Higher tier for `GET /api/v1/images/:id` to absorb attachment fan-out (default `300/minute`) |
