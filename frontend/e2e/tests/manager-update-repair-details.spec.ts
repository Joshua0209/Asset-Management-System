import { expect, test, loginAsManager } from "../fixtures/auth";
import { ReviewsPage } from "../pages/ReviewsPage";
import { ReviewDetailPage } from "../pages/ReviewDetailPage";

test.describe("Manager updates repair details mid-flight", () => {
  test("saves edited repair plan on an under_repair request", async ({ page }) => {
    // Arrange — "Update Details" is only exposed for under_repair status, the
    // window between approve and complete where the vendor reports back with
    // revised information.
    await loginAsManager(page);
    const reviewsPage = new ReviewsPage(page);
    await reviewsPage.goto();
    await reviewsPage.filterByStatus("Under Repair");

    await expect(reviewsPage.requestRows.first()).toBeVisible();
    await reviewsPage.openFirstRequestDetail();

    const newPlan =
      "E2E: vendor revised plan — replace mainboard instead of keyboard module.";

    // Act
    const reviewDetailPage = new ReviewDetailPage(page);
    await reviewDetailPage.openUpdateDetailsModal();
    await reviewDetailPage.submitUpdateDetailsForm({ repairPlan: newPlan });

    // Assert — the modal closes (Update Details button reappears on the
    // detail page) and the new plan text is rendered in the result section.
    await expect(reviewDetailPage.updateDetailsButton).toBeVisible();
    await expect(page.getByText(newPlan)).toBeVisible();
    // Status stays at Under Repair — this is a metadata edit, not a transition.
    await expect(page.getByText("Under Repair").first()).toBeVisible();
  });
});
