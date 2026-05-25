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
  readonly statusFilter: Locator;
  readonly resetFiltersButton: Locator;
  readonly registerButton: Locator;
  readonly assetRows: Locator;
  readonly registerModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.searchInput = page.getByPlaceholder("Search by asset code, name, or model");
    this.statusFilter = page.getByPlaceholder("Filter by status");
    this.resetFiltersButton = page.getByRole("button", { name: "Reset Filters" });
    this.registerButton = page.getByRole("button", { name: "Register Asset" });
    this.assetRows = page.locator(".ant-table-tbody > tr.ant-table-row");
    this.registerModal = page.getByRole("dialog", { name: "Register New Asset" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/assets");
  }

  async searchFor(text: string): Promise<void> {
    await this.searchInput.fill(text);
    // The filter is debounced; wait for the table loading spinner to clear.
    await this.page.locator(".ant-spin-spinning").waitFor({ state: "hidden" });
  }

  async filterByStatus(label: string): Promise<void> {
    await this.statusFilter.click();
    await this.page.getByRole("option", { name: label, exact: true }).click();
    await this.page.locator(".ant-spin-spinning").waitFor({ state: "hidden" });
  }

  async resetFilters(): Promise<void> {
    await this.resetFiltersButton.click();
    await this.page.locator(".ant-spin-spinning").waitFor({ state: "hidden" });
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
}
