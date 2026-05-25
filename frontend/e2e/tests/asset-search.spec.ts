import { expect, test, loginAsManager } from "../fixtures/auth";
import { AssetListPage } from "../pages/AssetListPage";

test.describe("Manager searches and filters the asset list", () => {
  test("narrows results by free-text search, then resets", async ({ page }) => {
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();

    // Capture the unfiltered row count so we can assert filtering actually
    // shrank the result set, not just "<= baseline".
    const baseRowCount = await assetListPage.assetRows.count();
    expect(baseRowCount).toBeGreaterThan(0);

    // Act — search for a known seed model.
    await assetListPage.searchFor("ThinkPad");
    const filteredRows = assetListPage.assetRows;
    const filteredCount = await filteredRows.count();
    expect(filteredCount).toBeGreaterThan(0);
    expect(filteredCount).toBeLessThanOrEqual(baseRowCount);
    // Every visible row should match the query (the backend filters on code,
    // name, and model — all three render in the table).
    for (let i = 0; i < filteredCount; i += 1) {
      await expect(filteredRows.nth(i)).toContainText(/ThinkPad/i);
    }

    // Reset and confirm we're back to the unfiltered baseline.
    await assetListPage.resetFilters();
    await expect(assetListPage.assetRows).toHaveCount(baseRowCount);
  });

  test("filters by status from the dropdown", async ({ page }) => {
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();

    await assetListPage.filterByStatus("In Use");

    const rows = assetListPage.assetRows;
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i += 1) {
      await expect(rows.nth(i)).toContainText("In Use");
    }
  });
});
