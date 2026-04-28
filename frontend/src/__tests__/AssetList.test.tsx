import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AssetList from "../pages/AssetList";
import i18n from "../i18n";

describe("AssetList", () => {
  beforeEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("renders dummy assets in table", async () => {
    await act(async () => {
      render(<AssetList />);
    });

    expect(screen.getByRole("heading", { name: "Asset List" })).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    expect(screen.getByText("Business Laptop 13")).toBeInTheDocument();
    expect(screen.getByText("Showing 18 assets")).toBeInTheDocument();
  });

  it("changes table page when pagination is clicked", async () => {
    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByTitle("2"));
    });

    await waitFor(() => {
      expect(screen.getByText("AST-2026-00006")).toBeInTheDocument();
    });
  });

  it("filters assets in holder mode", async () => {
    const user = userEvent.setup();
    await act(async () => {
      render(<AssetList />);
    });

    await act(async () => {
      await user.click(screen.getByText("Holder"));
    });

    await waitFor(() => {
      expect(screen.getByText("Showing 5 assets")).toBeInTheDocument();
    });

    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    expect(screen.queryByText("AST-2026-00002")).not.toBeInTheDocument();
  });

  it("opens detail modal and shows extended asset fields", async () => {
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
});
