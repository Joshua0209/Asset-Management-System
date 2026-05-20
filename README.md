# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript + Ant Design with i18n and theme toggle
- `docs/` — requirements, roadmap, and full system-design document set

## Status (as of Week 6 — Active, 2026-05-20)

**Weeks 1–5 — done.** Foundation, CI/CD, security gates (gitleaks + Semgrep + SonarCloud + pip-audit + npm audit + OWASP Dependency-Check), Auth API, Asset CRUD, the full repair-request workflow, asset FSM transitions, image upload + retrieval (now backed by `S3ImageStorage` in prod), manager + holder pages reorganized by role with the two largest pages decomposed into folder-modules, audit log + `GET /assets/:id/history`, composite search indexes + multi-dimensional asset filter/sort UI, optimistic-locking pin tests + conflict-resolution dialog, rate limiting + CORS tightening, full i18n parity (212 keys × 2 locales), production multi-stage Dockerfiles, `/health` + `/ready` probes, and the OIDC-based ECR → ECS Fargate rolling-deploy pipeline. See [docs/roadmap.md](docs/roadmap.md) for the full week-by-week retrospective.

**Currently working on Week 6 — Observability + Demo Prep (May 19–23).** Goal: instrument backend + frontend with the **Grafana observability stack** (Prometheus + Loki + Tempo + Pyroscope + Alloy + cAdvisor), stand it up locally via a compose overlay, provision dashboards, run k6 load + stress tests, finish the DESIGN.md theme pass, ship the Playwright E2E suite for the 6 critical flows, and merge PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) to land the operator-side AWS provisioning that PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58) was already pointing at.

### Week 5 — Infra + Testing + Polish (May 12–16) — Closed

Major merges:

