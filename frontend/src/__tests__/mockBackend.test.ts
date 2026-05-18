import { describe, expect, it, vi, beforeEach } from "vitest";

interface SessionUser {
  id: string;
  email: string;
  name: string;
  role: "manager" | "holder";
}

function seedSession(user: SessionUser) {
  globalThis.localStorage.setItem(
    "ams-auth",
    JSON.stringify({
      token: `token-${user.id}`,
      expiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      user,
    }),
  );
}

async function loadBackend() {
  vi.resetModules();
  return import("@/mocks/mockBackend");
}

describe("mocks/mockBackend", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
  });

  it("filters and paginates asset list", async () => {
    const backend = await loadBackend();

    const response = backend.listAssets({
      q: "AST",
      status: "in_use",
      page: 1,
      perPage: 3,
    });

    expect(response.meta.page).toBe(1);
    expect(response.meta.per_page).toBe(3);
    expect(response.data.length).toBeLessThanOrEqual(3);
    expect(response.data.every((item) => item.status === "in_use")).toBe(true);
  });

  it("requires session for holder-scoped operations", async () => {
    const backend = await loadBackend();

    expect(() => backend.listMyAssets()).toThrow();

    try {
      backend.listMyAssets();
    } catch (error) {
      expect((error as { status?: number }).status).toBe(401);
    }
  });

  it("falls back to seeded holder assets when holder ID has no direct matches", async () => {
    const backend = await loadBackend();
    seedSession({
      id: "holder-without-assets",
      email: "x@example.com",
      name: "No Assets Holder",
      role: "holder",
    });

    const response = backend.listMyAssets({ page: 1, perPage: 5 });

    expect(response.data.length).toBeGreaterThan(0);
    expect(response.meta.page).toBe(1);
  });

  it("supports create and update asset with optimistic locking", async () => {
    const backend = await loadBackend();

    const created = backend.createAsset({
      name: "New Workstation",
      model: "ThinkStation P3",
      category: "computer",
      supplier: "Lenovo",
      purchase_date: "2026-04-01",
      purchase_amount: "50000",
      specs: "32GB RAM",
      location: "HQ",
      department: "IT",
      activation_date: null,
      warranty_expiry: null,
    });

    expect(created.status).toBe("in_stock");
    expect(created.version).toBe(1);

    const updated = backend.updateAsset(created.id, {
      version: created.version,
      name: "Updated Workstation",
      location: null,
      department: null,
    });

    expect(updated.name).toBe("Updated Workstation");
    expect(updated.location).toBe("");
    expect(updated.department).toBe("");

    expect(() =>
      backend.updateAsset(created.id, {
        version: 1,
        name: "stale",
      }),
    ).toThrow();
  });

  it("handles assign, unassign and dispose transitions", async () => {
    const backend = await loadBackend();

    const created = backend.createAsset({
      name: "Transition Asset",
      model: "T100",
      category: "tablet",
      supplier: "Vendor",
      purchase_date: "2026-04-02",
      purchase_amount: "1000",
      specs: null,
      location: "HQ",
      department: "IT",
      activation_date: null,
      warranty_expiry: null,
    });

    const holders = backend.listUsers({ role: "holder" }).data;
    const holderId = holders[0]?.id;
    expect(holderId).toBeTruthy();

    const assigned = backend.assignAsset(created.id, {
      responsible_person_id: holderId,
      assignment_date: "2026-04-03",
      version: created.version,
    });
    expect(assigned.status).toBe("in_use");
    expect(assigned.responsible_person_id).toBe(holderId);

    const unassigned = backend.unassignAsset(created.id, {
      reason: "transfer",
      unassignment_date: "2026-04-04",
      version: assigned.version,
    });
    expect(unassigned.status).toBe("in_stock");
    expect(unassigned.responsible_person_id).toBeNull();
    expect(unassigned.assignment_date).toBe("2026-04-03");
    expect(unassigned.unassignment_date).toBe("2026-04-04");

    const disposed = backend.disposeAsset(created.id, {
      disposal_reason: "end-of-life",
      version: unassigned.version,
    });
    expect(disposed.status).toBe("disposed");
    expect(disposed.disposal_reason).toBe("end-of-life");
  });

  it("rejects invalid assignment and transition operations", async () => {
    const backend = await loadBackend();

    const stockAsset = backend
      .listAssets({ status: "in_stock", page: 1, perPage: 1 })
      .data[0];
    expect(stockAsset).toBeTruthy();

    expect(() =>
      backend.assignAsset(stockAsset.id, {
        responsible_person_id: "mock-manager",
        assignment_date: "2026-04-03",
        version: stockAsset.version,
      }),
    ).toThrow();

    expect(() =>
      backend.unassignAsset(stockAsset.id, {
        reason: "invalid",
        unassignment_date: "2026-04-03",
        version: stockAsset.version,
      }),
    ).toThrow();

    const inUseAsset = backend.listAssets({ status: "in_use", page: 1, perPage: 1 }).data[0];
    expect(inUseAsset).toBeTruthy();

    expect(() =>
      backend.disposeAsset(inUseAsset.id, {
        disposal_reason: "invalid",
        version: inUseAsset.version,
      }),
    ).toThrow();
  });

  it("filters users by role, department and keyword", async () => {
    const backend = await loadBackend();

    const byRole = backend.listUsers({ role: "holder", page: 1, perPage: 50 });
    expect(byRole.data.every((user) => user.role === "holder")).toBe(true);

    const byDept = backend.listUsers({ department: "Engineering", page: 1, perPage: 50 });
    expect(byDept.data.length).toBeGreaterThan(0);

    const byQuery = backend.listUsers({ q: "admin", page: 1, perPage: 50 });
    expect(byQuery.data.some((u) => u.email.includes("admin"))).toBe(true);
  });

  it("enforces repair-request visibility rules by role", async () => {
    const backend = await loadBackend();

    seedSession({
      id: "mock-manager",
      email: "admin@example.com",
      name: "Admin Manager",
      role: "manager",
    });
    const managerList = backend.listRepairRequests({ sort: "status" });
    expect(managerList.data.length).toBeGreaterThan(0);

    const requesterId = managerList.data[0].requester_id;
    seedSession({
      id: requesterId,
      email: "holder@example.com",
      name: "Holder",
      role: "holder",
    });
    const holderList = backend.listRepairRequests();
    expect(holderList.data.every((item) => item.requester_id === requesterId)).toBe(true);
  });

  it("applies approve -> details -> complete flow with asset side effects", async () => {
    const backend = await loadBackend();
    seedSession({
      id: "mock-manager",
      email: "admin@example.com",
      name: "Admin Manager",
      role: "manager",
    });

    const pending = backend
      .listRepairRequests({ status: "pending_review", page: 1, perPage: 1 })
      .data[0];
    expect(pending).toBeTruthy();

    const approved = backend.approveRepairRequest(pending.id, {
      version: pending.version,
      repair_plan: "replace panel",
      repair_vendor: "Vendor",
      repair_cost: "2000",
      planned_date: "2026-04-20",
    });
    expect(approved.status).toBe("under_repair");

    const detailed = backend.updateRepairRequestDetails(approved.id, {
      version: approved.version,
      fault_content: "connector issue",
      repair_plan: "replace panel",
      repair_cost: "2500",
    });
    expect(detailed.fault_content).toBe("connector issue");

    const completed = backend.completeRepairRequest(approved.id, {
      version: detailed.version,
      repair_date: "2026-04-22",
      fault_content: "connector issue",
      repair_plan: "replace panel",
      repair_cost: "2500",
      repair_vendor: "Vendor",
    });
    expect(completed.status).toBe("completed");

    const asset = backend.getAssetById(completed.asset_id);
    expect(asset.status).toBe("in_use");
  });

  it("applies reject flow and invalid repair transitions", async () => {
    const backend = await loadBackend();
    seedSession({
      id: "mock-manager",
      email: "admin@example.com",
      name: "Admin Manager",
      role: "manager",
    });

    const pending = backend
      .listRepairRequests({ status: "pending_review", page: 1, perPage: 1 })
      .data[0];
    expect(pending).toBeTruthy();

    const rejected = backend.rejectRepairRequest(pending.id, {
      version: pending.version,
      rejection_reason: "not reproducible",
    });
    expect(rejected.status).toBe("rejected");

    expect(() =>
      backend.approveRepairRequest(rejected.id, {
        version: rejected.version,
      }),
    ).toThrow();

    const completed = backend
      .listRepairRequests({ status: "completed", page: 1, perPage: 1 })
      .data[0];
    expect(completed).toBeTruthy();

    expect(() =>
      backend.updateRepairRequestDetails(completed.id, {
        version: completed.version,
      }),
    ).toThrow();
  });

  it("guards repair request detail access for unrelated holders", async () => {
    const backend = await loadBackend();

    seedSession({
      id: "mock-manager",
      email: "admin@example.com",
      name: "Admin Manager",
      role: "manager",
    });
    const request = backend.listRepairRequests({ page: 1, perPage: 1 }).data[0];
    expect(request).toBeTruthy();

    seedSession({
      id: "unrelated-holder",
      email: "holder2@example.com",
      name: "Unrelated Holder",
      role: "holder",
    });

    expect(() => backend.getRepairRequestById(request.id)).toThrow();
  });
});
