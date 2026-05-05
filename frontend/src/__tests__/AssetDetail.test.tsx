import { act, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import AssetDetail from "../pages/AssetDetail";
import i18n from "../i18n";
import { ApiError } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    assetsApi: {
      getAssetById: vi.fn(),
    },
  };
});

const apiModule = await import("../api");
const mockGetAsset = vi.mocked(apiModule.assetsApi.getAssetById);

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
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("loads and displays asset details", async () => {
    mockGetAsset.mockResolvedValueOnce(mockAsset);

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/assets/AST-2026-00001-id"]}>
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
    mockGetAsset.mockRejectedValueOnce(new ApiError(404, "Not Found"));

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/assets/unknown"]}>
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
    mockGetAsset.mockRejectedValueOnce(new ApiError(403, "Forbidden"));

    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/assets/AST-forbidden"]}>
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
