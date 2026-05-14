import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/base-client", () => ({
  request: vi.fn(),
}));

const baseClientModule = await import("@/api/base-client");
const mockRequest = vi.mocked(baseClientModule.request);

type UsersQueriesModule = typeof import("@/api/users/queries");

describe("api/users/queries", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
    vi.resetModules();
  });

  beforeEach(() => {
    vi.stubEnv("VITE_USE_MOCK_AUTH", "false");
  });

  it("normalizes non-paginated users response from current backend", async () => {
    mockRequest.mockResolvedValueOnce({
      data: [
        {
          id: "u1",
          email: "alice@example.com",
          name: "Alice",
          role: "holder",
          department: "IT",
          created_at: "2026-04-01T00:00:00Z",
        },
        {
          id: "u2",
          email: "manager@example.com",
          name: "Manager",
          role: "manager",
          department: "Ops",
          created_at: "2026-04-01T00:00:00Z",
        },
      ],
    });

    const mod: UsersQueriesModule = await import("@/api/users/queries");
    const response = await mod.listUsers({ page: 1, perPage: 10, role: "holder", q: "ali" });

    expect(mockRequest).toHaveBeenCalledWith({
      method: "GET",
      url: "/users",
      params: {
        page: 1,
        per_page: 10,
        role: "holder",
        department: undefined,
        q: "ali",
      },
    });
    expect(response.meta.total).toBe(1);
    expect(response.data).toHaveLength(1);
    expect(response.data[0]?.id).toBe("u1");
  });

  it("keeps paginated backend response unchanged", async () => {
    mockRequest.mockResolvedValueOnce({
      data: [
        {
          id: "u1",
          email: "alice@example.com",
          name: "Alice",
          role: "holder",
          department: "IT",
          created_at: "2026-04-01T00:00:00Z",
        },
      ],
      meta: {
        total: 1,
        page: 1,
        per_page: 20,
        total_pages: 1,
      },
    });

    const mod: UsersQueriesModule = await import("@/api/users/queries");
    const response = await mod.listUsers();

    expect(response.meta.total).toBe(1);
    expect(response.meta.per_page).toBe(20);
  });
});
