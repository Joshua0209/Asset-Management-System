import { act, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import MyAssetList from "../pages/MyAssetList";
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
    },
  };
});

const authModule = await import("../auth/AuthContext");
const apiModule = await import("../api");

const mockUseAuth = vi.mocked(authModule.useAuth);
const mockListMyAssets = vi.mocked(apiModule.assetsApi.listMyAssets);

const holderUser = {
  id: "holder-1",
  email: "holder@example.com",
  name: "Holder",
  role: "holder" as const,
};

function buildResponse(assetCode: string, assetName: string, total: number) {
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
      },
    ],
    meta: {
      total,
      page: 1,
      per_page: 5,
      total_pages: 1,
    },
  };
}

describe("MyAssetList", () => {
  beforeEach(async () => {
    mockListMyAssets.mockReset();
    await act(async () => {
      await i18n.changeLanguage("en");
    });
    mockUseAuth.mockReturnValue({
      user: holderUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("loads only current holder assets for holder role", async () => {
    mockListMyAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 1));

    await act(async () => {
      render(
        <MemoryRouter>
          <MyAssetList />
        </MemoryRouter>
      );
    });

    await waitFor(() => {
      expect(mockListMyAssets).toHaveBeenCalledWith({ page: 1, perPage: 5 });
    });
    expect(screen.getByText("Showing 1 assets")).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
  });
});
