import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import MyAssetList from "../pages/MyAssetList";
import i18n from "../i18n";
import { holderUser, buildAssetResponse } from "./test-helpers";

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

describe("MyAssetList", () => {
  beforeEach(async () => {
    mockListMyAssets.mockReset();
    await i18n.changeLanguage("en");
    mockUseAuth.mockReturnValue({
      user: holderUser,
      token: "token",
      isAuthenticated: true,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  it("loads only current holder assets for holder role", async () => {
    mockListMyAssets.mockResolvedValueOnce(buildAssetResponse("AST-2026-00001", "Business Laptop 13", 1));

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyAssetList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockListMyAssets).toHaveBeenCalledWith({ page: 1, perPage: 5 });
    });
    expect(screen.getByText("Showing 1 assets")).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
  });
});
