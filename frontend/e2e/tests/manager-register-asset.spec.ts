import { expect, test, loginAsManager } from "../fixtures/auth";
import { AssetListPage } from "../pages/AssetListPage";

test.describe("Manager registers a new asset", () => {
  test("creates an asset and sees it appear in the list", async ({ page }) => {
    // Arrange — login + navigate. Use a timestamp-suffixed name so the new
    // row is unambiguously identifiable in the table afterwards.
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();

    const uniqueName = `E2E ThinkPad ${Date.now()}`;

    // Act — open the modal, fill the required fields, save.
    await assetListPage.openRegisterModal();
    await assetListPage.fillAndSubmitRegisterForm({
      name: uniqueName,
      model: "X1 Carbon Gen 11",
      category: "computer",
      supplier: "Lenovo",
      purchaseDate: "2025-01-15",
      purchaseAmount: "45000",
    });

    // Assert — success notification surfaces, modal closes, and the new
    // asset is searchable in the list.
    await expect(page.getByText("Asset registered successfully")).toBeVisible();
    await assetListPage.searchFor(uniqueName);
    await expect(assetListPage.assetRows).toHaveCount(1);
    await expect(assetListPage.assetRows.first()).toContainText(uniqueName);
  });
});
