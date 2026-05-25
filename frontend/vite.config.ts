import path from "node:path";
import { availableParallelism } from "node:os";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    testTimeout: 15000,
    // Keep vitest scoped to unit/integration tests under `src/`. The Playwright
    // E2E suite under `e2e/` also uses *.spec.ts and would otherwise be picked
    // up here, where its `test.describe` collides with vitest's API.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // Cap fork concurrency so heavy jsdom + React + Ant Design renders
    // do not thrash the CPU and time out `waitFor` polls. Vitest defaults
    // to availableParallelism()-1 (≈9 on a 10-core Mac), and that's
    // exactly the load that produced flaky "Test timed out in 15000ms"
    // failures on pre-push. Four forks keeps wall-clock fast while
    // leaving headroom for the runner + system processes. Each fork
    // still has its own JSDOM, so test isolation is unchanged (single
    // fork would leak globals between tests).
    //
    // Take the MIN of 4 and the runner's actual parallelism so that
    // 2-vCPU CI runners (GitHub Actions ubuntu-latest, ~2-4 vCPU) are
    // not oversubscribed with 4 forks fighting for 2 cores. On the dev
    // Mac (10 cores) the cap stays at 4.
    pool: "forks",
    poolOptions: {
      forks: {
        maxForks: Math.min(4, availableParallelism()),
        minForks: 1,
      },
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      reportsDirectory: "coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx",
        "src/**/*.test.{ts,tsx}",
        "src/**/*.spec.{ts,tsx}",
        "src/__tests__/**",
      ],
    },
  },
});
