import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import Reviews from "../pages/Reviews";
import i18n from "../i18n";
import { getModalField, getOpenModalContent } from "./test-helpers";

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
    await i18n.changeLanguage("en");
  });

  it("renders repair list and status badge", async () => {
    render(<Reviews />);

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

    render(<Reviews />);

    await waitFor(() => {
      expect(screen.getByText("AST-1")).toBeInTheDocument();
    });

    mockListRepairRequests.mockResolvedValueOnce(buildResponse("under_repair"));

    const [statusFilterCombobox] = screen.getAllByRole("combobox");
    await user.click(statusFilterCombobox);
    await user.click(screen.getByText("Under Repair"));

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

    render(<Reviews />);

    await waitFor(() => expect(screen.getByText("AST-1")).toBeInTheDocument());

    const row = screen.getByText("AST-1").closest("tr");
    expect(row).not.toBeNull();
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(screen.getByText("Approve Repair Request")).toBeInTheDocument();
    });

    const approveModal = getOpenModalContent();
    await user.type(getModalField(approveModal, "#repair_plan"), "Replace panel");
    await user.type(getModalField(approveModal, "#repair_vendor"), "Vendor A");
    await user.type(getModalField(approveModal, "#repair_cost"), "2200");
    await user.type(getModalField(approveModal, "#planned_date"), "2026-04-25");
    await user.click(within(approveModal).getByRole("button", { name: "Approve" }));

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

    render(<Reviews />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => {
      expect(screen.getByText("Reject Repair Request")).toBeInTheDocument();
    });

    const rejectModal = getOpenModalContent();
    await user.type(getModalField(rejectModal, "#rejection_reason"), "Not reproducible");
    await user.click(within(rejectModal).getByRole("button", { name: "Reject" }));

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

    render(<Reviews />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Update Details" })).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Update Details" }));

    await waitFor(() => {
      expect(screen.getByText("Update Repair Details")).toBeInTheDocument();
    });

    const detailsModal = getOpenModalContent();
    await user.type(getModalField(detailsModal, "#fault_content"), "Connector issue");
    await user.type(getModalField(detailsModal, "#repair_plan"), "Reseat connector");
    await user.type(getModalField(detailsModal, "#repair_cost"), "1500");
    await user.type(getModalField(detailsModal, "#repair_vendor"), "Vendor B");
    await user.click(within(detailsModal).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mockUpdateRepairRequestDetails).toHaveBeenCalledWith(
        "rr-1",
        expect.objectContaining({
          version: 1,
          fault_content: expect.stringContaining("Connector issue"),
        }),
      );
    });

    const row = screen.getByText("AST-1").closest("tr");
    expect(row).not.toBeNull();
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Complete" }));

    await waitFor(() => {
      expect(screen.getByText("Complete Repair")).toBeInTheDocument();
    });

    const completeModal = getOpenModalContent();
    await user.type(getModalField(completeModal, "#repair_date"), "2026-04-28");
    await user.type(getModalField(completeModal, "#fault_content"), "Resolved");
    await user.type(getModalField(completeModal, "#repair_plan"), "Replaced part");
    await user.type(getModalField(completeModal, "#repair_cost"), "1800");
    await user.type(getModalField(completeModal, "#repair_vendor"), "Vendor C");
    await user.click(within(completeModal).getByRole("button", { name: "Complete" }));

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
