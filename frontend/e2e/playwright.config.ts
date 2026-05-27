import { defineConfig } from "@playwright/test";

// Browser-facing UI lives at this port (matches `frontend/vite.config.ts`).
const FRONTEND_BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

// Backend is NOT auto-started — E2E hits the real FastAPI + MySQL stack so the
// suite catches contract drift the unit tests (which mock `@/api`) cannot.
// See `e2e/README.md` for how to bring the backend up via docker compose.
const isCI = Boolean(process.env.CI);

// Per-action delay (ms) for headed debugging. CI stays at 0 so timing-sensitive
// flows don't slow down. Override locally with `E2E_SLOW_MO=500 npm run test:e2e:headed`.
const slowMoMs = Number(process.env.E2E_SLOW_MO ?? 0);

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  // Serialize on CI so concurrent specs don't race the single backend DB.
  workers: isCI ? 1 : undefined,
  reporter: isCI
    ? [["list"], ["html", { open: "never" }], ["github"]]
    : [["list"], ["html", { open: "never" }]],
  outputDir: "test-results",

  use: {
    baseURL: FRONTEND_BASE_URL,
    // Lock locale + timezone so i18n-sensitive assertions are stable across machines.
    locale: "en-US",
    timezoneId: "Asia/Taipei",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // `viewport: null` + `--start-maximized` makes the browser window open
    // full-screen in headed/demo runs. Headless ignores window args and falls
    // back to a default size, so this is safe for CI too.
    viewport: null,
    launchOptions: { slowMo: slowMoMs, args: ["--start-maximized"] },
  },

  projects: [
    // Default project — runs the regression suite. Demo specs live in
    // `tests/demo/` and are excluded here so `npm run test:e2e` stays focused
    // on coverage, not narrative. We deliberately don't use the
    // `devices["Desktop Chrome"]` preset because its baked-in
    // `deviceScaleFactor: 1` conflicts with the `viewport: null` we set at
    // the top-level `use` block.
    {
      name: "chromium",
      testIgnore: ["**/demo/**"],
    },
    // Demo project — slow-mo'd narrative flows for the live presentation.
    // Invoke with `npm run test:e2e:demo`; defaults to headed + slowMo so the
    // audience can follow along.
    {
      name: "demo",
      testMatch: ["**/demo/**"],
      workers: 1,
      // Each demo is one continuous test with ~8 narrative steps. At
      // slowMo:500ms the wall time easily exceeds Playwright's 30s default,
      // so give each flow 3 minutes of headroom.
      timeout: 180_000,
      use: {
        // Per-action delay matched to a comfortable reading pace; override via
        // `E2E_SLOW_MO` (see top of file) for finer control.
        launchOptions: { slowMo: slowMoMs || 500, args: ["--start-maximized"] },
      },
    },
  ],

  webServer: {
    command: "npm run dev",
    cwd: "..",
    url: FRONTEND_BASE_URL,
    reuseExistingServer: !isCI,
    timeout: 120_000,
  },
});
