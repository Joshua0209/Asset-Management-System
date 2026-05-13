import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import AssetDetail from "../pages/AssetDetail";
import i18n from "../i18n";
import { ApiError } from "../api";
import type { AssetRecord } from "../api/assets";
import { getModalField, getOpenModalContent, holderUser, managerUser } from "./test-helpers";

const mockGetAsset = vi.hoisted(() => vi.fn());
const mockListUsers = vi.hoisted(() => vi.fn());
const mockUpdateAsset = vi.hoisted(() => vi.fn());
const mockAssignAsset = vi.hoisted(() => vi.fn());
const mockUnassignAsset = vi.hoisted(() => vi.fn());
const mockDisposeAsset = vi.hoisted(() => vi.fn());
const mockApi = {
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
};

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    notification: {
      ...actual.notification,
      useNotification: () => [mockApi, null],
    },
  };
});

vi.mock("../auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../api", () => {
  class MockApiError extends Error {
    readonly status: number;
    readonly code: string;
    readonly details: Array<{ field: string; message: string; code: string }>;

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
  }

  return {
    ApiError: MockApiError,
    assetsApi: {
      getAssetById: mockGetAsset,
      updateAsset: mockUpdateAsset,
      assignAsset: mockAssignAsset,
      unassignAsset: mockUnassignAsset,
      disposeAsset: mockDisposeAsset,
    },
    usersApi: {
      listUsers: mockListUsers,
    },
  };
});

const authModule = await import("../auth/AuthContext");
const mockUseAuth = vi.mocked(authModule.useAuth);

type TestAuthUser = typeof holderUser | typeof managerUser;

