import { expect, test, loginAsManager } from "../fixtures/auth";
import { AssetListPage } from "../pages/AssetListPage";
import { AssetDetailPage } from "../pages/AssetDetailPage";

test.describe("Manager disposes an asset", () => {
  test("transitions an in_stock asset into disposed", async ({ page }) => {
    // Arrange — Dispose is only allowed from in_stock with no holder per
    // the FSM (`docs/system-design/11-asset-fsm.md`). Filter accordingly.
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();
    await assetListPage.filterByStatus("In Stock");
    // Pick an in_stock row dynamically so the test still passes if seeded
    // codes/states change between runs.
    await expect(assetListPage.assetRows.first()).toBeVisible();
    await assetListPage.openAssetDetailAt(0);

    // Act
    const assetDetailPage = new AssetDetailPage(page);
    await expect(assetDetailPage.disposeButton).toBeVisible({ timeout: 10_000 });
    await assetDetailPage.openDisposeModal();
    await assetDetailPage.submitDisposeForm({
      disposalReason: "E2E: end-of-life device, recycled via vendor.",
    });
    await page.reload();

    // Assert — status reaches the terminal Disposed state. The FSM-gated
    // buttons (Assign / Dispose) collapse off the action panel, while Edit
    // intentionally stays visible because metadata edits are allowed on any
    // status (see `frontend/src/pages/AssetDetail/index.tsx`).
    await expect(page.getByText("Disposed").first()).toBeVisible({ timeout: 10_000 });
    await expect(assetDetailPage.assignButton).toBeHidden();
    await expect(assetDetailPage.disposeButton).toBeHidden();
  });
});
