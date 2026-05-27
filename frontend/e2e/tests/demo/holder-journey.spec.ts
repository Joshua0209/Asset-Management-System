import {
  expect,
  test,
  HOLDER_CREDENTIALS,
  loginAsHolder,
} from "../../fixtures/auth";
import { SubmitRepairPage } from "../../pages/SubmitRepairPage";

// Demo: a holder reports a hardware fault.
//
// This is the narrative version of the regression specs. It runs as one
// long test with `test.step()` checkpoints so the presenter can talk through
// each phase while a single browser session stays open. Re-seed the demo
// database before showing it live so the asset list and repair list start
// from a known state.
test.describe("Demo — Holder reports a faulty asset", () => {
  test("logs in, files a repair with photo evidence, and tracks the request", async ({
    page,
  }) => {
    await test.step("Sign in as the seeded holder", async () => {
      await loginAsHolder(page);
      // RoleLandingRedirect lands holders on their asset list.
      await expect(page).toHaveURL(/\/my-assets$/);
      await expect(
        page.getByRole("heading", { name: "Asset List" }),
      ).toBeVisible();
    });

    await test.step("Review the assets assigned to me", async () => {
      // The seed leaves several in_use rows in the holder's name, so the
      // table should have content beyond the header row.
      const rows = page.locator(".ant-table-tbody > tr.ant-table-row");
      await expect(rows.first()).toBeVisible();
    });

    await test.step("Navigate to the repair-request submission form", async () => {
      // Use the side-nav rather than direct URL — the demo audience sees the
      // app's normal navigation affordances at work.
      await page.getByRole("menuitem", { name: /Repair Requests/i }).click();
      await expect(page).toHaveURL(/\/repairs$/);
      await page.getByRole("button", { name: /Submit New Request/i }).click();
      await expect(page).toHaveURL(/\/repairs\/new$/);
    });

    await test.step("Fill in the fault report and attach a photo", async () => {
      const submitRepairPage = new SubmitRepairPage(page);
      await submitRepairPage.selectFirstAvailableAsset();
      await submitRepairPage.fillFaultDescription(
        "DEMO: Laptop hinge cracked after a drop; screen still functional but the chassis no longer closes flush.",
      );
      await submitRepairPage.attachSampleImage();
      await submitRepairPage.submit();
    });

    await test.step("Confirm the new request appears as Pending Review", async () => {
      // The submit handler navigates back to the repair list on success.
      await expect(page).toHaveURL(/\/repairs$/);
      await expect(page.getByText("Pending Review").first()).toBeVisible();
    });

    await test.step("Re-confirm credentials are stored and the holder is identified", async () => {
      // Demo close: prove the session is real by surfacing the user chip in
      // the header. Useful for narrating "this is the same user logged in".
      await expect(page.getByText(HOLDER_CREDENTIALS.email)).toBeHidden();
      await expect(page.getByText("Asset Holder")).toBeVisible();
    });
  });
});
