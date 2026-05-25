import { expect, test, loginAsHolder } from "../fixtures/auth";

// `ProtectedRoute` rejects role-mismatched access by redirecting to
// `/forbidden`. The Forbidden page renders the i18n key `errors.forbiddenTitle`
// ("Access denied"). Test each manager-only route from the holder side.
const MANAGER_ONLY_ROUTES = ["/dashboard", "/reviews", "/assets"] as const;

test.describe("RBAC — holder cannot reach manager routes", () => {
  for (const route of MANAGER_ONLY_ROUTES) {
    test(`bounces ${route} to /forbidden`, async ({ page }) => {
      await loginAsHolder(page);

      await page.goto(route);

      await expect(page).toHaveURL(/\/forbidden$/);
      await expect(page.getByText("Access denied")).toBeVisible();
    });
  }
});
