# E2E tests (Playwright)

Browser-driven tests that exercise the React app against the **real** FastAPI +
MySQL backend. Unlike the Vitest suite under `frontend/src/__tests__/` (which
mocks `@/api`), these tests catch contract drift between the frontend and the
backend.

## Layout

```
e2e/
  playwright.config.ts   # baseURL, locale, webServer, reporters
  tsconfig.json          # extends ../tsconfig.json, adds @playwright/test types
  fixtures/              # shared test setup (login helpers, credentials)
  pages/                 # Page Object Models — one class per route
  tests/                 # *.spec.ts — the actual assertions
```

## Prerequisites

1. **Node 22.x** — `package.json` engines field is enforced. Switch with
   `nvm use 22` (or `fnm use 22`) before running anything.
2. **Backend + MySQL up.** The suite does NOT auto-start them; bring them up
   yourself before running tests:
   ```bash
   docker compose up -d mysql backend
   ```
3. **Seed the bootstrap manager.** The default test credentials are
   `admin@example.com` / `ChangeMe123` (sourced from `BOOTSTRAP_MANAGER_*` env
   vars — see `backend/.env.example`). The seed is destructive, so only run it
   against a disposable DB:
   ```bash
   docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py
   ```
4. **Playwright browsers.** Already installed once via `npx playwright install
   chromium`. Re-run after Playwright version bumps.

The Vite dev server is auto-started by Playwright's `webServer` config; you do
not need to run `npm run dev` yourself.

## Running

```bash
# Headless run (CI default)
npm run test:e2e

# Open the Playwright UI to debug interactively
npm run test:e2e:ui

# Headed mode (watch a real browser window)
npm run test:e2e:headed

# Filter to a single spec
npm run test:e2e -- tests/auth.spec.ts
```

After a failure run, open the HTML report:

```bash
npx playwright show-report e2e/playwright-report
```

## Conventions

- **One Page Object per route** under `pages/`. Locators live as readonly
  fields; specs never call `page.locator(".css-class")` directly.
- **Selectors prefer role/label over CSS.** Ant Design class names are
  unstable across minor versions. Use `getByRole`, `getByLabel`, `getByText`.
- **No `waitForTimeout`.** Use `expect(...).toBeVisible()` and other
  auto-retrying assertions. Hardcoded sleeps flake under CI load.
- **Each test is independent.** Tests get a fresh browser context (cookies,
  localStorage) automatically. Don't rely on state left by other tests.
- **AAA structure** — Arrange / Act / Assert. Matches the project-wide
  convention from `.claude/rules/testing.md`.
- **Locale is locked to `en-US`** in the chromium project so i18n-driven label
  assertions are stable. A zh-TW project can be added later for i18n
  regression coverage.

## Credentials in CI

Set `E2E_MANAGER_EMAIL` and `E2E_MANAGER_PASSWORD` as GitHub Actions secrets
when wiring this into `ci.yml`. The defaults in `fixtures/auth.ts` are safe to
commit because they are the documented seed values, not production secrets.