- **PR [#58](https://github.com/Joshua0209/Asset-Management-System/pull/58)** — prod CI/CD pipeline (ECS Fargate, multi-stage Dockerfiles, `S3ImageStorage`, `/ready` probe, OIDC deploy, full SCA gates).
- **PR [#59](https://github.com/Joshua0209/Asset-Management-System/pull/59)** — frontend reorganized by role into `pages/holder/` + `pages/manager/`, the 594-line `ReviewDetail` and 564-line `AssetDetail` decomposed into folder-modules sharing a `useSubmitAction` hook, inconsistent `REPAIR_REQUEST_STATUS_COLORS` unified, `@/` path alias adopted across 200 imports.
- **PR [#61](https://github.com/Joshua0209/Asset-Management-System/pull/61)** — multi-dimensional asset list filter + sort UI on a shared `listControls` module (closes the last open M4 outcome).
- **PR [#60](https://github.com/Joshua0209/Asset-Management-System/pull/60)** — rate-limited auth endpoints no longer 500 on the third failed login, CORS preflight unblocked.
- **PR [#62](https://github.com/Joshua0209/Asset-Management-System/pull/62)** — seed-data hardening: DISPOSED transitions, audit-log rows, email collisions, category enum drift.

**Carries into W6:** DESIGN.md theme application (token wiring through Antd `ConfigProvider`), operator-side AWS provisioning (PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) is open with the placeholder hydration + IAM roles + `ams/prod/app` secret), the Playwright E2E suite, and a coverage measurement run.

### Week 6 — Observability + Demo Prep (May 19–23) — Active

Resource shift this week: 5 devs → **1 dev (DESIGN.md theme + demo polish)** + **2 infra (backend instrumentation + Grafana stack + AWS provisioning)** + **1 QA (Playwright E2E + coverage)** + **1 presentation (slides + script)**.

**Why a Grafana stack instead of CloudWatch:** the original W6 plan called for CloudWatch metrics + alarms. The team is pivoting to a self-hosted Grafana stack (Prometheus + Loki + Tempo + Pyroscope + Alloy + cAdvisor) modelled on the `2025-05-observability-demo/` reference lab, so the live demo can showcase real metric/log/trace/profile correlation in a single tool without an AWS console login. CloudWatch is still produced by the ECS task logs for free and stays in the architecture diagram, but it is not the demo surface.

#### Observability stack (compose overlay)

| Layer        | Tool                  | What it does in AMS                                                                                  |
|--------------|------------------------|-------------------------------------------------------------------------------------------------------|
| Metrics      | **Prometheus**         | Scrapes `/metrics` on FastAPI (`prometheus-fastapi-instrumentator`) + cAdvisor container metrics      |
| Logs         | **Loki**               | Centralized log store; structured JSON logs from backend + CLF from the prod-image nginx              |
| Traces       | **Tempo**              | OTLP traces from backend (FastAPI + SQLAlchemy auto-instrumentation) and the browser SDK              |
| Profiling    | **Pyroscope**          | Continuous Python profiling via `pyroscope-io` SDK in the backend                                     |
| Collector    | **Grafana Alloy**      | Single agent: reads Docker JSON logs, scrapes Prom targets, receives OTLP, forwards to each backend   |
| Container    | **cAdvisor**           | CPU + memory utilization vs. cgroup limits                                                            |
| Dashboards   | **Grafana**            | RED, USE, Golden Signals, plus an AMS-flow dashboard ("Repair Journey")                               |
| Load gen     | **k6**                 | Constant-arrival-rate traffic across the 6 critical flows; results in Prom via remote-write           |

#### Infra / Observability (2 people)

| Task | Target | Notes |
|------|--------|-------|
| Backend Prometheus metrics (`/metrics`) | Mon–Tue | `prometheus-fastapi-instrumentator` plus custom counters for FSM transitions + 409 conflicts. Excluded from auth + rate limit |
| Backend OpenTelemetry traces | Mon–Wed | Auto-instrument FastAPI + SQLAlchemy. OTLP export to `alloy:4317`. `trace_id` propagated into structured logs |
| Backend structured JSON logs | Mon–Tue | Replace default access log with `{"level","service","replica","method","path","status","duration_ms","trace_id"}` |
| Backend continuous profiling | Wed | `pyroscope-io` SDK, app name `ams-backend.<replica>`, lazy-imported |
| Frontend browser OTLP | Tue–Wed | `@opentelemetry/sdk-trace-web` + auto-instrumentations-web, OTLP-HTTP to Alloy on `:4318` |
| `docker-compose.observability.yml` overlay | Tue–Wed | Brings up Grafana + Prom + Loki + Tempo + Pyroscope + Alloy + cAdvisor; mirrors `2025-05-observability-demo/docker-compose.yml` structure |
| Alloy config + Grafana dashboards | Wed–Thu | Provisioned dashboards: Operations Overview, Service Drilldown, Repair Journey, Logs/Traces/Profiles correlation |
| k6 load + stress test | Thu | Sustain peak QPS for 10 min; find breakpoint where P95 > 3s or error rate > 1%. Screenshots for slides |
| AWS provisioning carry-over | Mon–Tue | Merge PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63); confirm push-to-main triggers ECS rolling update; ALB target group → `/ready` |

#### QA / Testing (1 person)

| Task | Target | Notes |
|------|--------|-------|
| Playwright E2E: 6 critical flows | Mon–Wed | Login, holder submits repair, manager approves with repair plan, manager completes repair, manager registers asset, multi-dim asset search |
| Coverage measurement + gap fill | Tue–Thu | `pytest --cov` + `npm run test:coverage` against the current suite; target ≥ 80%; SonarQube quality gate must pass |
| Run E2E under load | Thu | Pair with infra: run Playwright against the stack while k6 generates background traffic |

#### Dev (1 person — DESIGN.md theme + polish)

| Task | Target | Notes |
|------|--------|-------|
| DESIGN.md theme via `ConfigProvider` + four-pillar audit | Mon–Wed | W5 carry-over. Wire `docs/designs/design-tokens.json` through Antd; audit visible-on-demo surfaces for precision (8px grid + tabular-nums), restraint (red as accent only, no gradients/emoji), hierarchy through typography, bilingual parity |
| Demo data: realistic seed | Thu | Believable company/asset names + repair histories spanning all FSM states |
| Final UX polish for demo flow | Thu–Fri | Focus order, default sort orders, animation timing on the 6 demo flows |
| Merge small consistency PR [#65](https://github.com/Joshua0209/Asset-Management-System/pull/65) | Mon | "Fault Content" → "Fault Description"; Reviews list shows Request ID; `formatDateTime` follows i18n locale |

#### Week 6 milestone — `M6 — Observed & Demo Ready`

- [ ] DESIGN.md theme applied (W5 carry)
- [ ] AWS resources provisioned + app reachable on public URL (PR [#63](https://github.com/Joshua0209/Asset-Management-System/pull/63) merged)
- [ ] Backend instrumented: `/metrics`, OTLP traces, structured JSON logs, Pyroscope profiles
- [ ] Frontend instrumented: browser OTLP
- [ ] Grafana stack runs via `docker compose -f docker-compose.yml -f docker-compose.observability.yml up`
- [ ] At least four dashboards provisioned (Operations Overview, Service Drilldown, Repair Journey, Logs/Traces/Profiles correlation)
- [ ] One end-to-end correlation demo: dashboard click → Loki log line → Tempo trace → Pyroscope flamegraph for the same window
- [ ] k6 load test report (sustained QPS for 10 min) + stress test breakpoint (P95 > 3s)
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
