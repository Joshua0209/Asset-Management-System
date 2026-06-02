import type { Locator, Page } from "@playwright/test";

// Demo instrumentation: make recorded runs look hand-driven instead of
// teleported. Wraps a Page so that every click glides the real mouse to the
// target with intermediate steps, every fill moves the cursor to the field
// first, and a visible SVG cursor overlay tracks the pointer. The technique
// (injected cursor + stepped mouse.move before click) follows
// `.claude/rules/ui-demo.md`.
//
// This is a pure presentation wrapper: it never changes WHAT an action does,
// only adds a visible approach motion before it. If the glide can't resolve a
// box (off-screen, detached) it silently falls through to the real action so
// the canonical Playwright error still surfaces.

// Number of intermediate points Playwright emits between the cursor's current
// spot and the target. Higher = smoother glide on camera.
const GLIDE_STEPS = 18;
// Settle pause (ms) after the cursor lands, before the click/fill fires — long
// enough to read as "the user aimed, then acted".
const SETTLE_MS = 140;

// Locator factory methods whose return value is itself a Locator. We re-wrap
// those so chained calls (`modal.getByRole(...).click()`) stay instrumented.
const LOCATOR_CHAIN = new Set([
  "locator",
  "getByRole",
  "getByLabel",
  "getByText",
  "getByPlaceholder",
  "getByTestId",
  "getByTitle",
  "getByAltText",
  "filter",
  "first",
  "last",
  "nth",
  "and",
  "or",
]);

const ARROW_CURSOR_SVG = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
</svg>`;

// Inject (idempotently) a fixed-position arrow that follows DOM mousemove
// events. Destroyed on full-document navigation, so we re-run it on every
// main-frame navigation in installDemoCursor.
async function injectCursor(page: Page): Promise<void> {
  try {
    await page.evaluate((svg) => {
      if (document.getElementById("demo-cursor")) return;
      const cursor = document.createElement("div");
      cursor.id = "demo-cursor";
      cursor.innerHTML = svg;
      cursor.style.cssText = [
        "position:fixed",
        "z-index:999999",
        "pointer-events:none",
        "width:24px",
        "height:24px",
        "left:0",
        "top:0",
        "transition:left 0.08s linear, top 0.08s linear",
        "filter:drop-shadow(1px 1px 2px rgba(0,0,0,0.3))",
      ].join(";");
      document.body.appendChild(cursor);
      document.addEventListener("mousemove", (e) => {
        cursor.style.left = `${e.clientX}px`;
        cursor.style.top = `${e.clientY}px`;
      });
    }, ARROW_CURSOR_SVG);
  } catch {
    // Body not ready yet (very early in a navigation) — the next framenavigated
    // or the first glide will re-inject. Never fail a demo over the overlay.
  }
}

// Move the real pointer to the centre of `locator` with visible intermediate
// steps, then pause so the landing reads on camera. Best-effort: any failure
// is swallowed so the subsequent real action owns the error.
async function glideTo(page: Page, locator: Locator): Promise<void> {
  try {
    await locator.scrollIntoViewIfNeeded({ timeout: 2_000 });
    const box = await locator.boundingBox({ timeout: 2_000 });
    if (!box) return;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {
      steps: GLIDE_STEPS,
    });
    await page.waitForTimeout(SETTLE_MS);
  } catch {
    // Non-actionable right now; let the real click/fill produce the real error.
  }
}

function isLocatorLike(value: unknown): value is Locator {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as Locator).click === "function" &&
    typeof (value as Locator).boundingBox === "function"
  );
}

// Proxy a Locator so `.click()` and `.fill()` are preceded by a glide, and any
// chained locator factory keeps returning instrumented locators.
function wrapLocator(locator: Locator, realPage: Page): Locator {
  return new Proxy(locator, {
    get(target, prop, receiver) {
      if (prop === "click") {
        return async (...args: unknown[]) => {
          await glideTo(realPage, target);
          // @ts-expect-error — forwarding the original variadic signature.
          return target.click(...args);
        };
      }
      if (prop === "fill") {
        return async (...args: unknown[]) => {
          await glideTo(realPage, target);
          // @ts-expect-error — forwarding the original variadic signature.
          return target.fill(...args);
        };
      }
      const value = Reflect.get(target, prop, receiver);
      if (typeof prop === "string" && LOCATOR_CHAIN.has(prop) && typeof value === "function") {
        return (...args: unknown[]) => {
          const result = (value as (...a: unknown[]) => unknown).apply(target, args);
          return isLocatorLike(result) ? wrapLocator(result, realPage) : result;
        };
      }
      // Everything else (waitFor, boundingBox, isVisible, textContent, expect
      // internals, …) is forwarded bound to the real locator, untouched.
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

// Page locator factories that must hand back instrumented locators.
const PAGE_LOCATOR_FACTORIES = new Set([
  "locator",
  "getByRole",
  "getByLabel",
  "getByText",
  "getByPlaceholder",
  "getByTestId",
  "getByTitle",
  "getByAltText",
]);

// Wrap a Page so locators it produces are instrumented and the cursor overlay
// is (re)injected after each main-frame navigation. Returns the proxy; pass it
// anywhere a Page is expected (page objects, login helpers, expect).
export async function installDemoCursor(page: Page): Promise<Page> {
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) void injectCursor(page);
  });
  await injectCursor(page);

  return new Proxy(page, {
    get(target, prop, receiver) {
      const value = Reflect.get(target, prop, receiver);
      if (typeof prop === "string" && PAGE_LOCATOR_FACTORIES.has(prop) && typeof value === "function") {
        return (...args: unknown[]) => {
          const locator = (value as (...a: unknown[]) => Locator).apply(target, args);
          return wrapLocator(locator, target);
        };
      }
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}
