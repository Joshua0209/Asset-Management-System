import { expect, test, loginAsManager } from "../fixtures/auth";

test.describe("Manager Dashboard", () => {
  test("renders the dashboard with title and description after manager login", async ({
    page,
  }) => {
    // loginAsManager already navigates to /dashboard. This test guards the
    // route + render path even though the Dashboard component is currently a
    // placeholder — when real widgets land they'll need this safety net.
    await loginAsManager(page);

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(
      page.getByRole("heading", { name: "Dashboard", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "Monitor asset inventory, repair workload, and review activity from one operational view.",
      ),
    ).toBeVisible();
  });
});
