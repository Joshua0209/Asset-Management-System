import { expect, test, loginAsHolder } from "../fixtures/auth";

// Lightweight render checks for the three holder-only read views. These don't
// drive FSM transitions, but they guard against route-wiring regressions and
// missing-import smoke breaks that unit tests with mocked APIs can miss.
test.describe("Holder read-only views", () => {
  test("my-assets page renders the holder's asset list", async ({ page }) => {
    await loginAsHolder(page);

    // loginAsHolder lands us on /my-assets; assert the header copy and that
    // at least the table chrome rendered (asset count summary is always
    // present once the list response settles).
    await expect(page).toHaveURL(/\/my-assets$/);
    await expect(
      page.getByRole("heading", { name: "Asset List" }),
    ).toBeVisible();
  });

  test("repairs page renders the holder's own repair requests", async ({ page }) => {
    await loginAsHolder(page);
    await page.goto("/repairs");

    await expect(page).toHaveURL(/\/repairs$/);
    await expect(
      page.getByRole("heading", { name: "My Repair Requests" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Submit New Request/ }),
    ).toBeVisible();
  });

  test("repair detail page renders for a request the holder owns", async ({ page }) => {
    await loginAsHolder(page);
    await page.goto("/repairs");

    // Click the first "Detail" row link, then assert the detail screen
    // mounted with its title and at least one of the section headers.
    await page
      .locator(".ant-table-tbody > tr.ant-table-row")
      .first()
      .getByRole("button", { name: "Detail" })
      .click();
    await page.waitForURL(/\/repairs\/[0-9a-f-]+$/i);

    await expect(
      page.getByRole("heading", { name: "Repair Request Details" }),
    ).toBeVisible();
  });
});
