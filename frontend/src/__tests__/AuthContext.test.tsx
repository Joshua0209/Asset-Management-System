import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { UNAUTHORIZED_EVENT, saveSession } from "@/auth/storage";
import type { AuthSession } from "@/api/auth";

vi.mock("@/api", () => ({
  authApi: {
    login: vi.fn(),
  },
}));

const { authApi } = await import("@/api");
const mockLogin = vi.mocked(authApi.login);

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

const seededSession = (): AuthSession => ({
  token: "tkn",
  expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  user: { id: "u-1", email: "a@b.c", name: "A", role: "manager" },
});

describe("AuthContext", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
    mockLogin.mockReset();
  });

  afterEach(() => {
    globalThis.localStorage.clear();
  });

  it("starts unauthenticated when no session is in storage", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
  });

  it("hydrates from a previously saved session", () => {
    saveSession(seededSession());
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user?.role).toBe("manager");
    expect(result.current.token).toBe("tkn");
  });

  it("login persists the returned session and exposes the user", async () => {
    mockLogin.mockResolvedValueOnce(seededSession());
    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await result.current.login("a@b.c", "pw");
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(globalThis.localStorage.getItem("ams-auth")).not.toBeNull();
  });

  it("logout clears storage and resets the user", () => {
    saveSession(seededSession());
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(globalThis.localStorage.getItem("ams-auth")).toBeNull();
  });

  it("resets state when the api layer dispatches UNAUTHORIZED_EVENT", async () => {
    saveSession(seededSession());
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      globalThis.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
    });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(false));
  });

  it("useAuth throws when used outside an AuthProvider", () => {
    // renderHook without `wrapper` mounts the hook with no provider.
    // Vitest spreads the hook error to the console — silence it for this case.
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/);
    spy.mockRestore();
  });
});
