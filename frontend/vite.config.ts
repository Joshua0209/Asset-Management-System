import path from "node:path";
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
    // Cap fork concurrency so heavy jsdom + React + Ant Design renders
    // do not thrash the CPU and time out `waitFor` polls. Vitest defaults
    // to availableParallelism()-1 (≈9 on a 10-core Mac), and that's
    // exactly the load that produced flaky "Test timed out in 15000ms"
    // failures on pre-push. Four forks keeps wall-clock fast while
    // leaving headroom for the runner + system processes. Each fork
    // still has its own JSDOM, so test isolation is unchanged (single
    // fork would leak globals between tests).
    pool: "forks",
    poolOptions: {
      forks: {
        maxForks: 4,
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
