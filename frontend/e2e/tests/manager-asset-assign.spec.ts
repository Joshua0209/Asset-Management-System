import { expect, test, loginAsManager, HOLDER_CREDENTIALS } from "../fixtures/auth";
import { AssetListPage } from "../pages/AssetListPage";
import { AssetDetailPage } from "../pages/AssetDetailPage";

test.describe("Manager assigns and unassigns an asset", () => {
  test("assigns an in_stock asset to a holder, then unassigns it", async ({ page }) => {
    // Arrange — target a specific seeded in_stock asset by code so this
    // spec doesn't race other parallel asset modal specs. AST-2026-00007
    // is created by `build_assets` (index 6, % 3 == 0 → no holder → in_stock).
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();
    await assetListPage.openAssetDetailByCode("AST-2026-00007");

    const assetDetailPage = new AssetDetailPage(page);

    // Act — assign the asset to the seeded holder. The holder query matches
    // the e-mail substring rendered in the dropdown's "<name> (<email>)" label.
    await assetDetailPage.openAssignModal();
    await assetDetailPage.submitAssignForm({
      holderQuery: HOLDER_CREDENTIALS.email,
      assignmentDate: "2026-05-25",
    });

    // Assert — status flips to In Use; the Unassign button now replaces
    // Assign in the action panel (FSM-driven).
    await expect(page.getByText("In Use").first()).toBeVisible();
    await expect(
      page.getByRole("row", { name: "Department 製造一部 Location 新竹 Fab12 行政樓" }),
    ).toBeVisible();
    await expect(assetDetailPage.unassignButton).toBeVisible();
    await expect(assetDetailPage.assignButton).toBeHidden();

    // Act 2 — immediately unassign to leave the seed in a recoverable state
    // and exercise the reverse transition in the same test.
    await assetDetailPage.openUnassignModal();
    await assetDetailPage.submitUnassignForm({
      reason: "E2E: cleanup after assign round-trip.",
      unassignmentDate: "2026-05-25",
    });

    // Assert 2 — back to In Stock; Assign button is back, Unassign gone.
    await expect(page.getByText("In Stock").first()).toBeVisible();
    await expect(
      page.getByRole("row", { name: "Department 資產管理部 Location 台北南港總部 8F" }),
    ).toBeVisible();
    await expect(assetDetailPage.assignButton).toBeVisible();
    await expect(assetDetailPage.unassignButton).toBeHidden();
  });
});
