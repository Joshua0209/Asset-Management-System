import type { Locator, Page } from "@playwright/test";

// Page Object for `/auth/register`. POST /auth/register always creates a
// holder per the project's auth conventions (managers are only seeded via
// `BOOTSTRAP_MANAGER_*`).
export class RegisterPage {
  readonly page: Page;
  readonly nameInput: Locator;
  readonly departmentInput: Locator;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly errorAlert: Locator;

  constructor(page: Page) {
    this.page = page;
    this.nameInput = page.getByLabel("Name");
    this.departmentInput = page.getByLabel("Department");
    this.emailInput = page.getByLabel("Email");
    this.passwordInput = page.getByLabel("Password");
    this.submitButton = page.getByRole("button", { name: "Register" });
    this.errorAlert = page.getByRole("alert");
  }

  async goto(): Promise<void> {
    await this.page.goto("/auth/register");
  }

  async register(values: {
    name: string;
    department: string;
    email: string;
    password: string;
  }): Promise<void> {
    await this.nameInput.fill(values.name);
    await this.departmentInput.fill(values.department);
    await this.emailInput.fill(values.email);
    await this.passwordInput.fill(values.password);
    await this.submitButton.click();
  }
}
