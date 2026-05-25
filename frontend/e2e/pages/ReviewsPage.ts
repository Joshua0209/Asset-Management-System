import type { Locator, Page } from "@playwright/test";

export type ReviewStatusLabel =
  | "Pending Review"
  | "Under Repair"
  | "Completed"
  | "Rejected";

// Page Object for the manager-side `/reviews` list. Drills into the first
// matching row for a given status so the manager-approve / manager-complete
// specs can target requests in the right FSM state.
export class ReviewsPage {
  readonly page: Page;
  readonly statusFilter: Locator;
  readonly requestRows: Locator;

  constructor(page: Page) {
    this.page = page;
    this.statusFilter = page.getByPlaceholder("Filter by status");
    this.requestRows = page.locator(".ant-table-tbody > tr.ant-table-row");
  }

  async goto(): Promise<void> {
    await this.page.goto("/reviews");
  }

  async filterByStatus(label: ReviewStatusLabel): Promise<void> {
    await this.statusFilter.click();
    await this.page.getByRole("option", { name: label, exact: true }).click();
    await this.page.locator(".ant-spin-spinning").waitFor({ state: "hidden" });
  }

  async openFirstRequestDetail(): Promise<void> {
    const firstDetailLink = this.requestRows
      .first()
      .getByRole("button", { name: "Detail" });
    await firstDetailLink.click();
    await this.page.waitForURL(/\/reviews\/[0-9a-f-]+$/i);
  }
}
