import type { Locator, Page } from "@playwright/test";

export interface ApproveFormInput {
  repairPlan: string;
  repairVendor: string;
  repairCost: string;
  plannedDate: string;
}

export interface CompleteFormInput {
  repairDate: string;
  faultContent: string;
  repairPlan: string;
  repairCost: string;
  repairVendor: string;
}

// Page Object for the manager-side `/reviews/:id` detail page. Covers the
// approve and complete modals (the two transitions exercised by the W6
// critical flows).
export class ReviewDetailPage {
  readonly page: Page;
  readonly approveButton: Locator;
  readonly completeButton: Locator;
  readonly approveModal: Locator;
  readonly completeModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.approveButton = page.getByRole("button", { name: "Approve", exact: true });
    this.completeButton = page.getByRole("button", { name: "Complete", exact: true });
    this.approveModal = page.getByRole("dialog", { name: "Approve Repair Request" });
    this.completeModal = page.getByRole("dialog", { name: "Complete Repair" });
  }

  async openApproveModal(): Promise<void> {
    await this.approveButton.click();
    await this.approveModal.waitFor({ state: "visible" });
  }

  async submitApproveForm(values: ApproveFormInput): Promise<void> {
    const modal = this.approveModal;
    await modal.getByLabel("Repair Plan").fill(values.repairPlan);
    await modal.getByLabel("Repair Vendor").fill(values.repairVendor);
    await modal.getByLabel("Repair Cost").fill(values.repairCost);
    await modal.getByLabel("Planned Date").fill(values.plannedDate);
    // The modal's primary action uses the same label as the row button, so
    // scope to the dialog to avoid the outer (now hidden) trigger.
    await modal.getByRole("button", { name: "Approve", exact: true }).click();
  }

  async openCompleteModal(): Promise<void> {
    await this.completeButton.click();
    await this.completeModal.waitFor({ state: "visible" });
  }

  async submitCompleteForm(values: CompleteFormInput): Promise<void> {
    const modal = this.completeModal;
    await modal.getByLabel("Repair Date").fill(values.repairDate);
    await modal.getByLabel("Fault Description").fill(values.faultContent);
    await modal.getByLabel("Repair Plan").fill(values.repairPlan);
    await modal.getByLabel("Repair Cost").fill(values.repairCost);
    await modal.getByLabel("Repair Vendor").fill(values.repairVendor);
    await modal.getByRole("button", { name: "Complete", exact: true }).click();
  }
}
