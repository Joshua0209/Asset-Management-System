import type { Locator, Page } from "@playwright/test";

export interface AssignFormInput {
  // Substring of the holder's display label (e.g. their name). The dropdown
  // shows "<name> (<email>)" — any substring uniquely identifying the row
  // works.
  holderQuery: string;
  assignmentDate: string;
}

export interface UnassignFormInput {
  reason: string;
  unassignmentDate: string;
}

export interface DisposeFormInput {
  disposalReason: string;
}

// Page Object for `/assets/:id` — the manager's asset detail page hosts four
// modals (edit, assign, unassign, dispose). Which action buttons appear depends
// on the asset's FSM state, so the helpers here only assume the corresponding
// button is visible at the time they're called.
export class AssetDetailPage {
  readonly page: Page;
  readonly editButton: Locator;
  readonly assignButton: Locator;
  readonly unassignButton: Locator;
  readonly disposeButton: Locator;
  // Edit modal title uses an interpolated asset code; match on the prefix.
  readonly editModal: Locator;
  readonly assignModal: Locator;
  readonly unassignModal: Locator;
  readonly disposeModal: Locator;

  constructor(page: Page) {
    this.page = page;
    this.editButton = page.getByRole("button", { name: "Edit", exact: true });
    this.assignButton = page.getByRole("button", { name: "Assign", exact: true });
    this.unassignButton = page.getByRole("button", { name: "Unassign", exact: true });
    this.disposeButton = page.getByRole("button", { name: "Dispose", exact: true });
    this.editModal = page.getByRole("dialog", { name: /^Edit Asset - / });
    this.assignModal = page.getByRole("dialog", { name: /^Assign Asset - / });
    this.unassignModal = page.getByRole("dialog", { name: /^Unassign Asset - / });
    this.disposeModal = page.getByRole("dialog", { name: /^Dispose Asset - / });
  }

  async openEditModal(): Promise<void> {
    await this.editButton.click();
    await this.editModal.waitFor({ state: "visible" });
  }

  async submitEditName(newName: string): Promise<void> {
    const modal = this.editModal;
    await modal.getByLabel("Name").fill(newName);
    await modal.getByRole("button", { name: "Save" }).click();
  }

  async openAssignModal(): Promise<void> {
    await this.assignButton.click();
    await this.assignModal.waitFor({ state: "visible" });
  }

  async submitAssignForm(values: AssignFormInput): Promise<void> {
    const modal = this.assignModal;
    await modal.getByLabel("Holder").click();
    await this.page
      .locator(".ant-select-dropdown:visible .ant-select-item-option")
      .filter({ hasText: values.holderQuery })
      .first()
      .click();
    await modal.getByLabel("Assignment Date").fill(values.assignmentDate);
    await modal.getByRole("button", { name: "Confirm" }).click();
  }

  async openUnassignModal(): Promise<void> {
    await this.unassignButton.click();
    await this.unassignModal.waitFor({ state: "visible" });
  }

  async submitUnassignForm(values: UnassignFormInput): Promise<void> {
    const modal = this.unassignModal;
    await modal.getByLabel("Unassign Reason").fill(values.reason);
    await modal.getByLabel("Unassignment Date").fill(values.unassignmentDate);
    await modal.getByRole("button", { name: "Confirm" }).click();
  }

  async openDisposeModal(): Promise<void> {
    await this.disposeButton.click();
    await this.disposeModal.waitFor({ state: "visible" });
  }

  async submitDisposeForm(values: DisposeFormInput): Promise<void> {
    const modal = this.disposeModal;
    await modal.getByLabel("Disposal Reason").fill(values.disposalReason);
    await modal.getByRole("button", { name: "Confirm" }).click();
  }
}
