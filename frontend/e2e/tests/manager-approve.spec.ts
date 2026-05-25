import { expect, test, loginAsManager } from "../fixtures/auth";
import { ReviewsPage } from "../pages/ReviewsPage";
import { ReviewDetailPage } from "../pages/ReviewDetailPage";

test.describe("Manager approves a pending repair request", () => {
  test("transitions a pending_review request into under_repair", async ({ page }) => {
    // Arrange — authenticate and filter the list to the FSM state this test
    // owns. The seed creates several pending_review requests; we pick the
    // first one off the top of the list.
    await loginAsManager(page);
    const reviewsPage = new ReviewsPage(page);
    await reviewsPage.goto();
    await reviewsPage.filterByStatus("Pending Review");

    // Guard: bail loudly if the seed didn't leave us anything to approve.
    await expect(reviewsPage.requestRows.first()).toBeVisible();

    await reviewsPage.openFirstRequestDetail();

    // Act — fill the approve modal with realistic repair-plan data.
    const reviewDetailPage = new ReviewDetailPage(page);
    await reviewDetailPage.openApproveModal();
    await reviewDetailPage.submitApproveForm({
      repairPlan: "E2E: ship to vendor for keyboard module replacement.",
      repairVendor: "聯強國際維修中心",
      repairCost: "3500",
      plannedDate: "2026-06-10",
    });

    // Assert — the success notification surfaces and the status badge on the
    // detail page now reads "Under Repair".
    await expect(page.getByText("Repair request approved")).toBeVisible();
    await expect(page.getByText("Under Repair").first()).toBeVisible();
  });
});
