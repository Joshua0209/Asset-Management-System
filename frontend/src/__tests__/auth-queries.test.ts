// Exercises the mock-mode branch of api/auth/queries (VITE_USE_MOCK_AUTH=true).
// Real-API branches go through `request()` and are covered by base-client.test.ts.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LoginPayload, RegisterPayload } from "../api/auth";

type QueriesModule = typeof import("../api/auth/queries");

describe("api/auth/queries (mock mode)", () => {
  let mod: QueriesModule;

  beforeEach(async () => {
    vi.stubEnv("VITE_USE_MOCK_AUTH", "true");
    vi.resetModules();
    mod = await import("../api/auth/queries");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    window.localStorage.clear();
  });

  it("login resolves to a manager session for the seeded admin credentials", async () => {
    const payload: LoginPayload = { email: "admin@example.com", password: "admin" };
    const session = await mod.login(payload);
    expect(session.user.role).toBe("manager");
    expect(session.token).toBe("mock-token-mock-manager");
    expect(new Date(session.expiresAt).getTime()).toBeGreaterThan(Date.now());
  });

  it("login rejects with a 401 ApiError on unknown credentials", async () => {
    await expect(
      mod.login({ email: "nope@example.com", password: "wrong" }),
    ).rejects.toMatchObject({ name: "ApiError", status: 401, code: "unauthorized" });
  });

  it("register creates a fresh holder for a new email", async () => {
    const payload: RegisterPayload = {
      email: "new@example.com",
      password: "abcd1234",
      name: "New User",
      department: "IT",
    };
    const user = await mod.register(payload);
    expect(user.email).toBe("new@example.com");
    expect(user.role).toBe("holder");
  });

  it("register rejects an already-registered email with a 409 ApiError", async () => {
    await expect(
      mod.register({
        email: "admin@example.com",
        password: "abcd1234",
        name: "Dup",
        department: "IT",
      }),
    ).rejects.toMatchObject({ name: "ApiError", status: 409, code: "conflict" });
  });

  it("fetchMe resolves to the user whose mock token is in localStorage", async () => {
    const session = await mod.login({ email: "admin@example.com", password: "admin" });
    const { saveSession } = await import("../auth/storage");
    saveSession(session);

    const user = await mod.fetchMe();
    expect(user.id).toBe("mock-manager");
    expect(user.role).toBe("manager");
  });

  it("fetchMe rejects with a 401 ApiError when no matching token is stored", async () => {
    await expect(mod.fetchMe()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
    });
  });
});
