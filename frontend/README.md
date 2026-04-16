# Frontend — Asset Management System

React + Vite + TypeScript + Ant Design

## Prerequisites

- **Node.js 22** LTS (use [fnm](https://github.com/Schniz/fnm) or [nvm](https://github.com/nvm-sh/nvm) — `.node-version` at repo root)
- **pnpm** (`npm i -g pnpm`)

## Quick Start

```bash
# From repo root (installs all workspace packages)
pnpm install

# Start dev server (http://localhost:5173)
cd frontend
pnpm dev

# Start with mock API (no backend needed)
VITE_ENABLE_MOCKS=true pnpm dev
```

## Scripts

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start Vite dev server on port 5173 |
| `pnpm build` | TypeScript check + production build |
| `pnpm preview` | Preview production build locally |
| `pnpm lint` | Run ESLint |
| `pnpm lint:fix` | Run ESLint with auto-fix |
| `pnpm format` | Format with Prettier |
| `pnpm format:check` | Check formatting (CI) |
| `pnpm typecheck` | TypeScript type-check without emit |

## Project Structure

```
src/
├── api/                    # API client layer
│   ├── client.ts           # Axios instance (auth interceptor, error handling)
│   ├── types.ts            # API response/error type wrappers
│   └── endpoints/          # One file per API domain (auth, assets, repairs)
├── components/             # Reusable UI components
│   └── layout/             # AppLayout, Sidebar, Header
├── hooks/                  # Custom React hooks (useAuth, etc.)
├── mocks/                  # MSW mock API handlers (dev only)
├── pages/                  # Route-level page components
│   ├── auth/               # Login, Register
│   ├── manager/            # Manager-role pages
│   └── holder/             # Holder-role pages
├── routes/                 # Routing configuration
├── stores/                 # Zustand state stores
├── styles/                 # Design tokens, Ant Design theme, global CSS
├── types/                  # Domain TypeScript types (asset, repair, user)
└── utils/                  # Utility functions
```

## API Proxy

In development, Vite proxies `/api/*` to `http://localhost:8000` (FastAPI backend). No CORS configuration needed during development.

## Mock API (MSW)

To develop frontend without a running backend:

```bash
VITE_ENABLE_MOCKS=true pnpm dev
```

MSW intercepts API calls in the browser and returns realistic mock data. Check `src/mocks/handlers.ts` to add or modify mock responses.

## Branch Naming Convention

| Prefix | Team | Example |
|--------|------|---------|
| `fe/` | Frontend | `fe/login-page` |
| `be/` | Backend | `be/auth-api` |
| `infra/` | Shared | `infra/ci-pipeline` |

## Design Tokens

All colors, typography, spacing are defined in `src/styles/tokens.ts` (sourced from `docs/system-design/13-design-tokens.md`). Ant Design's theme is configured via `src/styles/theme.ts` to use these tokens.

**Brand primary:** `#C8102E` · **Brand secondary:** `#0B3D91`

## Environment Variables

Copy `.env.example` to `.env.local` for local overrides:

```bash
cp .env.example .env.local
```

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `/api/v1` | Backend API base path |
| `VITE_ENABLE_MOCKS` | `false` | Enable MSW mock API |
