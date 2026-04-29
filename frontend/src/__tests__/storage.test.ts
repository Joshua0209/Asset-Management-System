import { afterEach, describe, expect, it } from "vitest";
import {
  UNAUTHORIZED_EVENT,
  clearSession,
  getToken,
  loadSession,
  saveSession,
} from "../auth/storage";
import type { AuthSession } from "../api/auth";

const STORAGE_KEY = "ams-auth";

function makeSession(overrides: Partial<AuthSession> = {}): AuthSession {
  return {
    token: "tkn",
    expiresAt: new Date(Date.now() + 3600_000).toISOString(),
    user: { id: "u-1", email: "a@b.c", name: "A", role: "holder" },
    ...overrides,
  };
}

describe("auth/storage", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("returns null when nothing is stored", () => {
    expect(loadSession()).toBeNull();
    expect(getToken()).toBeNull();
  });

  it("round-trips a valid session via saveSession + loadSession", () => {
    const session = makeSession({ token: "abc" });
    saveSession(session);
    expect(loadSession()).toEqual(session);
    expect(getToken()).toBe("abc");
  });

  it("returns null and purges storage when the session is expired", () => {
    saveSession(makeSession({ expiresAt: new Date(Date.now() - 1000).toISOString() }));
    expect(loadSession()).toBeNull();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("returns null when the stored payload is malformed JSON", () => {
    window.localStorage.setItem(STORAGE_KEY, "{not json");
    expect(loadSession()).toBeNull();
  });

  it("returns null when required fields are missing", () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "x" }));
    expect(loadSession()).toBeNull();
  });

  it("clearSession removes the stored entry", () => {
    saveSession(makeSession());
    clearSession();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("exports a stable UNAUTHORIZED_EVENT name", () => {
    // Pinning the event name guards against silent renames that would
    // break the AuthContext listener wiring.
    expect(UNAUTHORIZED_EVENT).toBe("ams:auth-unauthorized");
  });
});
