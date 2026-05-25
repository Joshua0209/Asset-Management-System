import type { Locator, Page } from "@playwright/test";

// Page Object for `/auth/login`. Hides selector wiring so specs read as user
// intent ("login as X"), and selector churn from Ant Design upgrades stays
// confined to this file.
export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorAlert: Locator;

  constructor(page: Page) {
    this.page = page;
    // Locale is locked to en-US in playwright.config.ts, so English labels
    // are reliable here. If we add a zh-TW project, switch to data-testid.
    this.emailInput = page.getByLabel("Email");
    this.passwordInput = page.getByLabel("Password");
    this.submitButton = page.getByRole("button", { name: "Sign in" });
    this.errorAlert = page.getByRole("alert");
  }

  async goto(): Promise<void> {
    await this.page.goto("/auth/login");
  }

  async login(email: string, password: string): Promise<void> {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
  }
}
