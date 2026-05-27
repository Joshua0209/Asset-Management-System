import { expect, test, MANAGER_CREDENTIALS } from "../fixtures/auth";

test.describe("Login page", () => {
  test("manager can log in and lands on the dashboard", async ({ page, loginPage }) => {
    // Arrange
    await loginPage.goto();

    // Act
    await loginPage.login(MANAGER_CREDENTIALS.email, MANAGER_CREDENTIALS.password);

    // Assert — RoleLandingRedirect bounces manager to /dashboard.
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test("wrong password shows a generic error", async ({ page, loginPage }) => {
    // Arrange
    await loginPage.goto();

    // Act
    await loginPage.login(MANAGER_CREDENTIALS.email, "WrongPassword99");

    // Assert — URL stays on the login page, an alert surfaces.
    await expect(loginPage.errorAlert).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/login$/);
  });

  test("unknown email returns the same error as a wrong password", async ({ loginPage }) => {
    // Anti-enumeration: the backend intentionally returns an identical 401 for
    // unknown-email and wrong-password (see CLAUDE.md → Auth conventions). The
    // UI should surface the same alert in both cases — this test guards that.
    await loginPage.goto();
    await loginPage.login("nobody-" + Date.now() + "@example.com", "WrongPassword99");

    await expect(loginPage.errorAlert).toBeVisible();
    const unknownEmailMessage = await loginPage.errorAlert.textContent();

    await loginPage.emailInput.fill(MANAGER_CREDENTIALS.email);
    await loginPage.passwordInput.fill("WrongPassword99");
    await loginPage.submitButton.click();

    await expect(loginPage.errorAlert).toBeVisible();
    const wrongPasswordMessage = await loginPage.errorAlert.textContent();

    expect(unknownEmailMessage).toBe(wrongPasswordMessage);
  });
});
