import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import AssetList from "../pages/AssetList";
import i18n from "../i18n";

vi.mock("../auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    assetsApi: {
      listAssets: vi.fn(),
      listMyAssets: vi.fn(),
      createAsset: vi.fn(),
      updateAsset: vi.fn(),
      assignAsset: vi.fn(),
      unassignAsset: vi.fn(),
      disposeAsset: vi.fn(),
    },
    usersApi: {
      listUsers: vi.fn(),
    },
  };
});

const authModule = await import("../auth/AuthContext");
const apiModule = await import("../api");

const mockUseAuth = vi.mocked(authModule.useAuth);
const mockListAssets = vi.mocked(apiModule.assetsApi.listAssets);
const mockListMyAssets = vi.mocked(apiModule.assetsApi.listMyAssets);
const mockUpdateAsset = vi.mocked(apiModule.assetsApi.updateAsset);
const mockUnassignAsset = vi.mocked(apiModule.assetsApi.unassignAsset);
const mockDisposeAsset = vi.mocked(apiModule.assetsApi.disposeAsset);
const mockListUsers = vi.mocked(apiModule.usersApi.listUsers);

const managerUser = {
  id: "manager-1",
  email: "manager@example.com",
  name: "Manager",
  role: "manager" as const,
};

const holderUser = {
  id: "holder-1",
  email: "holder@example.com",
  name: "Holder",
  role: "holder" as const,
};

