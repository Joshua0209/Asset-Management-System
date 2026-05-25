import { expect, test } from "../fixtures/auth";
import { RegisterPage } from "../pages/RegisterPage";

test.describe("Holder registration", () => {
  test("creates a new holder account and auto-logs in", async ({ page }) => {
    // Arrange — registration uniqueness is on email, so suffix with a
    // timestamp to keep the test idempotent across re-runs without re-seeding.
    const uniqueEmail = `e2e-holder-${Date.now()}@example.com`;
    const registerPage = new RegisterPage(page);
    await registerPage.goto();

    // Act
    await registerPage.register({
      name: "E2E Holder",
      department: "QA Automation",
      email: uniqueEmail,
      password: "Password123",
    });

    // Assert — the Register page calls authApi.register followed by login,
    // then navigates to "/", which RoleLandingRedirect resolves to
    // /my-assets for the freshly-created holder.
    await expect(page).toHaveURL(/\/my-assets$/);
    await expect(page.getByText("E2E Holder")).toBeVisible();
  });
});
