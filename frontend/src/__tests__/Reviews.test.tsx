import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import Reviews from "../pages/Reviews";
import i18n from "../i18n";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    repairRequestsApi: {
      listRepairRequests: vi.fn(),
      approveRepairRequest: vi.fn(),
      rejectRepairRequest: vi.fn(),
      updateRepairRequestDetails: vi.fn(),
      completeRepairRequest: vi.fn(),
    },
  };
});

const apiModule = await import("../api");
const mockListRepairRequests = vi.mocked(apiModule.repairRequestsApi.listRepairRequests);
const mockApproveRepairRequest = vi.mocked(apiModule.repairRequestsApi.approveRepairRequest);
const mockRejectRepairRequest = vi.mocked(apiModule.repairRequestsApi.rejectRepairRequest);
const mockUpdateRepairRequestDetails = vi.mocked(
  apiModule.repairRequestsApi.updateRepairRequestDetails,
);
const mockCompleteRepairRequest = vi.mocked(apiModule.repairRequestsApi.completeRepairRequest);

function buildResponse(status: "pending_review" | "under_repair") {
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
    mockApproveRepairRequest.mockReset();
    mockRejectRepairRequest.mockReset();
    mockUpdateRepairRequestDetails.mockReset();
    mockCompleteRepairRequest.mockReset();
    mockListRepairRequests.mockResolvedValue(buildResponse("pending_review"));
    mockApproveRepairRequest.mockResolvedValue({} as never);
    mockRejectRepairRequest.mockResolvedValue({} as never);
    mockUpdateRepairRequestDetails.mockResolvedValue({} as never);
    mockCompleteRepairRequest.mockResolvedValue({} as never);
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

  it("approves a pending request with repair plan payload", async () => {
    const user = userEvent.setup({ delay: null });
    mockListRepairRequests
      .mockResolvedValueOnce(buildResponse("pending_review"))
      .mockResolvedValueOnce(buildResponse("under_repair"));

    await act(async () => {
      render(<Reviews />);
    });

    await waitFor(() => expect(screen.getByText("Approve")).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Approve" }));
    });

    await act(async () => {
      await user.type(screen.getByLabelText("Repair Plan"), "Replace panel");
      await user.type(screen.getByLabelText("Repair Vendor"), "Vendor A");
      await user.type(screen.getByLabelText("Repair Cost"), "2200");
      await user.type(screen.getByLabelText("Planned Date"), "2026-04-25");
      const approveButtons = screen.getAllByRole("button", { name: "Approve" });
      await user.click(approveButtons[approveButtons.length - 1]);
    });

    await waitFor(() => {
      expect(mockApproveRepairRequest).toHaveBeenCalledWith("rr-1", {
        version: 1,
        repair_plan: "Replace panel",
        repair_vendor: "Vendor A",
        repair_cost: "2200",
        planned_date: "2026-04-25",
      });
    });
  });

  it("rejects a pending request with reason", async () => {
    const user = userEvent.setup({ delay: null });
    mockListRepairRequests
      .mockResolvedValueOnce(buildResponse("pending_review"))
      .mockResolvedValueOnce(buildResponse("pending_review"));

    await act(async () => {
      render(<Reviews />);
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Reject" }));
    });

    await act(async () => {
      await user.type(screen.getByLabelText("Rejection Reason"), "Not reproducible");
      const rejectButtons = screen.getAllByRole("button", { name: "Reject" });
      await user.click(rejectButtons[rejectButtons.length - 1]);
    });

    await waitFor(() => {
      expect(mockRejectRepairRequest).toHaveBeenCalledWith("rr-1", {
        version: 1,
        rejection_reason: "Not reproducible",
      });
    });
  });

  it("updates repair details and completes under-repair request", async () => {
    const user = userEvent.setup({ delay: null });
    mockListRepairRequests
      .mockResolvedValueOnce(buildResponse("under_repair"))
      .mockResolvedValueOnce(buildResponse("under_repair"))
      .mockResolvedValueOnce(buildResponse("under_repair"));

    await act(async () => {
      render(<Reviews />);
    });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Update Details" })).toBeInTheDocument(),
    );

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Update Details" }));
    });

    await act(async () => {
      await user.type(screen.getByLabelText("Fault Content"), "Connector issue");
      await user.type(screen.getByLabelText("Repair Plan"), "Reseat connector");
      await user.type(screen.getByLabelText("Repair Cost"), "1500");
      await user.type(screen.getByLabelText("Repair Vendor"), "Vendor B");
      await user.click(screen.getByRole("button", { name: "Save" }));
    });

    await waitFor(() => {
      expect(mockUpdateRepairRequestDetails).toHaveBeenCalledWith(
        "rr-1",
        expect.objectContaining({
          version: 1,
          fault_content: expect.stringContaining("Connector issue"),
        }),
      );
    });

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Complete" }));
    });

    await act(async () => {
      await user.type(screen.getByLabelText("Repair Date"), "2026-04-28");
      await user.type(screen.getByLabelText("Fault Content"), "Resolved");
      await user.type(screen.getByLabelText("Repair Plan"), "Replaced part");
      await user.type(screen.getByLabelText("Repair Cost"), "1800");
      await user.type(screen.getByLabelText("Repair Vendor"), "Vendor C");
      const completeButtons = screen.getAllByRole("button", { name: "Complete" });
      await user.click(completeButtons[completeButtons.length - 1]);
    });

    await waitFor(() => {
      expect(mockCompleteRepairRequest).toHaveBeenCalledWith(
        "rr-1",
        expect.objectContaining({
          version: 1,
          repair_vendor: expect.stringContaining("Vendor C"),
        }),
      );
    });
  });
});