function buildResponse(
  assetCode: string,
  assetName: string,
  total: number,
  status: "in_stock" | "in_use" = "in_use",
) {
  return {
    data: [
      {
        id: `${assetCode}-id`,
        asset_code: assetCode,
        name: assetName,
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
        status,
        responsible_person_id: "holder-1",
        responsible_person: {
          id: "holder-1",
          name: "Alice Chen",
        },
        disposal_reason: null,
        version: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    meta: {
      total,
      page: 1,
      per_page: 5,
      total_pages: 2,
    },
  };
}

describe("AssetList", () => {
  beforeEach(async () => {
    mockListAssets.mockReset();
    mockListMyAssets.mockReset();
    mockUpdateAsset.mockReset();
    mockUnassignAsset.mockReset();
    mockDisposeAsset.mockReset();
    mockListUsers.mockReset();
    mockUpdateAsset.mockResolvedValue(undefined as never);
    mockUnassignAsset.mockResolvedValue(undefined as never);
    mockDisposeAsset.mockResolvedValue(undefined as never);
    mockListUsers.mockResolvedValue({
      data: [],
      meta: {
        total: 0,
        page: 1,
        per_page: 20,
        total_pages: 0,
      },
    });
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("loads all assets for manager without role switch controls", async () => {
    mockUseAuth.mockReturnValue({
      user: managerUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockListAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 10));

    await act(async () => {
      render(<AssetList />);
    });

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenCalledWith({ page: 1, perPage: 5 });
    });
    expect(mockListMyAssets).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Asset List" })).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    expect(screen.getByText("Business Laptop 13")).toBeInTheDocument();
    expect(screen.getByText("Showing 10 assets")).toBeInTheDocument();
    expect(screen.queryByText("View Mode")).not.toBeInTheDocument();
    expect(screen.queryByText("Holder")).not.toBeInTheDocument();
  });

  it("changes table page when pagination is clicked", async () => {
    mockUseAuth.mockReturnValue({
      user: managerUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockListAssets
      .mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 10))
      .mockResolvedValueOnce(buildResponse("AST-2026-00006", "Field Laptop", 10));

    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    await waitFor(() => {
      expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    });

    await act(async () => {
      await user.click(screen.getByTitle("2"));
    });

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenLastCalledWith({ page: 2, perPage: 5 });
      expect(screen.getByText("AST-2026-00006")).toBeInTheDocument();
    });
  });

  it("loads only current holder assets for holder role", async () => {
    mockUseAuth.mockReturnValue({
      user: holderUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockListMyAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 1));

    await act(async () => {
      render(<AssetList />);
    });

    await waitFor(() => {
      expect(mockListMyAssets).toHaveBeenCalledWith({ page: 1, perPage: 5 });
    });
    expect(mockListAssets).not.toHaveBeenCalled();
    expect(screen.getByText("Showing 1 assets")).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
  });

  it("opens detail modal and shows extended asset fields", async () => {
    mockUseAuth.mockReturnValue({
      user: managerUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockListAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 1));

    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    await act(async () => {
      await user.click(screen.getAllByRole("button", { name: "Detail" })[0]);
    });

    await waitFor(() => {
      expect(screen.getByText("Asset Detail - AST-2026-00001")).toBeInTheDocument();
    });

    expect(screen.getByText("Alice Chen")).toBeInTheDocument();
    expect(screen.getByText("Dell Latitude 7440")).toBeInTheDocument();
    expect(screen.getByText("Intel Core i7, 16GB RAM, 512GB SSD")).toBeInTheDocument();
    expect(screen.getByText("Dell")).toBeInTheDocument();
  });

  it("edits an asset and submits update via API", async () => {
    mockUseAuth.mockReturnValue({
      user: managerUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    const initial = buildResponse("AST-2026-00001", "Business Laptop 13", 1, "in_use");
    const afterSave = buildResponse("AST-2026-00001", "Updated Laptop", 1, "in_use");
    mockListAssets.mockResolvedValueOnce(initial).mockResolvedValueOnce(afterSave);

    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    await waitFor(() => expect(screen.getByText("Business Laptop 13")).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Edit" }));
    });

    const nameInput = screen.getByLabelText("Name");
    await act(async () => {
      await user.clear(nameInput);
      await user.type(nameInput, "Updated Laptop");
      await user.click(screen.getByRole("button", { name: "Save" }));
    });

    await waitFor(() => {
      expect(mockUpdateAsset).toHaveBeenCalledWith(
        "AST-2026-00001-id",
        expect.objectContaining({
          name: "Updated Laptop",
          version: 1,
        }),
      );
    });
  });

  it("unassigns an in-use asset through manager action", async () => {
    mockUseAuth.mockReturnValue({
      user: managerUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    const initial = buildResponse("AST-2026-00001", "Business Laptop 13", 1, "in_use");
    const afterAction = buildResponse("AST-2026-00001", "Business Laptop 13", 1, "in_stock");
    mockListAssets.mockResolvedValueOnce(initial).mockResolvedValueOnce(afterAction);

    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    await waitFor(() => expect(screen.getByText("Business Laptop 13")).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Unassign" }));
    });

    const reasonInput = screen.getByLabelText("Unassign Reason");
    await act(async () => {
      await user.type(reasonInput, "Reclaim for reallocation");
      await user.click(screen.getByRole("button", { name: "Confirm" }));
    });

    await waitFor(() => {
      expect(mockUnassignAsset).toHaveBeenCalledWith("AST-2026-00001-id", {
        reason: "Reclaim for reallocation",
        version: 1,
      });
    });
  });

  it("disposes an in-stock asset through manager action", async () => {
    mockUseAuth.mockReturnValue({
      user: managerUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    const initial = buildResponse("AST-2026-00099", "Spare Tablet", 1, "in_stock");
    const afterAction = buildResponse("AST-2026-00099", "Spare Tablet", 1, "disposed");
    mockListAssets.mockResolvedValueOnce(initial).mockResolvedValueOnce(afterAction);

    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    await waitFor(() => expect(screen.getByText("Spare Tablet")).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Dispose" }));
    });

    await act(async () => {
      await user.type(screen.getByLabelText("Disposal Reason"), "End of life");
      await user.click(screen.getByRole("button", { name: "Confirm" }));
    });

    await waitFor(() => {
      expect(mockDisposeAsset).toHaveBeenCalledWith("AST-2026-00099-id", {
        disposal_reason: "End of life",
        version: 1,
      });
    });
  });
});
