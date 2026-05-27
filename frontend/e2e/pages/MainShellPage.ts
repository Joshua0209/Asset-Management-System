import type { Locator, Page } from "@playwright/test";

// Page Object for the persistent application chrome (`MainLayout`): sidebar
// nav, theme toggle, language switcher, and the user dropdown that hosts
// "Log out". Available on every authenticated route.
export class MainShellPage {
  readonly page: Page;
  readonly themeToggle: Locator;
  readonly languageSwitcher: Locator;
  // The user's name area in the header opens the dropdown menu on click.
  readonly userMenuTrigger: Locator;
  readonly sideNav: Locator;

  constructor(page: Page) {
    this.page = page;
    // The toggle's aria-label flips between light/dark mode messages; match
    // both so the locator works regardless of the current theme.
    this.themeToggle = page.getByRole("button", {
      name: /switch to (dark|light) mode/i,
    });
    this.languageSwitcher = page.getByRole("radiogroup", { name: "segmented control" });
    this.userMenuTrigger = page.getByText("Asset Manager").or(page.getByText("Asset Holder"));
    this.sideNav = page.getByRole("menu");
  }

  async toggleTheme(): Promise<void> {
    await this.themeToggle.click();
  }

  async switchLanguage(label: "中" | "EN"): Promise<void> {
    await this.languageSwitcher.getByText(label, { exact: true }).click();
  }

  async logout(): Promise<void> {
    await this.userMenuTrigger.click();
    // The dropdown menu is portaled to body; scope to the visible one.
    await this.page
      .locator(".ant-dropdown:visible")
      .getByRole("menuitem", { name: /log out|登出/i })
      .click();
    await this.page.waitForURL(/\/auth\/login$/);
  }
}
