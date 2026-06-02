import { expect, test, loginAsManager } from "../fixtures/auth";
import { AssetListPage } from "../pages/AssetListPage";
import { AssetDetailPage } from "../pages/AssetDetailPage";

test.describe("Manager edits an existing asset", () => {
  test("updates the asset name and sees the change persist", async ({ page }) => {
    // Arrange — target a specific seeded asset by code so this spec doesn't
    // race the parallel manager-asset-assign / manager-asset-dispose / register
    // specs for the same row. AST-2026-00050 is created by `build_assets`
    // in the seed (index 49, in_use, holder assigned).
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();
    await assetListPage.openAssetDetailByCode("AST-2026-00050");

    // Use a timestamped suffix so the assertion is unique to this run and
    // doesn't depend on prior seed state.
    const newName = `E2E Edited ${Date.now()}`;

    // Act
    const assetDetailPage = new AssetDetailPage(page);
    await assetDetailPage.openEditModal();
    await assetDetailPage.submitEditName(newName);

    // Assert — toast first (catches a silently-dropped api.success), then
    // the modal closes (Edit button reappears) and the new name is rendered
    // in the descriptions panel on the detail page.
    await expect(page.getByText("Asset updated successfully")).toBeVisible();
    await expect(assetDetailPage.editButton).toBeVisible();
    await expect(page.getByText(newName)).toBeVisible();
  });
});
