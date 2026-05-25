import { expect, test, loginAsManager } from "../fixtures/auth";
import { MainShellPage } from "../pages/MainShellPage";

test.describe("Application shell", () => {
  test("user can log out from the header dropdown", async ({ page }) => {
    await loginAsManager(page);
    const shell = new MainShellPage(page);

    await shell.logout();

    // Assert — back on the public login page; the protected sidebar nav
    // disappears once the session is cleared.
    await expect(page).toHaveURL(/\/auth\/login$/);
    await expect(shell.sideNav).toBeHidden();
  });

  test("language switcher swaps the nav labels into Traditional Chinese", async ({ page }) => {
    await loginAsManager(page);
    const shell = new MainShellPage(page);

    // Sanity check — locale lock means we start in English.
    await expect(shell.sideNav.getByText("Dashboard")).toBeVisible();

    await shell.switchLanguage("中");

    // The English label is gone and its zh-TW counterpart is rendered.
    await expect(shell.sideNav.getByText("Dashboard")).toBeHidden();
    await expect(shell.sideNav.getByText("儀表板")).toBeVisible();
  });

  test("dark mode toggle flips the theme button accessibility label", async ({ page }) => {
    await loginAsManager(page);
    const shell = new MainShellPage(page);

    // The button label encodes the action it *will* perform; before toggling
    // it advertises "switch to dark mode", after toggling it advertises
    // "switch to light mode".
    await expect(
      page.getByRole("button", { name: "switch to dark mode" }),
    ).toBeVisible();

    await shell.toggleTheme();

    await expect(
      page.getByRole("button", { name: "switch to light mode" }),
    ).toBeVisible();
  });
});
