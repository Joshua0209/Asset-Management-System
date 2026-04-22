# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript shell with i18n
- `docs/` — requirements, roadmap, and full system-design document set

## Progress

### Backend

| Task | Status | Notes |
|------|--------|-------|
| Monorepo setup | ✅ | `backend/` + `frontend/`; OpenAPI at `/docs` |
| FastAPI scaffold + MySQL schema | ✅ | 4 tables (`users`, `assets`, `repair_requests`, `repair_images`) via Alembic; `version` column for optimistic locking |
| Seed script with demo data | ✅ | 50 assets, 2 managers + 2 holders, 10 repair requests across all statuses |
| CI: lint + type-check + tests | ✅ | `ruff` + `mypy --strict` + `pytest --cov` on every push/PR |

### Frontend

| Task | Status | Notes |
|------|--------|-------|
| React + Vite project | ✅ | TypeScript strict mode; `react-router-dom` v6 |
| i18n framework | ✅ | `react-i18next` + `i18next-browser-languagedetector`; language switcher in `src/components/LanguageSwitcher.tsx`; locales under `src/i18n/locales/` |
| UI library | ✅ | Ant Design (`antd`) and `@ant-design/icons` integrated; `ConfigProvider` utilized for native light/dark mode toggling |
| Layout shell (sidebar + header) | ✅ | Global layout using Ant Design's Layout components with collapsible sidebar, navigation, and theme toggle |
| CI: lint + type-check + tests + build | ✅ | ESLint 9 (flat config) + `tsc --noEmit` + `vitest` + `vite build` |

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
