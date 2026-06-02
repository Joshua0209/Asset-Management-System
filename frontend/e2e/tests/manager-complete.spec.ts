import { expect, test, loginAsManager } from "../fixtures/auth";
import { ReviewsPage } from "../pages/ReviewsPage";
import { ReviewDetailPage } from "../pages/ReviewDetailPage";

test.describe("Manager completes an in-repair request", () => {
  test("transitions an under_repair request into completed", async ({ page }) => {
    // Arrange — login and pick a request that's already in the repair phase.
    // The seed leaves multiple under_repair rows; we take the first one.
    await loginAsManager(page);
    const reviewsPage = new ReviewsPage(page);
    await reviewsPage.goto();
    await reviewsPage.filterByStatus("Under Repair");

    await expect(reviewsPage.requestRows.first()).toBeVisible();
    await reviewsPage.openFirstRequestDetail();

    // Act — fill the complete modal with the final repair record.
    const reviewDetailPage = new ReviewDetailPage(page);
    await reviewDetailPage.openCompleteModal();
    await reviewDetailPage.submitCompleteForm({
      repairDate: "2026-05-25",
      faultContent: "Confirmed faulty keyboard; module swapped at vendor.",
      repairPlan: "Replace keyboard module; bench-test before return.",
      repairCost: "3500",
      repairVendor: "聯強國際維修中心",
    });

    // Assert — toast first (guards against silently-dropped api.success;
    // see manager-update-repair-details.spec.ts for the bug history), then
    // the terminal state. The Complete button is hidden because the action
    // panel collapses to a "-" placeholder for completed/rejected requests.
    await expect(page.getByText("Repair request completed")).toBeVisible();
    await expect(page.getByText("Current Status")).toBeVisible();
    await expect(page.getByText("Completed").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Complete", exact: true })).toBeHidden();
  });
});
