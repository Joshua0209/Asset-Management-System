import { expect, test, loginAsManager } from "../../fixtures/auth";
import { AssetListPage } from "../../pages/AssetListPage";
import { ReviewsPage } from "../../pages/ReviewsPage";
import { ReviewDetailPage } from "../../pages/ReviewDetailPage";

// Demo: a manager runs the asset + repair lifecycle end to end.
//
// One continuous test with `test.step()` checkpoints. Designed to be paired
// with the holder demo: if you run holder-journey first, the Pending Review
// item the holder filed shows up at the top of this manager's review queue.
// The demo also works standalone — the seed leaves multiple Pending Review
// rows to draw from.
test.describe("Demo — Manager processes the asset and repair lifecycle", () => {
  test("registers an asset, then approves and completes a repair", async ({ page }) => {
    const demoAssetName = `Demo MacBook ${Date.now()}`;

    await test.step("Sign in as the bootstrap manager", async () => {
      await loginAsManager(page);
      await expect(page).toHaveURL(/\/dashboard$/);
      await expect(
        page.getByRole("heading", { name: "Dashboard", exact: true }),
      ).toBeVisible();
    });

    await test.step("Open the asset inventory and explore search", async () => {
      const assetsMenuItem = page.getByRole("menuitem", {
        name: /Asset Management|Assets|資產管理/i,
      });
      await expect(assetsMenuItem).toBeVisible({ timeout: 15_000 });
      await assetsMenuItem.click({ timeout: 15_000 });
      await expect(page).toHaveURL(/\/assets$/);
      await expect(
        page.getByRole("heading", { name: "Asset List" }),
      ).toBeVisible();

      // Show the search affordance — narrates "I can quickly find any asset
      // by code, name, or model". Reset after so the next step sees the
      // unfiltered list.
      const assetListPage = new AssetListPage(page);
      await assetListPage.searchFor("MacBook");
      await expect(assetListPage.assetRows.first()).toBeVisible();
      await assetListPage.resetFilters();
    });

    await test.step("Register a newly procured laptop", async () => {
      const assetListPage = new AssetListPage(page);
      await assetListPage.openRegisterModal();
      await assetListPage.fillAndSubmitRegisterForm({
        name: demoAssetName,
        model: "MacBook Pro 14 M3",
        category: "computer",
        supplier: "Apple",
        purchaseDate: "2026-05-01",
        purchaseAmount: "62000",
      });
      await expect(page.getByText("Asset registered successfully")).toBeVisible();
    });

    await test.step("Find the brand-new asset in the inventory", async () => {
      const assetListPage = new AssetListPage(page);
      await assetListPage.searchFor(demoAssetName);
      await expect(assetListPage.assetRows).toHaveCount(1);
      await expect(assetListPage.assetRows.first()).toContainText(demoAssetName);
    });

    await test.step("Pivot to the repair-review queue", async () => {
      const reviewsMenuItem = page.getByRole("menuitem", {
        name: /Repair Management|Reviews|維修管理/i,
      });
      await expect(reviewsMenuItem).toBeVisible({ timeout: 15_000 });
      await reviewsMenuItem.click({ timeout: 15_000 });
      await expect(page).toHaveURL(/\/reviews$/);
      await expect(
        page.getByRole("heading", { name: /Repair Requests|Repair Reviews/i }),
      ).toBeVisible();
    });

    await test.step("Approve the top Pending Review with a repair plan", async () => {
      const reviewsPage = new ReviewsPage(page);
      await reviewsPage.filterByStatus("Pending Review");
      await expect(reviewsPage.requestRows.first()).toBeVisible();
      await reviewsPage.openFirstRequestDetail();

      const reviewDetailPage = new ReviewDetailPage(page);
      await reviewDetailPage.openApproveModal();
      await reviewDetailPage.submitApproveForm({
        repairPlan: "Demo: dispatch to authorised vendor for hinge replacement.",
        repairVendor: "聯強國際維修中心",
        repairCost: "4200",
        plannedDate: "2026-06-15",
      });
      await expect(page.getByText("Under Repair").first()).toBeVisible();
    });

    await test.step("Vendor returns the unit — record completion", async () => {
      const reviewDetailPage = new ReviewDetailPage(page);
      await reviewDetailPage.openCompleteModal();
      await reviewDetailPage.submitCompleteForm({
        repairDate: "2026-06-18",
        faultContent: "Demo: cracked hinge confirmed; replaced with OEM part.",
        repairPlan: "Demo: bench-tested before return, no further issues observed.",
        repairCost: "4200",
        repairVendor: "聯強國際維修中心",
      });
      // Status reaches the terminal Completed state — no more transition
      // buttons on the action panel.
      await expect(page.getByText("Completed").first()).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Complete", exact: true }),
      ).toBeHidden();
    });
  });
});
