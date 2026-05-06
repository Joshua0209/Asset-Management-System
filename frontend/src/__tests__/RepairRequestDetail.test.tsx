import { act, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import RepairRequestDetail from "../pages/RepairRequestDetail";
import i18n from "../i18n";
import type { RepairRequestRecord } from "../api/repair-requests/types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    repairRequestsApi: {
      getRepairRequestById: vi.fn(),
    },
  };
});

const apiModule = await import("../api");
const mockGetRepairRequestById = vi.mocked(apiModule.repairRequestsApi.getRepairRequestById);

const mockRequest = {
  id: "req-1",
  asset_id: "asset-1",
  requester_id: "user-1",
  reviewer_id: "mgr-1",
  asset: { id: "asset-1", asset_code: "AST-001", name: "MacBook Pro" },
  requester: { id: "user-1", name: "Alice Chen" },
  reviewer: { id: "mgr-1", name: "Manager Wang" },
  status: "completed" as const,
  fault_description: "Screen flicker",
  rejection_reason: null,
  repair_date: "2026-05-10",
  fault_content: "Loose cable",
  repair_plan: "Reseated cable",
  repair_cost: "500.00",
  repair_vendor: "Genius Bar",
  images: [
    { id: "img-1", url: "http://example.com/img1.jpg", uploaded_at: "2026-05-01T10:00:00Z" }
  ],
  completed_at: "2026-05-12T15:00:00Z",
  created_at: "2026-05-01T10:00:00Z",
  updated_at: "2026-05-12T15:00:00Z",
  version: 3,
};

describe("RepairRequestDetail", () => {
  beforeEach(async () => {
    mockGetRepairRequestById.mockReset();
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("renders repair request details and timeline", async () => {
    mockGetRepairRequestById.mockResolvedValueOnce(mockRequest as unknown as RepairRequestRecord);

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/repairs/req-1"]}>
          <Routes>
            <Route path="/repairs/:id" element={<RepairRequestDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText("Repair Request Details")).toBeInTheDocument();
    });

    expect(screen.getByText("MacBook Pro")).toBeInTheDocument();
    expect(screen.getByText("AST-001")).toBeInTheDocument();
    expect(screen.getByText("Screen flicker")).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);

    // Check result section (visible because status is completed)
    expect(screen.getByText("Genius Bar")).toBeInTheDocument();
    expect(screen.getByText("TWD 500.00")).toBeInTheDocument();
    expect(screen.getByText("Reseated cable")).toBeInTheDocument();
  });

  it("shows rejection reason when status is rejected", async () => {
    const rejectedRequest = {
      ...mockRequest,
      status: "rejected" as const,
      rejection_reason: "Cannot reproduce",
      completed_at: null,
    };
    mockGetRepairRequestById.mockResolvedValueOnce(rejectedRequest as unknown as RepairRequestRecord);

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/repairs/req-1"]}>
          <Routes>
            <Route path="/repairs/:id" element={<RepairRequestDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getAllByText("Rejected").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("Rejection Reason:")).toBeInTheDocument();
    expect(screen.getByText("Cannot reproduce")).toBeInTheDocument();
  });

  it("shows error alert when fetch fails", async () => {
    mockGetRepairRequestById.mockRejectedValueOnce(new Error("Not found"));

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/repairs/req-1"]}>
          <Routes>
            <Route path="/repairs/:id" element={<RepairRequestDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText("Something went wrong. Please try again later.")).toBeInTheDocument();
    });
  });
});
