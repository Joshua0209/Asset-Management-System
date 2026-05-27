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
    // See AssetListPage for why the `.ant-select` wrapper is targeted instead
    // of getByPlaceholder — Ant Design's Select component doesn't expose the
    // placeholder on a real <input>.
    this.statusFilter = page
      .locator(".ant-select")
      .filter({ hasText: "Filter by status" });
    this.requestRows = page.locator(".ant-table-tbody > tr.ant-table-row");
  }

  async goto(): Promise<void> {
    const initialFetch = this.waitForRepairRequestsResponse();
    await this.page.goto("/reviews");
    await initialFetch;
  }

  private waitForRepairRequestsResponse(): Promise<unknown> {
    return this.page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/repair-requests") &&
        response.request().method() === "GET" &&
        response.status() === 200,
      { timeout: 10_000 },
    );
  }

  async filterByStatus(label: ReviewStatusLabel): Promise<void> {
    const next = this.waitForRepairRequestsResponse();
    await this.statusFilter.click();
    // Ant Design portals the dropdown to <body>; scope to the visible
    // `.ant-select-dropdown` and click the `.ant-select-item-option` row.
    // getByRole("option") can pick the wrong child node and silently miss
    // the actual click target.
    await this.page
      .locator(".ant-select-dropdown:visible .ant-select-item-option")
      .filter({ hasText: label })
      .first()
      .click();
    await next;
  }

  async openFirstRequestDetail(): Promise<void> {
    const firstDetailLink = this.requestRows
      .first()
      .getByRole("button", { name: "Detail" });
    await firstDetailLink.click();
    await this.page.waitForURL(/\/reviews\/[0-9a-f-]+$/i);
  }
}
