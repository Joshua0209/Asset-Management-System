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

export interface RejectFormInput {
  rejectionReason: string;
}

export interface UpdateDetailsFormInput {
  repairDate?: string;
  faultContent?: string;
  repairPlan?: string;
  repairCost?: string;
  repairVendor?: string;
}

// Page Object for the manager-side `/reviews/:id` detail page. Covers all
// four FSM transitions (approve, reject, update-details, complete) the
// manager can drive from this screen.
export class ReviewDetailPage {
  readonly page: Page;
  readonly approveButton: Locator;
  readonly rejectButton: Locator;
  readonly updateDetailsButton: Locator;
  readonly completeButton: Locator;
  readonly approveModal: Locator;
  readonly rejectModal: Locator;
  readonly updateDetailsModal: Locator;
  readonly completeModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.approveButton = page.getByRole("button", { name: "Approve", exact: true });
    this.rejectButton = page.getByRole("button", { name: "Reject", exact: true });
    this.updateDetailsButton = page.getByRole("button", { name: "Update Details" });
    this.completeButton = page.getByRole("button", { name: "Complete", exact: true });
    this.approveModal = page.getByRole("dialog", { name: "Approve Repair Request" });
    this.rejectModal = page.getByRole("dialog", { name: "Reject Repair Request" });
    this.updateDetailsModal = page.getByRole("dialog", { name: "Update Repair Details" });
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

  async openRejectModal(): Promise<void> {
    await this.rejectButton.click();
    await this.rejectModal.waitFor({ state: "visible" });
  }

  async submitRejectForm(values: RejectFormInput): Promise<void> {
    const modal = this.rejectModal;
    await modal.getByLabel("Rejection Reason").fill(values.rejectionReason);
    await modal.getByRole("button", { name: "Reject", exact: true }).click();
  }

  async openUpdateDetailsModal(): Promise<void> {
    await this.updateDetailsButton.click();
    await this.updateDetailsModal.waitFor({ state: "visible" });
  }

  async submitUpdateDetailsForm(values: UpdateDetailsFormInput): Promise<void> {
    const modal = this.updateDetailsModal;
    if (values.repairDate !== undefined) {
      await modal.getByLabel("Repair Date").fill(values.repairDate);
    }
    if (values.faultContent !== undefined) {
      await modal.getByLabel("Fault Description").fill(values.faultContent);
    }
    if (values.repairPlan !== undefined) {
      await modal.getByLabel("Repair Plan").fill(values.repairPlan);
    }
    if (values.repairCost !== undefined) {
      await modal.getByLabel("Repair Cost").fill(values.repairCost);
    }
    if (values.repairVendor !== undefined) {
      await modal.getByLabel("Repair Vendor").fill(values.repairVendor);
    }
    await modal.getByRole("button", { name: "Save" }).click();
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
