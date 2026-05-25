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
    // Target a specific seeded in_stock asset by code so this spec doesn't
    // race other parallel asset modal specs. AST-2026-00013 is created by
    // `build_assets` (index 12, % 3 == 0 → no holder → in_stock, eligible
    // for dispose per the FSM).
    await assetListPage.openAssetDetailByCode("AST-2026-00013");

    // Act
    const assetDetailPage = new AssetDetailPage(page);
    await assetDetailPage.openDisposeModal();
    await assetDetailPage.submitDisposeForm({
      disposalReason: "E2E: end-of-life device, recycled via vendor.",
    });

    // Assert — status reaches the terminal Disposed state. The FSM-gated
    // buttons (Assign / Dispose) collapse off the action panel, while Edit
    // intentionally stays visible because metadata edits are allowed on any
    // status (see `frontend/src/pages/AssetDetail/index.tsx`).
    await expect(page.getByText("Disposed").first()).toBeVisible();
    await expect(assetDetailPage.assignButton).toBeHidden();
    await expect(assetDetailPage.disposeButton).toBeHidden();
  });
});
