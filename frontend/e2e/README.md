# E2E tests (Playwright)

Browser-driven tests against the real FastAPI + MySQL backend.

## Layout

```
e2e/
  playwright.config.ts                       # two projects: `chromium` + `demo`
  tsconfig.json                              # extends ../tsconfig.json
  README.md
  fixtures/
    auth.ts                                  # MANAGER_/HOLDER_CREDENTIALS + loginAs*() helpers
    test-images/
      sample.png                             # 1×1 PNG for repair-request upload spec
  pages/
    LoginPage.ts                             # /auth/login
    RegisterPage.ts                          # /auth/register
    MainShellPage.ts                         # sidebar / theme / language / logout
    SubmitRepairPage.ts                      # /repairs/new
    AssetListPage.ts                         # /assets (search + filter + register modal)
    AssetDetailPage.ts                       # /assets/:id (edit / assign / unassign / dispose modals)
    ReviewsPage.ts                           # /reviews
    ReviewDetailPage.ts                      # /reviews/:id (approve / reject / update-details / complete modals)
  tests/
    auth.spec.ts
    auth-register.spec.ts
    rbac.spec.ts
    holder-submit-repair.spec.ts
    holder-views.spec.ts
    manager-approve.spec.ts
    manager-reject.spec.ts
    manager-complete.spec.ts
    manager-update-repair-details.spec.ts
    manager-register-asset.spec.ts
    manager-asset-edit.spec.ts
    manager-asset-assign.spec.ts
    manager-asset-dispose.spec.ts
    asset-search.spec.ts
    manager-dashboard.spec.ts
    shell.spec.ts
    demo/
      holder-journey.spec.ts                 # narrative for live presentation
      manager-journey.spec.ts                # narrative for live presentation
```

## Regression suite — what each spec covers

25 tests across 16 spec files. Default `npm run test:e2e` runs all of them.

| Spec | Tests | What it covers |
|---|---|---|
| `auth.spec.ts` | 3 | Manager logs in and lands on dashboard; wrong password shows error; unknown email returns the same error as wrong password (anti-enumeration guard) |
| `auth-register.spec.ts` | 1 | New holder registers via `/auth/register`, auto-logs in, lands on `/my-assets` |
| `rbac.spec.ts` | 3 | Holder hitting `/dashboard`, `/reviews`, `/assets` is bounced to `/forbidden` by `ProtectedRoute` |
| `holder-submit-repair.spec.ts` | 1 | Holder picks an in_use asset, fills fault description, attaches a PNG, submits — new request appears as Pending Review |
| `holder-views.spec.ts` | 3 | Render checks on `/my-assets`, `/repairs` list, and a `/repairs/:id` detail page |
| `manager-approve.spec.ts` | 1 | Manager approves a `pending_review` repair with a repair plan → status flips to Under Repair, Complete button appears |
| `manager-reject.spec.ts` | 1 | Manager rejects a `pending_review` with a reason → status flips to Rejected, Approve button gone |
| `manager-complete.spec.ts` | 1 | Manager completes an `under_repair` request with vendor + cost → status flips to Completed, Complete button gone |
| `manager-update-repair-details.spec.ts` | 1 | Manager edits a repair plan on an `under_repair` request — metadata-only change, status stays Under Repair |
| `manager-register-asset.spec.ts` | 1 | Manager opens the register-asset modal, fills it, saves, and verifies the row appears in the list via search |
| `manager-asset-edit.spec.ts` | 1 | Manager edits the name of `AST-2026-00050` (any FSM state — edit is always allowed) |
| `manager-asset-assign.spec.ts` | 1 | Manager assigns `AST-2026-00007` to a holder (in_stock → in_use) then unassigns it (back to in_stock) |
| `manager-asset-dispose.spec.ts` | 1 | Manager disposes `AST-2026-00013` (in_stock → disposed); Assign/Dispose buttons collapse afterwards |
| `asset-search.spec.ts` | 2 | Free-text search narrows the list to rows containing the query; status filter shows only In Use rows |
| `manager-dashboard.spec.ts` | 1 | Render check on `/dashboard` for the bootstrap manager |
| `shell.spec.ts` | 3 | Logout returns to `/auth/login`; language switcher rewrites nav into zh-TW; dark-mode toggle flips the theme button's aria-label |


## Demo flows — what each `test.step()` does

Two narrative specs in `tests/demo/`, run by `npm run test:e2e:demo`
(headed + 500 ms slowMo so the audience can follow each action).

### `demo/holder-journey.spec.ts`

A holder finds a broken laptop, files a repair, and watches it land in their
queue. Six `test.step()` checkpoints:

1. Sign in as the seeded holder
2. Review the assets assigned to me
3. Navigate to the repair-request submission form
4. Fill in the fault report and attach a photo
5. Confirm the new request appears as Pending Review
6. Re-confirm credentials are stored and the holder is identified

### `demo/manager-journey.spec.ts`

A manager registers newly procured hardware, then drives a repair from
queue to closed. Seven `test.step()` checkpoints:

1. Sign in as the bootstrap manager
2. Open the asset inventory and explore search
3. Register a newly procured laptop
4. Find the brand-new asset in the inventory
5. Pivot to the repair-review queue
6. Approve the top Pending Review with a repair plan
7. Vendor returns the unit — record completion

If you run the holder demo first, the Pending Review it leaves behind is
the same one the manager demo picks up — the two compose into one story.

## Run the regression suite

```bash
# Headless run — 25 tests, ~25s
cd frontend && npm run test:e2e

# Headed (watch a real browser window)
cd frontend && npm run test:e2e:headed

# Interactive UI for debugging a single spec
cd frontend && npm run test:e2e:ui

# Only one spec file
cd frontend && npm run test:e2e -- tests/auth.spec.ts

# Open the HTML report after a failed run
cd frontend && npx playwright show-report e2e/playwright-report
```

Re-seed the backend between full runs.

```bash
docker compose run --rm -e AMS_SEED_CONFIRM=1 backend python scripts/seed_demo_data.py
```

## Run the demo flows

```bash
# Both demos back-to-back (holder first, then manager)
cd frontend && npm run test:e2e:demo

# Holder only
cd frontend && npm run test:e2e:demo -- tests/demo/holder-journey.spec.ts

# Manager only
cd frontend && npm run test:e2e:demo -- tests/demo/manager-journey.spec.ts

# Slower playback for the actual presentation (1 s per action)
cd frontend && E2E_SLOW_MO=1000 npm run test:e2e:demo -- tests/demo/holder-journey.spec.ts
cd frontend && E2E_SLOW_MO=1000 npm run test:e2e:demo -- tests/demo/manager-journey.spec.ts
```
