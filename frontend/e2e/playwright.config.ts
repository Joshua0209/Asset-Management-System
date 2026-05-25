import { defineConfig, devices } from "@playwright/test";

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
    launchOptions: { slowMo: slowMoMs },
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
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
