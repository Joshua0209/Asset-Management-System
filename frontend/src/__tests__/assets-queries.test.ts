import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DUMMY_HOLDERS } from "../mocks/assets";
import { saveSession } from "../auth/storage";

vi.mock("../api/base-client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details: Array<{ field: string; message: string; code: string }>;

    constructor(
      status: number,
      code: string,
      message: string,
      details: Array<{ field: string; message: string; code: string }> = [],
    ) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
      this.details = details;
    }
  },
  request: vi.fn(),
}));

const baseClientModule = await import("../api/base-client");
const mockRequest = vi.mocked(baseClientModule.request);

type QueriesModule = typeof import("../api/assets/queries");

function sessionFor(userId: string, role: "holder" | "manager") {
  return {
    token: `mock-token-${userId}`,
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    user: {
      id: userId,
      email: `${userId}@example.com`,
      name: userId,
      role,
    },
  };
}

describe("api/assets/queries", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
    vi.resetModules();
    globalThis.localStorage.clear();
  });

  describe("mock mode", () => {
    let mod: QueriesModule;

    beforeEach(async () => {
      vi.stubEnv("VITE_USE_MOCK_AUTH", "true");
      vi.resetModules();
      mod = await import("../api/assets/queries");
    });

    it("listAssets returns paginated dummy assets and maps responsible_person_id", async () => {
      const result = await mod.listAssets({ page: 2, perPage: 3 });

      expect(mockRequest).not.toHaveBeenCalled();
      expect(result.meta).toEqual({
        total: 18,
        page: 2,
        per_page: 3,
        total_pages: 6,
      });
      expect(result.data).toHaveLength(3);
      expect(result.data[0]?.asset_code).toBe("AST-2026-00004");
      expect(result.data[0]?.responsible_person_id).toBe(DUMMY_HOLDERS[2]?.id);
    });

    it("listMyAssets returns only assets for current holder when IDs match", async () => {
      saveSession(sessionFor(DUMMY_HOLDERS[1]!.id, "holder"));

      const result = await mod.listMyAssets({ page: 1, perPage: 20 });

      expect(mockRequest).not.toHaveBeenCalled();
      expect(result.meta.total).toBeGreaterThan(0);
      expect(result.data.every((asset) => asset.responsible_person_id === DUMMY_HOLDERS[1]!.id)).toBe(
        true,
      );
    });

    it("listMyAssets falls back to first dummy holder for unmatched mock holder IDs", async () => {
      saveSession(sessionFor("mock-holder", "holder"));

      const result = await mod.listMyAssets({ page: 1, perPage: 20 });

      expect(result.meta.total).toBeGreaterThan(0);
      expect(result.data.every((asset) => asset.responsible_person_id === DUMMY_HOLDERS[0]!.id)).toBe(
        true,
      );
    });
  });

  describe("real API mode", () => {
    let mod: QueriesModule;

    beforeEach(async () => {
      vi.stubEnv("VITE_USE_MOCK_AUTH", "false");
      vi.resetModules();
      mod = await import("../api/assets/queries");
    });

    it("listAssets calls backend /assets endpoint with normalized params", async () => {
      mockRequest.mockResolvedValueOnce({
        data: [],
        meta: { total: 0, page: 1, per_page: 5, total_pages: 0 },
      });

      await mod.listAssets({ page: 3, perPage: 10 });

      expect(mockRequest).toHaveBeenCalledWith({
        method: "GET",
        url: "/assets",
        params: { page: 3, per_page: 10 },
      });
    });

    it("listMyAssets calls backend /assets/mine endpoint and default pagination", async () => {
      mockRequest.mockResolvedValueOnce({
        data: [],
        meta: { total: 0, page: 1, per_page: 5, total_pages: 0 },
      });

      await mod.listMyAssets();

      expect(mockRequest).toHaveBeenCalledWith({
        method: "GET",
        url: "/assets/mine",
        params: { page: 1, per_page: 5 },
      });
    });

    it("createAsset rejects negative purchase_amount before hitting API", async () => {
      await expect(
        mod.createAsset({
          name: "Laptop",
          model: "X1",
          category: "computer",
          supplier: "Supplier A",
          purchase_date: "2026-01-01",
          purchase_amount: "-5",
        }),
      ).rejects.toMatchObject({
        name: "ApiError",
        status: 422,
        code: "validation_error",
      });

      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("createAsset rejects warranty_expiry earlier than activation_date before hitting API", async () => {
      await expect(
        mod.createAsset({
          name: "Laptop",
          model: "X1",
          category: "computer",
          supplier: "Supplier A",
          purchase_date: "2026-01-01",
          purchase_amount: "1000",
          activation_date: "2026-05-10",
          warranty_expiry: "2026-05-01",
        }),
      ).rejects.toMatchObject({
        name: "ApiError",
        status: 422,
        code: "validation_error",
      });

      expect(mockRequest).not.toHaveBeenCalled();
    });
  });
});
