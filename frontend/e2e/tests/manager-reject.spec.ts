import { expect, test, loginAsManager } from "../fixtures/auth";
import { ReviewsPage } from "../pages/ReviewsPage";
import { ReviewDetailPage } from "../pages/ReviewDetailPage";

test.describe("Manager rejects a pending repair request", () => {
  test("transitions a pending_review request into rejected", async ({ page }) => {
    // Arrange — pick a pending_review row, the only state where Reject is
    // exposed in the action panel. Mirrors the manager-approve spec but
    // drives the opposite FSM transition.
    await loginAsManager(page);
    const reviewsPage = new ReviewsPage(page);
    await reviewsPage.goto();
    await reviewsPage.filterByStatus("Pending Review");

    await expect(reviewsPage.requestRows.first()).toBeVisible();
    await reviewsPage.openFirstRequestDetail();

    // Act — open the reject modal and submit a reason.
    const reviewDetailPage = new ReviewDetailPage(page);
    await reviewDetailPage.openRejectModal();
    await reviewDetailPage.submitRejectForm({
      rejectionReason: "E2E: out of warranty, rejecting per cost policy.",
    });

    // Assert — toast first (guards against silently-dropped api.success),
    // then FSM: status flips to Rejected and the action panel collapses
    // (no actions on a terminal-rejected request).
    await expect(page.getByText("Repair request rejected")).toBeVisible();
    await expect(page.getByText("Current Status")).toBeVisible();
    await expect(page.getByText("Rejected").first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Approve", exact: true }),
    ).toBeHidden();
  });
});