function setAuthUser(user: TestAuthUser = holderUser): void {
  mockUseAuth.mockReturnValue({
    user,
    token: "token",
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

function renderAssetDetail(path = "/assets/AST-2026-00001-id") {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/assets/:id" element={<AssetDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

function buildAsset(overrides: Partial<AssetRecord> = {}): AssetRecord {
  return {
    ...mockAsset,
    ...overrides,
  };
}

function mockAssetReloadSequence(
  initialAsset: Partial<AssetRecord>,
  refreshedAsset: Partial<AssetRecord>,
): void {
  mockGetAsset.mockResolvedValueOnce(buildAsset(initialAsset)).mockResolvedValueOnce(buildAsset(refreshedAsset));
}

const mockAsset: AssetRecord = {
  id: "AST-2026-00001-id",
  asset_code: "AST-2026-00001",
  name: "Business Laptop 13",
  model: "Dell Latitude 7440",
  specs: "Intel Core i7, 16GB RAM, 512GB SSD",
  category: "computer",
  supplier: "Dell",
  purchase_date: "2026-01-01",
  purchase_amount: "42900.00",
  location: "Taipei HQ",
  department: "IT",
  activation_date: "2026-01-05",
  warranty_expiry: "2028-01-01",
  status: "in_use" as const,
  responsible_person_id: "holder-1",
  responsible_person: {
    id: "holder-1",
    name: "Alice Chen",
  },
  disposal_reason: null,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("AssetDetail", () => {
  beforeEach(async () => {
    mockGetAsset.mockReset();
    mockListUsers.mockReset();
    mockUpdateAsset.mockReset();
    mockAssignAsset.mockReset();
    mockUnassignAsset.mockReset();
    mockDisposeAsset.mockReset();
    mockApi.success.mockReset();
    mockApi.error.mockReset();
    setAuthUser(holderUser);
    mockUpdateAsset.mockResolvedValue({});
    mockAssignAsset.mockResolvedValue({});
    mockUnassignAsset.mockResolvedValue({});
    mockDisposeAsset.mockResolvedValue({});
    mockListUsers.mockResolvedValue({
      data: [
        { id: "holder-2", name: "Bob Lee", email: "bob@example.com", role: "holder" },
      ],
      meta: {
        total: 1,
        page: 1,
        per_page: 100,
        total_pages: 1,
      },
    });
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("shows manager action buttons on asset detail page", async () => {
    setAuthUser(managerUser);
    mockGetAsset.mockResolvedValueOnce(mockAsset);

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Unassign" })).toBeInTheDocument();
    });
  });

  it("loads and displays asset details", async () => {
    mockGetAsset.mockResolvedValueOnce(mockAsset);

    renderAssetDetail();

    await waitFor(() => {
      expect(mockGetAsset).toHaveBeenCalledWith("AST-2026-00001-id");
      expect(screen.getByText("Asset Detail - AST-2026-00001")).toBeInTheDocument();
    });

    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    expect(screen.getByText("Dell Latitude 7440")).toBeInTheDocument();
    expect(screen.getByText("Intel Core i7, 16GB RAM, 512GB SSD")).toBeInTheDocument();
    expect(screen.getByText("Dell")).toBeInTheDocument();
  });

  it("renders 404 when asset is not found", async () => {
    mockGetAsset.mockRejectedValueOnce(new ApiError(404, "not_found", "Not Found"));

    renderAssetDetail("/assets/unknown");

    await waitFor(() => {
      expect(screen.getByText("Asset not found")).toBeInTheDocument();
    });
  });

  it("renders 403 when access is forbidden", async () => {
    mockGetAsset.mockRejectedValueOnce(new ApiError(403, "forbidden", "Forbidden"));

    renderAssetDetail("/assets/AST-forbidden");

    await waitFor(() => {
      expect(screen.getByText("You do not have permission to view this asset")).toBeInTheDocument();
    });
  });

  it("hides manager action buttons for holder users", async () => {
    setAuthUser(holderUser);
    mockGetAsset.mockResolvedValueOnce(mockAsset);

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByText("Asset Detail - AST-2026-00001")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unassign" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dispose" })).not.toBeInTheDocument();
  });

  it("updates an asset from the edit modal", async () => {
    const user = userEvent.setup({ delay: null });
    setAuthUser(managerUser);
    mockGetAsset
      .mockResolvedValueOnce(buildAsset())
      .mockResolvedValueOnce(buildAsset({ name: "Updated Laptop" }));

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Edit" }));

    const editModal = getOpenModalContent();
    const nameInput = getModalField(editModal, "#name");
    await user.clear(nameInput);
    await user.type(nameInput, "Updated Laptop");
    await user.click(within(editModal).getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(mockUpdateAsset).toHaveBeenCalledWith(
        "AST-2026-00001-id",
        expect.objectContaining({
          version: 1,
          name: "Updated Laptop",
        }),
      );
    });
  });

  it("assigns an in-stock asset from detail page", async () => {
    const user = userEvent.setup({ delay: null });
    setAuthUser(managerUser);
    mockAssetReloadSequence(
      { status: "in_stock", responsible_person: null, responsible_person_id: null },
      { status: "in_use", responsible_person_id: "holder-2" },
    );

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Assign" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Assign" }));

    const assignModal = getOpenModalContent();
    await user.click(within(assignModal).getByRole("combobox", { name: "Holder" }));
    await user.click(screen.getByText("Bob Lee (bob@example.com)"));
    await user.type(getModalField(assignModal, "#assignment_date"), "2026-05-08");
    await user.click(within(assignModal).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(mockAssignAsset).toHaveBeenCalledWith("AST-2026-00001-id", {
        responsible_person_id: "holder-2",
        assignment_date: "2026-05-08",
        version: 1,
      });
    });
  });

  it("unassigns an in-use asset from detail page", async () => {
    const user = userEvent.setup({ delay: null });
    setAuthUser(managerUser);
    mockGetAsset
      .mockResolvedValueOnce(buildAsset({ status: "in_use" }))
      .mockResolvedValueOnce(buildAsset({ status: "in_stock", responsible_person: null, responsible_person_id: null }));

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Unassign" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Unassign" }));

    const unassignModal = getOpenModalContent();
    await user.type(getModalField(unassignModal, "#reason"), "Returned to IT");
    await user.click(within(unassignModal).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(mockUnassignAsset).toHaveBeenCalledWith("AST-2026-00001-id", {
        reason: "Returned to IT",
        version: 1,
      });
    });
  });

  it("disposes an in-stock asset from detail page", async () => {
    const user = userEvent.setup({ delay: null });
    setAuthUser(managerUser);
    mockAssetReloadSequence(
      { status: "in_stock", responsible_person: null, responsible_person_id: null },
      { status: "disposed" },
    );

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Dispose" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Dispose" }));

    const disposeModal = getOpenModalContent();
    await user.type(getModalField(disposeModal, "#disposal_reason"), "Lifecycle end");
    await user.click(within(disposeModal).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(mockDisposeAsset).toHaveBeenCalledWith("AST-2026-00001-id", {
        disposal_reason: "Lifecycle end",
        version: 1,
      });
    });
  });

  it("shows a warning modal on 409 conflict error and refreshes data", async () => {
    const user = userEvent.setup({ delay: null });
    setAuthUser(managerUser);
    mockGetAsset
      .mockResolvedValueOnce(buildAsset()) // Initial load
      .mockResolvedValueOnce(buildAsset({ version: 2 })); // Refresh load

    mockUpdateAsset.mockRejectedValueOnce(
      new ApiError(409, "conflict", "Conflict message")
    );

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Edit" }));

    const editModal = getOpenModalContent();
    await user.click(within(editModal).getByRole("button", { name: "Save" }));

    // Wait for the conflict dialog
    await waitFor(() => {
      expect(screen.getAllByText("Update Conflict")[0]).toBeInTheDocument();
    });

    // Dismiss the dialog
    await user.click(screen.getByRole("button", { name: "OK" }));

    // Verify refresh
    await waitFor(() => {
      expect(mockGetAsset).toHaveBeenCalledTimes(2);
    });
  });

  it("shows a generic error toast for other ApiErrors during update", async () => {
    const user = userEvent.setup({ delay: null });
    setAuthUser(managerUser);
    mockGetAsset.mockResolvedValue(buildAsset());

    mockUpdateAsset.mockRejectedValueOnce(
      new ApiError(400, "validation_error", "Bad request")
    );

    renderAssetDetail();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const editModal = getOpenModalContent();
    await user.click(within(editModal).getByRole("button", { name: "Save" }));

    // Verify error toast
    await waitFor(() => {
      expect(mockApi.error).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Action failed",
          description: "Invalid input",
        })
      );
    });
  });
});
