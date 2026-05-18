import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/base-client", () => ({
  request: vi.fn(),
}));

const baseClientModule = await import("@/api/base-client");
const mockRequest = vi.mocked(baseClientModule.request);

type RepairQueriesModule = typeof import("@/api/repair-requests/queries");

describe("api/repair-requests/queries", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
    vi.resetModules();
  });

  beforeEach(() => {
    vi.stubEnv("VITE_USE_MOCK_AUTH", "false");
  });

  it("listRepairRequests maps filters to backend query params", async () => {
    mockRequest.mockResolvedValueOnce({
      data: [],
      meta: { total: 0, page: 1, per_page: 20, total_pages: 0 },
    });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    await mod.listRepairRequests({
      page: 2,
      perPage: 10,
      status: "pending_review",
      assetId: "asset-1",
      requesterId: "user-1",
      sort: "-created_at",
    });

    expect(mockRequest).toHaveBeenCalledWith({
      method: "GET",
      url: "/repair-requests",
      params: {
        page: 2,
        per_page: 10,
        status: "pending_review",
        asset_id: "asset-1",
        requester_id: "user-1",
        sort: "-created_at",
      },
    });
  });

  it("approveRepairRequest posts version and optionally follows with repair-details update", async () => {
    mockRequest
      .mockResolvedValueOnce({
        data: {
          id: "rr-1",
          asset_id: "asset-1",
          requester_id: "holder-1",
          reviewer_id: "manager-1",
          status: "under_repair",
          fault_description: "desc",
          repair_date: null,
          fault_content: null,
          repair_plan: null,
          repair_cost: null,
          repair_vendor: null,
          rejection_reason: null,
          completed_at: null,
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T00:00:00Z",
          version: 2,
          asset: { id: "asset-1", asset_code: "AST-1", name: "Asset" },
          requester: { id: "holder-1", name: "Holder" },
          reviewer: { id: "manager-1", name: "Manager" },
          images: [],
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: "rr-1",
          asset_id: "asset-1",
          requester_id: "holder-1",
          reviewer_id: "manager-1",
          status: "under_repair",
          fault_description: "desc",
          repair_date: "2026-04-20",
          fault_content: "",
          repair_plan: "replace board",
          repair_cost: "2000",
          repair_vendor: "Vendor",
          rejection_reason: null,
          completed_at: null,
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T00:00:00Z",
          version: 3,
          asset: { id: "asset-1", asset_code: "AST-1", name: "Asset" },
          requester: { id: "holder-1", name: "Holder" },
          reviewer: { id: "manager-1", name: "Manager" },
          images: [],
        },
      });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    const result = await mod.approveRepairRequest("rr-1", {
      version: 1,
      repair_plan: "replace board",
      repair_vendor: "Vendor",
      repair_cost: "2000",
      planned_date: "2026-04-20",
    });

    expect(mockRequest).toHaveBeenNthCalledWith(1, {
      method: "POST",
      url: "/repair-requests/rr-1/approve",
      data: { version: 1 },
    });
    expect(mockRequest).toHaveBeenNthCalledWith(2, {
      method: "PATCH",
      url: "/repair-requests/rr-1/repair-details",
      data: {
        version: 2,
        repair_date: "2026-04-20",
        repair_plan: "replace board",
        repair_cost: "2000",
        repair_vendor: "Vendor",
      },
    });
    expect(result.version).toBe(3);
  });

  it("approveRepairRequest skips details update when no extra fields are provided", async () => {
    mockRequest.mockResolvedValueOnce({
      data: { id: "rr-1", version: 2, status: "under_repair" },
    });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    const result = await mod.approveRepairRequest("rr-1", { version: 1 });

    expect(mockRequest).toHaveBeenCalledTimes(1);
    expect(mockRequest).toHaveBeenCalledWith({
      method: "POST",
      url: "/repair-requests/rr-1/approve",
      data: { version: 1 },
    });
    expect(result.version).toBe(2);
  });

  it("getRepairRequestById unwraps both wrapped and unwrapped responses", async () => {
    mockRequest
      .mockResolvedValueOnce({ data: { id: "rr-1", version: 1 } })
      .mockResolvedValueOnce({ id: "rr-2", version: 1 });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    const wrapped = await mod.getRepairRequestById("rr-1");
    const unwrapped = await mod.getRepairRequestById("rr-2");

    expect(wrapped.id).toBe("rr-1");
    expect(unwrapped.id).toBe("rr-2");
    expect(mockRequest).toHaveBeenNthCalledWith(1, {
      method: "GET",
      url: "/repair-requests/rr-1",
    });
  });

  it("rejectRepairRequest sends rejection_reason or fallback reason", async () => {
    mockRequest
      .mockResolvedValueOnce({ data: { id: "rr-1", status: "rejected", version: 2 } })
      .mockResolvedValueOnce({ data: { id: "rr-2", status: "rejected", version: 2 } });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    await mod.rejectRepairRequest("rr-1", { version: 1, rejection_reason: "no fault" });
    await mod.rejectRepairRequest("rr-2", { version: 1, reason: "fallback" });

    expect(mockRequest).toHaveBeenNthCalledWith(1, {
      method: "POST",
      url: "/repair-requests/rr-1/reject",
      data: { version: 1, rejection_reason: "no fault" },
    });
    expect(mockRequest).toHaveBeenNthCalledWith(2, {
      method: "POST",
      url: "/repair-requests/rr-2/reject",
      data: { version: 1, rejection_reason: "fallback" },
    });
  });

  it("updateRepairRequestDetails patches the repair-details endpoint", async () => {
    mockRequest.mockResolvedValueOnce({ data: { id: "rr-1", version: 2 } });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    await mod.updateRepairRequestDetails("rr-1", {
      version: 1,
      fault_content: "connector",
      repair_plan: "replace",
      repair_cost: "1500",
    });

    expect(mockRequest).toHaveBeenCalledWith({
      method: "PATCH",
      url: "/repair-requests/rr-1/repair-details",
      data: {
        version: 1,
        fault_content: "connector",
        repair_plan: "replace",
        repair_cost: "1500",
      },
    });
  });

  it("completeRepairRequest posts complete payload", async () => {
    mockRequest.mockResolvedValueOnce({ data: { id: "rr-1", status: "completed", version: 3 } });

    const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");
    const result = await mod.completeRepairRequest("rr-1", {
      version: 2,
      repair_date: "2026-04-25",
      fault_content: "fixed",
      repair_plan: "done",
      repair_cost: "2000",
      repair_vendor: "Vendor",
    });

    expect(mockRequest).toHaveBeenCalledWith({
      method: "POST",
      url: "/repair-requests/rr-1/complete",
      data: {
        version: 2,
        repair_date: "2026-04-25",
        fault_content: "fixed",
        repair_plan: "done",
        repair_cost: "2000",
        repair_vendor: "Vendor",
      },
    });
    expect(result.status).toBe("completed");
  });

  describe("mock mode", () => {
    beforeEach(() => {
      vi.stubEnv("VITE_USE_MOCK_AUTH", "true");
    });

    it("delegates list/get/approve/reject/details/complete to mock backend", async () => {
      vi.doMock("@/mocks/mockBackend", () => ({
        listRepairRequests: vi.fn().mockReturnValue({ data: [], meta: { total: 0, page: 1, per_page: 20, total_pages: 0 } }),
        getRepairRequestById: vi.fn().mockReturnValue({ id: "rr-1" }),
        approveRepairRequest: vi.fn().mockReturnValue({ id: "rr-1", version: 2 }),
        rejectRepairRequest: vi.fn().mockReturnValue({ id: "rr-1", version: 2 }),
        updateRepairRequestDetails: vi.fn().mockReturnValue({ id: "rr-1", version: 2 }),
        completeRepairRequest: vi.fn().mockReturnValue({ id: "rr-1", version: 3 }),
      }));

      const mod: RepairQueriesModule = await import("@/api/repair-requests/queries");

      await mod.listRepairRequests({ page: 1, perPage: 5 });
      const got = await mod.getRepairRequestById("rr-1");
      expect(got.id).toBe("rr-1");

      const approved = await mod.approveRepairRequest("rr-1", { version: 1 });
      expect(approved.version).toBe(2);

      const rejected = await mod.rejectRepairRequest("rr-1", {
        version: 1,
        rejection_reason: "n/a",
      });
      expect(rejected.id).toBe("rr-1");

      const detailed = await mod.updateRepairRequestDetails("rr-1", { version: 1 });
      expect(detailed.id).toBe("rr-1");

      const completed = await mod.completeRepairRequest("rr-1", {
        version: 2,
        repair_date: "2026-04-25",
        fault_content: "ok",
        repair_plan: "ok",
        repair_cost: "0",
        repair_vendor: "v",
      });
      expect(completed.version).toBe(3);

      expect(mockRequest).not.toHaveBeenCalled();
    });
  });
});
