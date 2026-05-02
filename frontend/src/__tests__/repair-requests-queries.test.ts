import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/base-client", () => ({
  request: vi.fn(),
}));

const baseClientModule = await import("../api/base-client");
const mockRequest = vi.mocked(baseClientModule.request);

type RepairQueriesModule = typeof import("../api/repair-requests/queries");

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

    const mod: RepairQueriesModule = await import("../api/repair-requests/queries");
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

    const mod: RepairQueriesModule = await import("../api/repair-requests/queries");
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
});
