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

    const validCreatePayload = {
      name: "Laptop",
      model: "X1",
      category: "computer" as const,
      supplier: "Supplier A",
      purchase_date: "2026-01-01",
      purchase_amount: "1000",
    };

    it("createAsset posts payload to /assets when validation passes", async () => {
      mockRequest.mockResolvedValueOnce({ data: { id: "asset-1", version: 1 } });

      const result = await mod.createAsset(validCreatePayload);

      expect(mockRequest).toHaveBeenCalledWith({
        method: "POST",
        url: "/assets",
        data: validCreatePayload,
      });
      expect(result.id).toBe("asset-1");
    });

    it("createAsset rejects when required fields are blank", async () => {
      await expect(mod.createAsset({ ...validCreatePayload, name: "" })).rejects.toMatchObject({
        code: "validation_error",
      });
      await expect(mod.createAsset({ ...validCreatePayload, model: "" })).rejects.toMatchObject({
        code: "validation_error",
      });
      await expect(mod.createAsset({ ...validCreatePayload, supplier: "" })).rejects.toMatchObject({
        code: "validation_error",
      });
      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("createAsset rejects malformed and future purchase_date", async () => {
      await expect(
        mod.createAsset({ ...validCreatePayload, purchase_date: "not-a-date" }),
      ).rejects.toMatchObject({ code: "validation_error" });

      await expect(
        mod.createAsset({ ...validCreatePayload, purchase_date: "2099-01-01" }),
      ).rejects.toMatchObject({ code: "validation_error" });
      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("createAsset rejects malformed warranty_expiry and warranty before purchase", async () => {
      await expect(
        mod.createAsset({ ...validCreatePayload, warranty_expiry: "not-a-date" }),
      ).rejects.toMatchObject({ code: "validation_error" });

      await expect(
        mod.createAsset({
          ...validCreatePayload,
          warranty_expiry: "2025-01-01",
        }),
      ).rejects.toMatchObject({ code: "validation_error" });
      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("createAsset rejects purchase_amount with bad format / zero / overflow", async () => {
      await expect(
        mod.createAsset({ ...validCreatePayload, purchase_amount: "abc" }),
      ).rejects.toMatchObject({ code: "validation_error" });
      await expect(
        mod.createAsset({ ...validCreatePayload, purchase_amount: "0" }),
      ).rejects.toMatchObject({ code: "validation_error" });
      await expect(
        mod.createAsset({ ...validCreatePayload, purchase_amount: "1234567890123456" }),
      ).rejects.toMatchObject({ code: "validation_error" });
      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("createAsset rejects fields exceeding max length", async () => {
      const longName = "x".repeat(121);
      await expect(
        mod.createAsset({ ...validCreatePayload, name: longName }),
      ).rejects.toMatchObject({ code: "validation_error" });
      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("updateAsset patches /assets/:id when validation passes", async () => {
      mockRequest.mockResolvedValueOnce({ data: { id: "asset-1", version: 2 } });

      const result = await mod.updateAsset("asset-1", { name: "New Name", version: 1 });

      expect(mockRequest).toHaveBeenCalledWith({
        method: "PATCH",
        url: "/assets/asset-1",
        data: { name: "New Name", version: 1 },
      });
      expect(result.version).toBe(2);
    });

    it("updateAsset rejects empty required strings only when present", async () => {
      await expect(mod.updateAsset("asset-1", { name: "", version: 1 })).rejects.toMatchObject({
        code: "validation_error",
      });
      await expect(mod.updateAsset("asset-1", { model: " ", version: 1 })).rejects.toMatchObject({
        code: "validation_error",
      });
      await expect(mod.updateAsset("asset-1", { supplier: "", version: 1 })).rejects.toMatchObject({
        code: "validation_error",
      });
      expect(mockRequest).not.toHaveBeenCalled();
    });

    it("getAssetById fetches /assets/:id and unwraps response", async () => {
      mockRequest.mockResolvedValueOnce({ data: { id: "asset-1" } });

      const asset = await mod.getAssetById("asset-1");

      expect(mockRequest).toHaveBeenCalledWith({
        method: "GET",
        url: "/assets/asset-1",
      });
      expect(asset.id).toBe("asset-1");
    });

    it("assignAsset posts to /assets/:id/assign", async () => {
      mockRequest.mockResolvedValueOnce({ data: { id: "asset-1", status: "in_use" } });

      await mod.assignAsset("asset-1", {
        responsible_person_id: "holder-1",
        assignment_date: "2026-05-08",
        version: 1,
      });

      expect(mockRequest).toHaveBeenCalledWith({
        method: "POST",
        url: "/assets/asset-1/assign",
        data: {
          responsible_person_id: "holder-1",
          assignment_date: "2026-05-08",
          version: 1,
        },
      });
    });

    it("unassignAsset posts to /assets/:id/unassign", async () => {
      mockRequest.mockResolvedValueOnce({ data: { id: "asset-1", status: "in_stock" } });

      await mod.unassignAsset("asset-1", {
        reason: "transfer",
        unassignment_date: "2026-05-10",
        version: 1,
      });

      expect(mockRequest).toHaveBeenCalledWith({
        method: "POST",
        url: "/assets/asset-1/unassign",
        data: {
          reason: "transfer",
          unassignment_date: "2026-05-10",
          version: 1,
        },
      });
    });

    it("disposeAsset posts to /assets/:id/dispose", async () => {
      mockRequest.mockResolvedValueOnce({ data: { id: "asset-1", status: "disposed" } });

      await mod.disposeAsset("asset-1", {
        disposal_reason: "end-of-life",
        version: 1,
      });

      expect(mockRequest).toHaveBeenCalledWith({
        method: "POST",
        url: "/assets/asset-1/dispose",
        data: { disposal_reason: "end-of-life", version: 1 },
      });
    });

    it("listAssets forwards optional filters as snake_case query params", async () => {
      mockRequest.mockResolvedValueOnce({
        data: [],
        meta: { total: 0, page: 1, per_page: 5, total_pages: 0 },
      });

      await mod.listAssets({
        page: 1,
        perPage: 5,
        q: "abc",
        status: "in_use",
        category: "computer",
        department: "IT",
        location: "HQ",
        responsiblePersonId: "h1",
        sort: "asset_code",
      });

      expect(mockRequest).toHaveBeenCalledWith({
        method: "GET",
        url: "/assets",
        params: {
          page: 1,
          per_page: 5,
          q: "abc",
          status: "in_use",
          category: "computer",
          department: "IT",
          location: "HQ",
          responsible_person_id: "h1",
          sort: "asset_code",
        },
      });
    });
  });
});
