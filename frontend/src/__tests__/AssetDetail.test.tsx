import { act, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import AssetDetail from "../pages/AssetDetail";
import i18n from "../i18n";
import { ApiError } from "../api";

const mockGetAsset = vi.hoisted(() => vi.fn());
const mockListUsers = vi.hoisted(() => vi.fn());

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
    },
      usersApi: {
        listUsers: mockListUsers,
      },
  };
});

const authModule = await import("../auth/AuthContext");
const mockUseAuth = vi.mocked(authModule.useAuth);

const mockAsset = {
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
    mockUseAuth.mockReturnValue({
      user: {
        id: "holder-1",
        email: "holder@example.com",
        name: "Holder",
        role: "holder",
      },
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("shows manager action buttons on asset detail page", async () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "manager-1",
        email: "manager@example.com",
        name: "Manager",
        role: "manager",
      },
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
    mockGetAsset.mockResolvedValueOnce(mockAsset);
    mockListUsers.mockResolvedValueOnce({
      data: [],
      meta: {
        total: 0,
        page: 1,
        per_page: 100,
        total_pages: 0,
      },
    });

    await act(async () => {
      render(
        <MemoryRouter
          initialEntries={["/assets/AST-2026-00001-id"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route path="/assets/:id" element={<AssetDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Unassign" })).toBeInTheDocument();
    });
  });

  it("loads and displays asset details", async () => {
    mockGetAsset.mockResolvedValueOnce(mockAsset);

    await act(async () => {
      render(
        <MemoryRouter
          initialEntries={["/assets/AST-2026-00001-id"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route path="/assets/:id" element={<AssetDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

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

    await act(async () => {
      render(
        <MemoryRouter
          initialEntries={["/assets/unknown"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route path="/assets/:id" element={<AssetDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText("Asset not found")).toBeInTheDocument();
    });
  });

  it("renders 403 when access is forbidden", async () => {
    mockGetAsset.mockRejectedValueOnce(new ApiError(403, "forbidden", "Forbidden"));

    await act(async () => {
      render(
        <MemoryRouter
          initialEntries={["/assets/AST-forbidden"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route path="/assets/:id" element={<AssetDetail />} />
          </Routes>
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(screen.getByText("You do not have permission to view this asset")).toBeInTheDocument();
    });
  });
});
