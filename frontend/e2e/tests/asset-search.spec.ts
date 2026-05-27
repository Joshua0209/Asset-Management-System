import { expect, test, loginAsManager } from "../fixtures/auth";
import { AssetListPage } from "../pages/AssetListPage";

test.describe("Manager searches and filters the asset list", () => {
  test("narrows results by free-text search, then resets", async ({ page }) => {
    await loginAsManager(page);
    const assetListPage = new AssetListPage(page);
    await assetListPage.goto();

    // Capture the unfiltered row count + a search term derived from real
    // data so the assertion is seed-agnostic (different demo seeds will
    // ship different model names over time).
    const baseRowCount = await assetListPage.assetRows.count();
    expect(baseRowCount).toBeGreaterThan(0);
    const firstName = await assetListPage.firstRowName();
    // Use the first whitespace-separated token of the name as the query —
    // this guarantees at least one row matches and avoids partial-word
    // surprises (e.g. searching "MacBook" when the row says "MacBook Pro").
    const query = firstName.split(/\s+/)[0];
    expect(query.length).toBeGreaterThan(0);

    // Act — search and confirm the result set narrowed.
    await assetListPage.searchFor(query);
    const filteredRows = assetListPage.assetRows;
    const filteredCount = await filteredRows.count();
    expect(filteredCount).toBeGreaterThan(0);
    expect(filteredCount).toBeLessThanOrEqual(baseRowCount);
    // Every visible row should match the query somewhere (the backend
    // filters on code, name, and model — all three render in the table).
    const queryPattern = new RegExp(escapeRegExp(query), "i");
    for (let i = 0; i < filteredCount; i += 1) {
      await expect(filteredRows.nth(i)).toContainText(queryPattern);
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

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
