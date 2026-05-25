import type { Locator, Page } from "@playwright/test";

export interface AssetFormInput {
  name: string;
  model: string;
  category: "computer" | "phone" | "tablet" | "monitor" | "other";
  supplier: string;
  purchaseDate: string;
  purchaseAmount: string;
}

// Page Object for the manager-side `/assets` route. Covers the filter bar,
// asset table, and the "Register Asset" modal (the AssetFormFields component).
export class AssetListPage {
  readonly page: Page;
  readonly searchInput: Locator;
  // Ant Design Select renders its placeholder inside a wrapper div, NOT on a
  // real <input placeholder=...>; `getByPlaceholder` finds the hidden combobox
  // input but clicking it doesn't open the dropdown. Target the `.ant-select`
  // wrapper that has the placeholder text instead.
  readonly statusFilter: Locator;
  readonly resetFiltersButton: Locator;
  readonly registerButton: Locator;
  readonly assetRows: Locator;
  readonly registerModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.getByPlaceholder("Search by asset code, name, or model");
    this.statusFilter = page
      .locator(".ant-select")
      .filter({ hasText: "Filter by status" });
    this.resetFiltersButton = page.getByRole("button", { name: "Reset Filters" });
    this.registerButton = page.getByRole("button", { name: "Register Asset" });
    this.assetRows = page.locator(".ant-table-tbody > tr.ant-table-row");
    this.registerModal = page.getByRole("dialog", { name: "Register New Asset" });
  }

  async goto(): Promise<void> {
    // Pin the wait to the initial list fetch so the baseline row count is
    // stable before tests interact with the table.
    const initialFetch = this.waitForAssetsResponse();
    await this.page.goto("/assets");
    await initialFetch;
  }

  // Wait for the next GET /api/v1/assets response. The search input is
  // debounced and the spinner is too short-lived to be a reliable signal —
  // pinning the wait to the actual network round-trip removes the race.
  private waitForAssetsResponse(): Promise<unknown> {
    return this.page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/assets") &&
        response.request().method() === "GET" &&
        response.status() === 200,
      { timeout: 10_000 },
    );
  }

  async searchFor(text: string): Promise<void> {
    const next = this.waitForAssetsResponse();
    await this.searchInput.fill(text);
    await next;
  }

  async filterByStatus(label: string): Promise<void> {
    const next = this.waitForAssetsResponse();
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

  async resetFilters(): Promise<void> {
    const next = this.waitForAssetsResponse();
    await this.resetFiltersButton.click();
    await next;
  }

  async openRegisterModal(): Promise<void> {
    await this.registerButton.click();
    await this.registerModal.waitFor({ state: "visible" });
  }

  async fillAndSubmitRegisterForm(values: AssetFormInput): Promise<void> {
    const modal = this.registerModal;
    await modal.getByLabel("Name").fill(values.name);
    await modal.getByLabel("Model").fill(values.model);

    // Ant Design Select inside the modal — open it, then click the option.
    await modal.getByLabel("Category").click();
    await this.page
      .locator(".ant-select-dropdown:visible .ant-select-item-option")
      .filter({ hasText: values.category })
      .first()
      .click();

    await modal.getByLabel("Supplier").fill(values.supplier);
    await modal.getByLabel("Purchase Date").fill(values.purchaseDate);
    await modal.getByLabel("Purchase Amount").fill(values.purchaseAmount);

    await modal.getByRole("button", { name: "Save" }).click();
  }

  // Returns the trimmed text of the first row's "Name" cell. Useful when a
  // test wants to derive a search query from whatever data the backend has,
  // making the assertion seed-agnostic.
  async firstRowName(): Promise<string> {
    const nameCell = this.assetRows.first().locator("td").nth(1);
    return ((await nameCell.textContent()) ?? "").trim();
  }
}
