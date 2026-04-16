# Asset Management System

> 資產管理系統 — Course project for cloud computing / software engineering

## What Was Done

This commit sets up the **React + Vite frontend scaffold** in a monorepo layout, completing the Week 1 roadmap task "React + Vite project in monorepo".

### Monorepo Root

| File | Purpose |
|------|---------|
| `.gitignore` | Covers Node, Python, IDE, and OS files |
| `.editorconfig` | 2‑space for JS/TS/JSON, 4‑space for Python, LF line endings |
| `.node-version` | Pins Node 22 LTS across team |
| `pnpm-workspace.yaml` | Declares `frontend/` as a pnpm workspace; backend stays independent (Python/pip) |
| `.gitattributes` | Marks `pnpm-lock.yaml` as binary merge to avoid lockfile conflicts |

### Frontend (`frontend/`)

| Category | Key Files |
|----------|-----------|
| **Build** | `vite.config.ts` (proxy `/api` → `:8000`, `@/` alias), `tsconfig.app.json` (strict mode) |
| **UI** | Ant Design 6 themed with project design tokens (`#C8102E` brand red) |
| **Styling** | `src/styles/tokens.ts` → `theme.ts` → `global.css` (Inter + Noto Sans TC) |
| **Routing** | `src/routes/index.tsx` — `/login`, `/manager/*`, `/holder/*` with layout shell |
| **Layout** | `AppLayout`, `Sidebar` (role-aware nav), `Header` (user info + logout) |
| **Pages** | `LoginPage` (functional form), Manager Dashboard, Asset List, Holder Dashboard (placeholders) |
| **API Layer** | Axios client with JWT interceptor + endpoint stubs (`auth`, `assets`, `repairs`) |
| **Types** | Domain models: `User`, `Asset`, `RepairRequest` matching API contract |
| **State** | Zustand `authStore` + `useAuth` hook |
| **Mock API** | MSW handlers — enables FE development without running backend |
| **DX** | ESLint + Prettier, `.env.example`, 8 npm scripts |

### FE–BE Independence Mechanisms

| Mechanism | How It Helps |
|-----------|-------------|
| Vite dev proxy (`/api` → `:8000`) | No CORS issues, FE/BE on separate ports |
| MSW mock handlers | FE devs build pages without waiting for BE endpoints |
| Separate `package.json` + scripts | FE CI runs/passes independently of BE |
| Branch naming convention | Clarifies team ownership per branch |
| `.gitattributes` lockfile strategy | Eliminates painful `pnpm-lock.yaml` merge conflicts |

---

## How to Run

### Prerequisites

- **Node.js 22** LTS — install via [fnm](https://github.com/Schniz/fnm) or [nvm](https://github.com/nvm-sh/nvm)
- **pnpm** — `npm i -g pnpm`

### Install & Start

```bash
# Install all dependencies (from repo root)
pnpm install

# Start frontend dev server → http://localhost:5173
cd frontend
pnpm dev
```

### Mock Mode (no backend needed)

```bash
cd frontend
VITE_ENABLE_MOCKS=true pnpm dev
```

MSW intercepts all `/api/v1/*` requests in the browser and returns realistic mock data. Perfect for FE-only development.

### Available Scripts (inside `frontend/`)

| Command | Description |
|---------|-------------|
| `pnpm dev` | Vite dev server on port 5173 |
| `pnpm build` | TypeScript check + production build |
| `pnpm preview` | Preview production build locally |
| `pnpm typecheck` | Type-check only (no emit) |
| `pnpm lint` | ESLint |
| `pnpm lint:fix` | ESLint with auto-fix |
| `pnpm format` | Prettier write |
| `pnpm format:check` | Prettier check (CI) |

### Environment Variables

Copy `.env.example` → `.env.local` for local overrides:

```bash
cp frontend/.env.example frontend/.env.local
```

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `/api/v1` | Backend API base path |
| `VITE_ENABLE_MOCKS` | `false` | Enable MSW mock API |

---

## Branch Naming Convention

| Prefix | Team | Example |
|--------|------|---------|
| `fe/` | Frontend | `fe/login-page` |
| `be/` | Backend | `be/auth-api` |
| `infra/` | Shared | `infra/ci-pipeline` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, TypeScript 6 (strict) |
| UI | Ant Design 6 |
| State | Zustand 5 |
| API Client | Axios + TanStack React Query 5 |
| Routing | React Router 7 |
| Mock | MSW 2 |
| Backend (TBD) | FastAPI, SQLAlchemy, MySQL |
| Package Manager | pnpm |

## Documentation

See `docs/system-design/` for the full design document set (architecture, database, API contract, testing strategy, etc.).
