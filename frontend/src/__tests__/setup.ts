import "@testing-library/jest-dom";

// Mock matchMedia for Ant Design
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // Deprecated
    removeListener: () => {}, // Deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock ResizeObserver for Ant Design rc-resize-observer in jsdom.
// jsdom never fires resize events; observe/unobserve/disconnect are intentional no-ops.
class ResizeObserverMock {
  observe() {
    // no-op
  }

  unobserve() {
    // no-op
  }

  disconnect() {
    // no-op
  }
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  configurable: true,
  value: ResizeObserverMock,
});

// jsdom does not implement pseudo-element styles; ignore the second argument
// so rc-table scrollbar measurement does not emit noisy not-implemented errors.
const originalGetComputedStyle = globalThis.getComputedStyle.bind(globalThis);
Object.defineProperty(globalThis, 'getComputedStyle', {
  writable: true,
  configurable: true,
  value: (element: Element) => originalGetComputedStyle(element),
});
// Fix for Vitest + React Router + JSDOM AbortSignal mismatch
// This happens because React Router uses the global Request/Fetch which might be from Node (undici)
// while JSDOM provides its own AbortSignal.
const OriginalRequest = globalThis.Request;
globalThis.Request = class extends OriginalRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (init && init.signal && init.signal.constructor.name === 'AbortSignal') {
      // Strip signal to avoid realm mismatch error in undici
      delete init.signal;
    }
    super(input, init);
  }
} as typeof OriginalRequest;
