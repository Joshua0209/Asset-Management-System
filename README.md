# Asset Management System

Week 1 foundation for the Asset Management System course project. This repository now includes:

- `backend/`: FastAPI app scaffold, SQLAlchemy models, Alembic migrations, and demo seed script
- `frontend/`: React + Vite monorepo frontend shell
- `docs/`: requirements, roadmap, and design references

## Week 1 Progress

### Backend

| Task | Status | Notes |
|------|--------|-------|
| Monorepo setup | ✅ Done | `backend/` + `frontend/` layout; OpenAPI auto-generated at `/docs` |
| FastAPI scaffold + MySQL schema | ✅ Done | All 4 tables (`users`, `assets`, `repair_requests`, `repair_images`) via Alembic migration; `version` column on all mutable tables for optimistic locking |
| Seed script with demo data | ✅ Done | 50 assets, 2 managers + 2 holders, 10 repair requests across all status states |
| CI pipeline (lint + type-check + tests) | ✅ Done | `ruff` + `mypy` + `pytest` run on every push/PR via `.github/workflows/ci.yml` |

### Frontend

| Task | Status | Notes |
|------|--------|-------|
| React + Vite project in monorepo | ✅ Done | TypeScript strict mode enabled; `react-router-dom` v6 installed |
| UI library setup | ❌ Missing | No UI library (Ant Design or shadcn) added yet |
| i18n framework (`react-i18next`) | ❌ Missing | Not installed or configured |
| Layout: sidebar nav + header | ❌ Missing | `App.tsx` is a static placeholder; no layout shell or routing structure |
| CI pipeline (ESLint + type-check) | ✅ Done | ESLint 9 (flat config) + `tsc --noEmit` + `vite build` run on every push/PR via `.github/workflows/ci.yml` |

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
└── docs
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

FastAPI docs will be available at `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server defaults to `http://localhost:5173`.

## Pre-commit hooks (recommended)

`gitleaks` runs in CI to block any commit with secrets, but you should also run it locally before pushing:

```bash
pip install pre-commit
pre-commit install        # one-time per clone
pre-commit run --all-files  # optional: scan everything once
```

Hooks configured in [.pre-commit-config.yaml](.pre-commit-config.yaml):
- **gitleaks** — secret scan
- **ruff** — lint + autofix on backend Python files
- standard hygiene (trailing whitespace, EOF newline, merge-conflict markers, large files)

## Environment

Backend defaults are stored in [backend/.env.example](/Users/jnes0/cloud_native/Asset-Management-System/backend/.env.example:1).
Update `DATABASE_URL` to point to your local MySQL instance before running migrations or seed data.
If you use the bundled [docker-compose.yml](/Users/jnes0/cloud_native/Asset-Management-System/docker-compose.yml:1),
the default `DATABASE_URL` already matches the container settings.
