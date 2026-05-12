import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import RepairRequestList from "../pages/RepairRequestList";
import i18n from "../i18n";
import type { PaginatedRepairRequestResponse } from "../api/repair-requests/types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    repairRequestsApi: {
      listRepairRequests: vi.fn(),
    },
  };
});

const apiModule = await import("../api");
const mockListRepairRequests = vi.mocked(apiModule.repairRequestsApi.listRepairRequests);

const mockRequests = {
  data: [
    {
      id: "req-1",
      asset: { name: "MacBook Pro", asset_code: "AST-001" },
      status: "pending_review" as const,
      created_at: "2026-05-01T10:00:00Z",
    },
    {
      id: "req-2",
      asset: { name: "Dell Monitor", asset_code: "AST-002" },
      status: "completed" as const,
      created_at: "2026-05-02T11:00:00Z",
    },
  ],
  meta: {
    total: 2,
    page: 1,
    per_page: 20,
    total_pages: 1,
  },
};

describe("RepairRequestList", () => {
  beforeEach(async () => {
    mockListRepairRequests.mockReset();
    await i18n.changeLanguage("en");
  });

  it("renders the list of repair requests", async () => {
    mockListRepairRequests.mockResolvedValueOnce(mockRequests as PaginatedRepairRequestResponse);

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RepairRequestList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("My Repair Requests")).toBeInTheDocument();
    });

    expect(screen.getByText("MacBook Pro")).toBeInTheDocument();
    expect(screen.getByText("AST-001")).toBeInTheDocument();
    expect(screen.getByText("Pending Review")).toBeInTheDocument();

    expect(screen.getByText("Dell Monitor")).toBeInTheDocument();
    expect(screen.getByText("AST-002")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("shows error alert when fetch fails", async () => {
    mockListRepairRequests.mockRejectedValueOnce(new Error("Failed to load"));

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RepairRequestList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Something went wrong. Please try again later.")).toBeInTheDocument();
    });
  });
});
