import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Locator, Page } from "@playwright/test";

// Resolve the fixture path relative to this file so the test works no matter
// where Playwright is invoked from.
const FIXTURE_DIR = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE_IMAGE_PATH = path.resolve(
  FIXTURE_DIR,
  "..",
  "fixtures",
  "test-images",
  "sample.png",
);

// Page Object for `/repairs/new` (holder route).
export class SubmitRepairPage {
  readonly page: Page;
  readonly assetSelect: Locator;
  readonly faultDescriptionInput: Locator;
  readonly fileInput: Locator;
  readonly submitButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.assetSelect = page.getByLabel("Asset ID");
    this.faultDescriptionInput = page.getByLabel("Fault Description");
    // Ant Design Upload renders a hidden <input type="file">. Match it
    // explicitly so we can drive setInputFiles without clicking the visible
    // upload button (which would open the native OS picker).
    this.fileInput = page.locator('input[type="file"]');
    this.submitButton = page.getByRole("button", { name: "Submit Request" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/repairs/new");
  }

  async selectFirstAvailableAsset(): Promise<void> {
    await this.assetSelect.click();
    // Ant Design Select renders its dropdown options in a portal. Wait for
    // the listbox to appear, then pick the first non-loading option.
    const firstOption = this.page.locator(".ant-select-item-option").first();
    await firstOption.waitFor({ state: "visible" });
    await firstOption.click();
  }

  async fillFaultDescription(text: string): Promise<void> {
    await this.faultDescriptionInput.fill(text);
  }

  async attachSampleImage(): Promise<void> {
    await this.fileInput.setInputFiles(SAMPLE_IMAGE_PATH);
  }

  async submit(): Promise<void> {
    await this.submitButton.click();
  }
}
