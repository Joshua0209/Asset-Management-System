import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "@/pages/manager/Dashboard";
import i18n from "@/i18n";
import { ApiError } from "@/api";
import type { ManagerDashboard } from "@/api/dashboard";

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
  return {
    ...actual,
    dashboardApi: {
      getManagerDashboard: vi.fn(),
    },
  };
});

const apiModule = await import("@/api");
const mockGetManagerDashboard = vi.mocked(apiModule.dashboardApi.getManagerDashboard);

function buildPayload(overrides: Partial<ManagerDashboard> = {}): ManagerDashboard {
  return {
    kpis: {
      total_assets: 10,
      in_stock_assets: 2,
      in_use_assets: 5,
      pending_repair_assets: 1,
      under_repair_assets: 1,
      pending_repair_requests: 1,
    },
    asset_categories: [
      { category: "computer", count: 4 },
      { category: "monitor", count: 2 },
    ],
    repair_summary: {
      created_today: 1,
      pending_review: 1,
      under_repair: 1,
      completed_today: 0,
    },
    recent_pending_repairs: [
      {
        id: "rr-uuid-1",
        repair_id: "REP-2026-00041",
        asset_id: "asset-uuid-1",
        asset_name: "MacBook Pro 14",
        requester_name: "Alice",
        status: "pending_review",
        created_at: "2026-05-26T10:30:00+00:00",
      },
    ],
    ...overrides,
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

describe("Dashboard", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    if (i18n.language !== "en") {
      await i18n.changeLanguage("en");
    }
  });

  it("renders skeleton during initial load", async () => {
    let resolvePayload: (value: { data: ManagerDashboard; isMock: boolean }) => void;
    mockGetManagerDashboard.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePayload = resolve;
      }),
    );
    const { container } = renderDashboard();
    expect(container.querySelector(".ant-skeleton")).toBeInTheDocument();
    resolvePayload!({ data: buildPayload(), isMock: false });
    await waitFor(() => {
      expect(container.querySelector(".ant-skeleton")).not.toBeInTheDocument();
    });
  });

  it("renders the six KPI cards with values from the API", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({ data: buildPayload(), isMock: false });
    renderDashboard();
    await screen.findByText("Total assets");
    expect(screen.getByText("In stock")).toBeInTheDocument();
    expect(screen.getByText("In use")).toBeInTheDocument();
    expect(screen.getByText("Pending repair")).toBeInTheDocument();
    expect(screen.getByText("Under repair")).toBeInTheDocument();
    // pendingReview appears twice (KPI + summary card) — assert there are at least two
    expect(screen.getAllByText("Pending review").length).toBeGreaterThanOrEqual(2);
  });

  it("shows the empty state for asset categories when none exist", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({
      data: buildPayload({ asset_categories: [] }),
      isMock: false,
    });
    renderDashboard();
    expect(await screen.findByText("No active assets yet.")).toBeInTheDocument();
  });

  it("shows the empty state for recent pending repairs when none exist", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({
      data: buildPayload({ recent_pending_repairs: [] }),
      isMock: false,
    });
    renderDashboard();
    expect(await screen.findByText("No pending review requests.")).toBeInTheDocument();
  });

  it("renders the error alert with a retry button that reloads on click", async () => {
    mockGetManagerDashboard
      .mockRejectedValueOnce(
        new ApiError(
          503,
          "dashboard_unavailable",
          "Unable to load dashboard. Please try again later.",
        ),
      )
      .mockResolvedValueOnce({ data: buildPayload(), isMock: false });
    renderDashboard();
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(mockGetManagerDashboard).toHaveBeenCalledTimes(1);
    await userEvent.click(retry);
    await waitFor(() => {
      expect(mockGetManagerDashboard).toHaveBeenCalledTimes(2);
    });
    await screen.findByText("Total assets");
  });

  it("navigates to /reviews/<id> when a recent pending row is clicked", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({ data: buildPayload(), isMock: false });
    renderDashboard();
    const row = await screen.findByText("REP-2026-00041");
    await userEvent.click(row);
    expect(mockNavigate).toHaveBeenCalledWith("/reviews/rr-uuid-1");
  });

  it("does not navigate when the pending row is missing its UUID id", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({
      data: buildPayload({
        recent_pending_repairs: [
          {
            id: "",
            repair_id: "REP-NO-ID",
            asset_id: "asset-x",
            asset_name: "Asset X",
            requester_name: "Carol",
            status: "pending_review",
            created_at: "2026-05-26T10:30:00+00:00",
          },
        ],
      }),
      isMock: false,
    });
    renderDashboard();
    const row = await screen.findByText("REP-NO-ID");
    await userEvent.click(row);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("deep-links 'View all' to the pending-review filtered Reviews page", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({ data: buildPayload(), isMock: false });
    renderDashboard();
    const viewAll = await screen.findByRole("button", { name: "View all" });
    await userEvent.click(viewAll);
    expect(mockNavigate).toHaveBeenCalledWith("/reviews?status=pending_review");
  });

  it("renders the mock-data banner when isMock is true", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({ data: buildPayload(), isMock: true });
    renderDashboard();
    expect(await screen.findByText("Mock data")).toBeInTheDocument();
  });

  it("hides the mock-data banner under normal API responses", async () => {
    mockGetManagerDashboard.mockResolvedValueOnce({ data: buildPayload(), isMock: false });
    renderDashboard();
    await screen.findByText("Total assets");
    expect(screen.queryByText("Mock data")).not.toBeInTheDocument();
  });
});
