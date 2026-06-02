import { test as authTest } from "./auth";
import { installDemoCursor } from "./demo-cursor";

// Test object for the narrative demo specs in `tests/demo/`. It reuses the auth
// fixtures but overrides `page` with the cursor-instrumented wrapper from
// demo-cursor.ts, so the existing page objects and login helpers glide the
// mouse and show a visible pointer without any change on their side.
//
// Regression specs keep importing from `./auth` (no overlay, no glide) so this
// presentation layer never touches the coverage suite.
export const test = authTest.extend({
  page: async ({ page }, use) => {
    const demoPage = await installDemoCursor(page);
    await use(demoPage);
  },
});

export { expect } from "@playwright/test";
