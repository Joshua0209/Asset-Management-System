# Backend

FastAPI app for the Asset Management System. SQLAlchemy + Alembic + MySQL 8, JWT auth with RBAC, optimistic locking on mutable tables, OTLP-native observability (traces, metrics, logs to Grafana Cloud).

For the human-facing quick start, env-var table, and CI overview, see the root [README.md](../README.md). For non-obvious conventions (auth, image storage, health endpoints, docker compose gotchas), see [CLAUDE.md](../CLAUDE.md).

## Layout

```text
backend/
├── alembic/                # Migrations
├── app/
│   ├── api/v1/endpoints/   # FastAPI routers (auth, users, assets, repair-requests, images, dashboard, observability)
│   ├── core/               # config, security, rate_limit, observability
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   └── services/           # image_storage, audit_log
├── scripts/seed_demo_data.py
└── tests/
```

## Local development

The recommended flow is the full docker compose stack from the repo root (`docker compose up`), which runs MySQL + backend + frontend with hot-reload. This file covers the **native** flow when you want an in-process debugger or to iterate on the seed script.

### Prerequisites

- Python 3.11+
- A running MySQL 8 instance. The simplest path is `docker compose up -d mysql` from the repo root.

### Setup (native, no Docker for app code)

```bash
# Always use a virtualenv, never pip install globally.
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

cp .env.example .env             # then edit DATABASE_URL / JWT_SECRET / BOOTSTRAP_MANAGER_*
alembic upgrade head
AMS_SEED_CONFIRM=1 python scripts/seed_demo_data.py   # destructive: wipes all four tables
uvicorn app.main:app --reload
```

FastAPI docs: <http://localhost:8000/docs>. Health probe: <http://localhost:8000/health>. Readiness (DB connectivity): <http://localhost:8000/ready>.

The seed script is destructive and gated behind `AMS_SEED_CONFIRM=1` on purpose. Do not wire it into a boot command. Under docker compose, run it as a one-off: `docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py`.

## Scripts reference

| Command | Description |
|---------|-------------|
| `ruff check .` | Lint (matches CI `backend-lint`) |
| `mypy app` | Strict type-check (matches CI `backend-typecheck`) |
| `pytest --cov=app --cov-report=term --cov-report=xml` | Tests with coverage (matches CI `backend-test`) |
| `pytest -n auto` | Parallel test run via `pytest-xdist` |
| `alembic upgrade head` | Apply migrations |
| `alembic revision --autogenerate -m "msg"` | Generate a new migration from model changes |
| `AMS_SEED_CONFIRM=1 python scripts/seed_demo_data.py` | Load demo data (destructive) |
| `uvicorn app.main:app --reload` | Dev server with autoreload |

## Migrations

- Use backward-compatible migrations only (add columns; never remove or rename in the same release).
- For breaking changes, ship the two-phase plan documented in [docs/system-design/08-deployment-operations.md](../docs/system-design/08-deployment-operations.md): (1) add new column, write to both, (2) backfill, (3) drop old column.
- In production, the `migrate-database` CI job runs `alembic upgrade head` as a one-off Fargate task before `deploy-backend` starts the rolling update, so the new task set never boots against an unmigrated schema. Rollback to a prior schema still requires a hand-written revert migration.

## Authoritative conventions

These are easy to miss from code alone. Read before adding endpoints or touching auth:

- **RBAC dependencies** live in `app/api/deps.py`. Use the `CurrentUser` / `ManagerUser` / `HolderUser` aliases on route signatures instead of inlining JWT decoding.
- **Error envelope**: every 4xx/5xx returns `{"error": {"code": "...", "message": "..."}}` via the global `HTTPException` handler in `app/main.py`. Do not return raw FastAPI `{"detail": ...}`.
- **Password policy**: enforced by `validate_password_policy` in `app/core/security.py` (≥8 chars, ≥1 letter, ≥1 digit). Reuse it; do not re-implement.
- **Login anti-enumeration**: `POST /auth/login` returns the same 401 body whether the email is unknown or the password is wrong, and always runs a bcrypt verify against a dummy hash to neutralise timing.
- **Optimistic locking**: mutable tables carry a `version` column. Use it on update paths; do not reach for `SELECT … FOR UPDATE`.
- **Image storage**: writes go through the `ImageStorage` Protocol in `app/services/image_storage.py`. `LocalImageStorage` for dev, `S3ImageStorage` for production (selected by `REPAIR_IMAGE_BACKEND=s3`). `repair_images.image_url` stores a backend key, not a public URL.
- **Health probes**: `/health` is liveness (always 200), `/ready` runs `SELECT 1` and returns 503 when the DB is unreachable so the ALB drains the target without killing an otherwise-fine container.

## Observability

OTLP-native. Three signals (traces, metrics, logs) push directly to Grafana Cloud over gRPC; continuous profiling is opt-in via `pyroscope-io` in the `[prod]` extra. All of it is off by default: with `OTEL_ENABLED=false` (the dev default), the backend boots with zero outbound telemetry.

To wire local dev to Grafana Cloud, fill in the `OTEL_*` and `PYROSCOPE_*` variables in `.env` (see [`backend/.env.example`](.env.example)) and flip `OTEL_ENABLED=true`. In production these come from the `ams-grafana-cloud` Secrets Manager entry referenced by `infra/aws/tasks/backend-task-def.json`. See [docs/system-design/08-deployment-operations.md](../docs/system-design/08-deployment-operations.md) § Observability for the full topology.

`WEB_CONCURRENCY=1` is an invariant in production: OTel providers and the Pyroscope sampling thread are process-wide singletons installed once at startup. Bumping the worker count above 1 needs an explicit post-fork re-init for both. See [infra/aws/tasks/README.md](../infra/aws/tasks/README.md).

## Production image

`Dockerfile.prod` is a multi-stage build that installs `.[prod]` (no dev extras) and supervises uvicorn through `gunicorn` with `uvicorn.workers.UvicornWorker` for clean SIGTERM handling during ECS rolling deploys. The dev `Dockerfile` is bind-mount + `--reload` and is only used by `docker-compose.yml`.
