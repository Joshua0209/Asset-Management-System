import "@testing-library/jest-dom";
import { vi } from 'vitest';
import { mockApi } from './test-helpers';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
if (globalThis.window !== undefined) {
  (globalThis.window as Window & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
}

// Node 25+ ships an unfinished WebStorage at globalThis.localStorage that
// lacks setItem/clear, and under vitest+jsdom `window === globalThis`, so
// jsdom never gets to install its own working store — both names resolve to
// the broken stub. Detect that case and install an in-memory Storage so the
// suite is portable across runtimes. No-op on Node 22 (CI default), where
// jsdom's Storage is already in place with a real setItem.
class MemoryStorage implements Storage {
  private readonly store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  if (typeof globalThis[name]?.setItem !== 'function') {
    Object.defineProperty(globalThis, name, {
      writable: true,
      configurable: true,
      value: new MemoryStorage(),
    });
  }
}

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

// Mock URL.createObjectURL and URL.revokeObjectURL for jsdom
Object.defineProperty(URL, 'createObjectURL', {
  writable: true,
  value: () => 'blob:mock-url',
});
Object.defineProperty(URL, 'revokeObjectURL', {
  writable: true,
  value: () => {},
});

// Fix for Vitest + React Router + JSDOM AbortSignal mismatch
// This happens because React Router uses the global Request/Fetch which might be from Node (undici)
// while JSDOM provides its own AbortSignal.
const OriginalRequest = globalThis.Request;
globalThis.Request = class extends OriginalRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (init?.signal?.constructor.name === 'AbortSignal') {
      // Strip signal to avoid realm mismatch error in undici
      delete init.signal;
    }
    super(input, init);
  }
} as typeof OriginalRequest;

// Global Ant Design notification mock
vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    notification: {
      ...actual.notification,
      useNotification: () => [mockApi, null],
    },
  };
});
