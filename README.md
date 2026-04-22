# Asset Management System

Course project for a cloud computing / software engineering class. The repository is a monorepo containing:

- `backend/` — FastAPI app, SQLAlchemy models, Alembic migrations, demo seed script
- `frontend/` — React + Vite + TypeScript shell with i18n
- `docs/` — requirements, roadmap, and full system-design document set

## Progress

### Week 1 — Foundation & CI Setup (Apr 14–18) — Mostly done

**Backend**

| Task | Status | Notes |
|------|--------|-------|
| Monorepo setup | ✅ | `backend/` + `frontend/`; OpenAPI at `/docs` |
| FastAPI scaffold + MySQL schema | ✅ | 4 tables (`users`, `assets`, `repair_requests`, `repair_images`) via Alembic; `version` column for optimistic locking |
| Seed script with demo data | ✅ | 50 assets, 2 managers + 2 holders, 10 repair requests across all statuses |
| CI: lint + type-check + tests | ✅ | `ruff` + `mypy --strict` + `pytest --cov` on every push/PR |

**Frontend**

| Task | Status | Notes |
|------|--------|-------|
| React + Vite project | ✅ | TypeScript strict mode; `react-router-dom` v6 |
| i18n framework | ✅ | `react-i18next` + `i18next-browser-languagedetector`; language switcher in `src/components/LanguageSwitcher.tsx`; locales under `src/i18n/locales/` |
| UI library | ❌ (carry-over → Week 2) | No Ant Design / shadcn yet — open team decision |
| Layout shell (sidebar + header) | ❌ (carry-over → Week 2) | `App.tsx` still a placeholder; no routing shell |
| CI: lint + type-check + tests + build | ✅ | ESLint 9 (flat config) + `tsc --noEmit` + `vitest` + `vite build` |

**CI & Security Gates**

| Task | Status | Notes |
|------|--------|-------|
| GitHub Actions workflow | ✅ | 5 jobs: backend, frontend, secrets, sast, sonarqube |
| gitleaks (pre-commit + CI) | ✅ | Secret scanning from day 1 |
| Semgrep SAST | ✅ | OWASP top-10 rules |
| SonarCloud quality gate | ✅ (pulled from Week 5) | Consumes FE+BE coverage; BLOCKER/CRITICAL/MAJOR findings resolved |
| Reviewer auto-assignment | ✅ (bonus) | Round-robin by path ownership |

### Week 2 — Auth & Core Features Start (Apr 21–25) — Planned

**Backend**

| Task | Status | Notes |
|------|--------|-------|
| Auth API (register, login, JWT) | ⏳ Planned | RBAC middleware (`holder` vs `manager`); reuse bcrypt hashing from seed script |
| Asset CRUD APIs (create, read, update, list) | ⏳ Planned | Pagination + basic filtering; replace current 501 on `POST /assets` |
| Repair Request APIs (submit + list) | ⏳ Planned | Server-side FSM validation per `docs/system-design/11-asset-fsm.md` |

**Frontend**

| Task | Status | Notes |
|------|--------|-------|
| UI library pick + setup | ⏳ **Must land Mon** | Carry-over from Week 1. Default to shadcn if team undecided by Mon EOD |
| Layout shell (sidebar + header) | ⏳ Mon–Tue | Carry-over from Week 1. Role-aware menu, not yet enforced |
| Login / Register pages | ⏳ Tue–Wed | Connected to real auth API; zh-TW + en strings |
| Auth guard + role-based routing | ⏳ Wed–Thu | Redirect holder away from manager-only pages |
| Asset list page (table + pagination) | ⏳ Wed–Fri | Manager sees all; holder sees own assets |
| Repair request submit form | ⏳ Thu–Fri | Asset ID, fault description, image upload (max 5) |

**Week 2 milestone (`M2 — Auth + CRUD Basics`):** login/register end-to-end · manager registers an asset · holder views own assets · holder submits a repair request · RBAC enforced on FE + BE.

> Full weekly plan, risks, and resource allocation live in [docs/roadmap.md](docs/roadmap.md).

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
│       └── i18n
│           └── locales
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
