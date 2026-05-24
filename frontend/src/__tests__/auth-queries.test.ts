// Exercises both branches of api/auth/queries:
//   - mock mode (VITE_USE_MOCK_AUTH=true): returns in-memory fixtures
//   - real-API mode (VITE_USE_MOCK_AUTH=false): forwards to base-client `request()`
//
// `request()` itself is covered by base-client.test.ts; here we only assert the
// HTTP method/url contract and the envelope-unwrapping done by queries.ts.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api";
import type { LoginPayload, RegisterPayload } from "@/api/auth";

// Mock base-client.request but preserve ApiError so mock-mode tests below
// (which `throw new ApiError(...)`) still get a real constructor.
vi.mock("@/api/base-client", async () => {
  const actual = await vi.importActual<typeof import("@/api/base-client")>("@/api/base-client");
  return {
    ...actual,
    request: vi.fn(),
  };
});

const baseClientModule = await import("@/api/base-client");
const mockRequest = vi.mocked(baseClientModule.request);

type QueriesModule = typeof import("@/api/auth/queries");

describe("api/auth/queries (mock mode)", () => {
  let mod: QueriesModule;

  beforeEach(async () => {
    vi.stubEnv("VITE_USE_MOCK_AUTH", "true");
    vi.resetModules();
    mod = await import("@/api/auth/queries");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    globalThis.localStorage.clear();
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
    const { saveSession } = await import("@/auth/storage");
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

describe("api/auth/queries (real-API mode)", () => {
  let mod: QueriesModule;

  beforeEach(async () => {
    vi.stubEnv("VITE_USE_MOCK_AUTH", "false");
    vi.resetModules();
    mockRequest.mockReset();
    mod = await import("@/api/auth/queries");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("login posts to /auth/login and unwraps the data envelope", async () => {
    mockRequest.mockResolvedValueOnce({
      data: {
        token: "tok-1",
        expires_at: "2026-12-31T00:00:00Z",
        user: { id: "u1", email: "alice@example.com", name: "Alice", role: "holder" },
      },
    });

    const payload: LoginPayload = { email: "alice@example.com", password: "abcd1234" };
    const session = await mod.login(payload);

    expect(mockRequest).toHaveBeenCalledWith({
      method: "POST",
      url: "/auth/login",
      data: payload,
    });
    expect(session.token).toBe("tok-1");
    expect(session.expiresAt).toBe("2026-12-31T00:00:00Z");
    expect(session.user.role).toBe("holder");
  });

  it("register posts to /auth/register and returns the unwrapped user", async () => {
    mockRequest.mockResolvedValueOnce({
      data: {
        id: "u-new",
        email: "new@example.com",
        name: "New User",
        role: "holder",
      },
    });

    const payload: RegisterPayload = {
      email: "new@example.com",
      password: "abcd1234",
      name: "New User",
      department: "IT",
    };
    const user = await mod.register(payload);

    expect(mockRequest).toHaveBeenCalledWith({
      method: "POST",
      url: "/auth/register",
      data: payload,
    });
    expect(user.id).toBe("u-new");
    expect(user.email).toBe("new@example.com");
    expect(user.role).toBe("holder");
  });

  it("fetchMe GETs /auth/me and returns the unwrapped user", async () => {
    mockRequest.mockResolvedValueOnce({
      data: {
        id: "u1",
        email: "alice@example.com",
        name: "Alice",
        role: "holder",
      },
    });

    const user = await mod.fetchMe();

    expect(mockRequest).toHaveBeenCalledWith({
      method: "GET",
      url: "/auth/me",
    });
    expect(user.id).toBe("u1");
    expect(user.email).toBe("alice@example.com");
  });

  // queries.ts has no try/catch around the real-API request(...) calls —
  // ApiError instances raised by base-client must bubble untouched to the
  // caller (auth provider, UI handlers, react-query). A regression that
  // wraps the request in a silent-fallback try/catch would not be caught by
  // the happy-path tests above, so each function gets a direct propagation
  // test that asserts the exact ApiError instance survives.
  it("login propagates an ApiError raised by the underlying request()", async () => {
    const apiError = new ApiError(401, "unauthorized", "Invalid email or password");
    mockRequest.mockRejectedValueOnce(apiError);

    await expect(
      mod.login({ email: "alice@example.com", password: "wrong" }),
    ).rejects.toBe(apiError);
  });

  it("register propagates an ApiError raised by the underlying request()", async () => {
    const apiError = new ApiError(409, "conflict", "Email is already registered");
    mockRequest.mockRejectedValueOnce(apiError);

    await expect(
      mod.register({
        email: "taken@example.com",
        password: "abcd1234",
        name: "Dup",
        department: "IT",
      }),
    ).rejects.toBe(apiError);
  });

  it("fetchMe propagates an ApiError raised by the underlying request()", async () => {
    const apiError = new ApiError(401, "unauthorized", "Invalid token");
    mockRequest.mockRejectedValueOnce(apiError);

    await expect(mod.fetchMe()).rejects.toBe(apiError);
  });
});
