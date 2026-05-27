import { test as base, type Page } from "@playwright/test";
import { LoginPage } from "../pages/LoginPage";

// Credentials are sourced from env vars so CI can inject test-only accounts
// without committing secrets. Defaults match the bootstrap manager and the
// first seeded holder from `backend/scripts/seed_demo_data.py` (see
// `BOOTSTRAP_MANAGER_*` in `backend/.env.example` and `HOLDER_NAMES` in the
// seed script).
export const MANAGER_CREDENTIALS = {
  email: process.env.E2E_MANAGER_EMAIL ?? "admin@example.com",
  password: process.env.E2E_MANAGER_PASSWORD ?? "ChangeMe123",
} as const;

export const HOLDER_CREDENTIALS = {
  email: process.env.E2E_HOLDER_EMAIL ?? "holder1@example.com",
  password: process.env.E2E_HOLDER_PASSWORD ?? "Password123",
} as const;

interface AuthFixtures {
  loginPage: LoginPage;
}

export const test = base.extend<AuthFixtures>({
  loginPage: async ({ page }, use) => {
    await use(new LoginPage(page));
  },
});

export { expect } from "@playwright/test";

// Helpers for tests that need to start in an authenticated state. Not fixtures
// because they depend on the test's own `page`, not on worker-scoped setup.
export async function loginAsManager(page: Page): Promise<void> {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login(MANAGER_CREDENTIALS.email, MANAGER_CREDENTIALS.password);
  await page.waitForURL("**/dashboard");
}

export async function loginAsHolder(page: Page): Promise<void> {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.login(HOLDER_CREDENTIALS.email, HOLDER_CREDENTIALS.password);
  await page.waitForURL("**/my-assets");
}
