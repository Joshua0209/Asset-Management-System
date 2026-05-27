import { expect, test, loginAsHolder } from "../fixtures/auth";
import { SubmitRepairPage } from "../pages/SubmitRepairPage";

test.describe("Holder submits a repair request", () => {
  test("submits a repair request with an attached image and lands on the list", async ({
    page,
  }) => {
    // Arrange — start authenticated as a seeded holder. Their in-use assets
    // populate the asset dropdown (filtered server-side to status=in_use).
    await loginAsHolder(page);
    const submitRepairPage = new SubmitRepairPage(page);
    await submitRepairPage.goto();

    // Act — fill the form, attach the sample PNG, submit.
    await submitRepairPage.selectFirstAvailableAsset();
    await submitRepairPage.fillFaultDescription(
      "E2E smoke: screen flickering after sleep — Playwright run " + Date.now(),
    );
    await submitRepairPage.attachSampleImage();
    await submitRepairPage.submit();

    // Assert — the success toast surfaces and the app navigates to the
    // holder's repair-request list at /repairs.
    await expect(page.getByText("Repair request submitted successfully")).toBeVisible();
    await expect(page).toHaveURL(/\/repairs$/);
  });
});
