import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import Reviews from "../pages/Reviews";
import i18n from "../i18n";

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

function buildResponse(
  status: "pending_review" | "under_repair" | "completed" | "rejected",
) {
  return {
    data: [
      {
        id: "rr-1",
        asset_id: "asset-1",
        requester_id: "holder-1",
        reviewer_id: null,
        status,
        fault_description: "screen flickers",
        repair_date: null,
        fault_content: null,
        repair_plan: null,
        repair_cost: null,
        repair_vendor: null,
        rejection_reason: null,
        completed_at: null,
        created_at: "2026-04-01T00:00:00Z",
        updated_at: "2026-04-01T00:00:00Z",
        version: 1,
        asset: { id: "asset-1", asset_code: "AST-1", name: "Laptop" },
        requester: { id: "holder-1", name: "Holder" },
        reviewer: null,
        images: [],
      },
    ],
    meta: {
      total: 1,
      page: 1,
      per_page: 5,
      total_pages: 1,
    },
  };
}

describe("Reviews", () => {
  beforeEach(async () => {
    mockListRepairRequests.mockReset();
    mockNavigate.mockReset();
    mockListRepairRequests.mockResolvedValue(buildResponse("pending_review"));
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("renders repair list and status badge", async () => {
    await act(async () => {
      render(<Reviews />);
    });

    await waitFor(() => {
      expect(mockListRepairRequests).toHaveBeenCalledWith({
        page: 1,
        perPage: 5,
        status: undefined,
      });
    });

    expect(screen.getByRole("heading", { name: "Repair Reviews" })).toBeInTheDocument();
    expect(screen.getByText("AST-1")).toBeInTheDocument();
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
  });

  it("navigates to full-page review details", async () => {
    const user = userEvent.setup({ delay: null });
    mockListRepairRequests.mockResolvedValueOnce(buildResponse("completed"));

    await act(async () => {
      render(<Reviews />);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Detail" })).toBeInTheDocument();
    });

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Detail" }));
    });

    expect(mockNavigate).toHaveBeenCalledWith("/reviews/rr-1");
  });

  it("applies status filter and reloads list", async () => {
    const user = userEvent.setup({ delay: null });

    await act(async () => {
      render(<Reviews />);
    });

    await waitFor(() => {
      expect(screen.getByText("AST-1")).toBeInTheDocument();
    });

    mockListRepairRequests.mockResolvedValueOnce(buildResponse("under_repair"));

    const [statusFilterCombobox] = screen.getAllByRole("combobox");
    await act(async () => {
      await user.click(statusFilterCombobox);
    });
    await act(async () => {
      await user.click(screen.getByText("Under Repair"));
    });

    await waitFor(() => {
      expect(mockListRepairRequests).toHaveBeenLastCalledWith({
        page: 1,
        perPage: 5,
        status: "under_repair",
      });
    });
  });
});
