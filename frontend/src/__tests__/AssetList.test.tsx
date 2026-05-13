import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import AssetList from "../pages/AssetList";
import i18n from "../i18n";
import type { AssetRecord } from "../api/assets";
import { getOpenModalContent } from "./test-helpers";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

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
const mockCreateAsset = vi.mocked(apiModule.assetsApi.createAsset);
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

function buildHolder(id: string, name: string, department = "IT") {
  return {
    id,
    email: `${id}@example.com`,
    name,
    role: "holder" as const,
    department,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function authAs(user: typeof managerUser | typeof holderUser) {
  mockUseAuth.mockReturnValue({
    user,
    token: "token",
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

async function renderAsManagerWith(...responses: ReturnType<typeof buildResponse>[]) {
  authAs(managerUser);
  mockListUsers.mockResolvedValue({
    data: [buildHolder("holder-1", "Alice Chen")],
    meta: { total: 1, page: 1, per_page: 100, total_pages: 1 },
  });
  responses.forEach((r) => mockListAssets.mockResolvedValueOnce(r));
  const user = userEvent.setup({ delay: null });
  render(<AssetList />);
  await waitFor(() => expect(screen.getByText(responses[0].data[0].name)).toBeInTheDocument());
  return user;
}

async function selectOption(
  user: ReturnType<typeof userEvent.setup>,
  testId: string,
  optionName: string,
) {
  const control = screen.getByTestId(testId);
  const selector = control.querySelector<HTMLElement>(".ant-select-selector");

  fireEvent.mouseDown(selector ?? control);

  const dropdown = Array.from(document.querySelectorAll<HTMLElement>(".ant-select-dropdown")).find(
    (element) => !element.className.includes("ant-select-dropdown-hidden"),
  );

  if (!dropdown) {
    throw new Error(`Expected an open dropdown for ${testId}, but none was found.`);
  }

  const option = Array.from(dropdown.querySelectorAll<HTMLElement>(".ant-select-item-option")).find(
    (element) => element.getAttribute("title") === optionName || element.textContent?.trim() === optionName,
  );

  if (!option) {
    throw new Error(`Expected option ${optionName} in dropdown ${testId}, but none was found.`);
  }

  await user.click(option);
}

function buildAsset(overrides: Partial<AssetRecord> = {}): AssetRecord {
  return {
    id: overrides.id ?? "asset-1",
    asset_code: overrides.asset_code ?? "AST-2026-00001",
    name: overrides.name ?? "Business Laptop 13",
    model: overrides.model ?? "Dell Latitude 7440",
    specs: overrides.specs ?? "Intel Core i7, 16GB RAM, 512GB SSD",
    category: overrides.category ?? "computer",
    supplier: overrides.supplier ?? "Dell",
    purchase_date: overrides.purchase_date ?? "2026-01-01",
    purchase_amount: overrides.purchase_amount ?? "42900.00",
    location: overrides.location ?? "Taipei HQ",
    department: overrides.department ?? "IT",
    activation_date: overrides.activation_date ?? "2026-01-05",
    warranty_expiry: overrides.warranty_expiry ?? "2028-01-01",
    status: overrides.status ?? "in_use",
    responsible_person_id: overrides.responsible_person_id ?? "holder-1",
    responsible_person: overrides.responsible_person ?? {
      id: "holder-1",
      name: "Alice Chen",
    },
    disposal_reason: overrides.disposal_reason ?? null,
    version: overrides.version ?? 1,
    created_at: overrides.created_at ?? "2026-01-01T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-01-01T00:00:00Z",
  };
}

function buildResponseFromAssets(assets: AssetRecord[], total = assets.length, perPage = 5) {
  return {
    data: assets,
    meta: {
      total,
      page: 1,
      per_page: perPage,
      total_pages: total > 0 ? Math.ceil(total / perPage) : 0,
    },
  };
}

function getRenderedRowTexts() {
  return Array.from(document.querySelectorAll(".ant-table-tbody > tr.ant-table-row")).map(
    (row) => row.textContent ?? "",
  );
}

async function openCreateForm(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Register Asset" }));
}

async function fillRequiredCreateFields(
  user: ReturnType<typeof userEvent.setup>,
  overrides: {
    name: string;
    model: string;
    purchaseAmount: string;
    activationDate?: string;
    warrantyExpiry?: string;
  },
) {
  const modal = getOpenModalContent();

  await user.type(within(modal).getByLabelText("Name"), overrides.name);
  await user.type(within(modal).getByLabelText("Model"), overrides.model);
  await user.click(within(modal).getByLabelText("Category"));
  await user.click(screen.getAllByRole("option", { name: "Computer" })[0]);
  await user.type(within(modal).getByLabelText("Supplier"), "Acme");
  await user.type(within(modal).getByLabelText("Purchase Date"), "2026-01-10");
  await user.type(within(modal).getByLabelText("Purchase Amount"), overrides.purchaseAmount);
  if (overrides.activationDate) {
    await user.type(within(modal).getByLabelText("Activation Date"), overrides.activationDate);
  }
  if (overrides.warrantyExpiry) {
    await user.type(within(modal).getByLabelText("Warranty Expiry"), overrides.warrantyExpiry);
  }
  await user.click(within(modal).getByRole("button", { name: "Save" }));
}

function buildResponse(
  assetCode: string,
  assetName: string,
  total: number,
  status: "in_stock" | "in_use" | "disposed" = "in_use",
) {
  return buildResponseFromAssets(
    [
      buildAsset({
        id: `${assetCode}-id`,
        asset_code: assetCode,
        name: assetName,
        status,
      }),
    ],
    total,
  );
}

describe("AssetList", () => {
  beforeEach(async () => {
    mockListAssets.mockReset();
    mockListMyAssets.mockReset();
    mockCreateAsset.mockReset();
    mockListUsers.mockReset();
    mockNavigate.mockReset();
    mockCreateAsset.mockResolvedValue({} as never);
    mockListUsers.mockResolvedValue({
      data: [buildHolder("holder-1", "Alice Chen")],
      meta: { total: 1, page: 1, per_page: 100, total_pages: 1 },
    });
    await i18n.changeLanguage("en");
  });

  it("loads all assets for manager without role switch controls", async () => {
    authAs(managerUser);
    mockListAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 10));

    render(<AssetList />);

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenCalledWith({ page: 1, perPage: 5 });
    });
    expect(mockListUsers).toHaveBeenCalledWith({ page: 1, perPage: 100, role: "holder" });
    expect(mockListMyAssets).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Asset List" })).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    expect(screen.getByText("Business Laptop 13")).toBeInTheDocument();
    expect(screen.getByText("Showing 10 assets")).toBeInTheDocument();
    expect(screen.queryByText("View Mode")).not.toBeInTheDocument();
    expect(screen.queryByText("Holder")).not.toBeInTheDocument();
  });

  it("changes table page when pagination is clicked", async () => {
    authAs(managerUser);
    mockListAssets
      .mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 10))
      .mockResolvedValueOnce(buildResponse("AST-2026-00006", "Field Laptop", 10));

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    });

    await user.click(screen.getByTitle("2"));

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenLastCalledWith({ page: 2, perPage: 5 });
      expect(screen.getByText("AST-2026-00006")).toBeInTheDocument();
    });
  });

  it("loads only current holder assets for holder role", async () => {
    authAs(holderUser);
    mockListMyAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 1));

    render(<AssetList />);

    await waitFor(() => {
      expect(mockListMyAssets).toHaveBeenCalledWith({ page: 1, perPage: 5 });
    });
    expect(mockListAssets).not.toHaveBeenCalled();
    expect(screen.getByText("Showing 1 assets")).toBeInTheDocument();
    expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
  });

  it("applies multi-dimensional filters to the manager asset query", async () => {
    authAs(managerUser);
    mockListAssets.mockResolvedValue(buildResponseFromAssets([buildAsset()], 1, 100));

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("Business Laptop 13")).toBeInTheDocument();
    });

    await user.type(screen.getByRole("textbox", { name: "Asset search" }), "Laptop");
    await user.type(screen.getByRole("textbox", { name: "Department filter" }), "IT");
    await user.type(screen.getByRole("textbox", { name: "Location filter" }), "Taipei HQ");
    await selectOption(user, "asset-status-filter", "In Use");
    await selectOption(user, "asset-category-filter", "Computer");
    await selectOption(user, "asset-holder-filter", "Alice Chen (IT)");

    await waitFor(
      () => {
        expect(mockListAssets).toHaveBeenLastCalledWith({
          page: 1,
          perPage: 100,
          q: "Laptop",
          status: "in_use",
          category: "computer",
          responsiblePersonId: "holder-1",
        });
      },
      { timeout: 1000 },
    );
  });

  it("filters department and location by substring on the client", async () => {
    authAs(managerUser);
    mockListAssets.mockResolvedValue(
      buildResponseFromAssets(
        [
          buildAsset({
            id: "asset-eng",
            asset_code: "AST-2026-00001",
            name: "Engineering Laptop",
            department: "Engineering",
            location: "Hsinchu Office",
          }),
          buildAsset({
            id: "asset-fin",
            asset_code: "AST-2026-00002",
            name: "Finance Laptop",
            department: "Finance",
            location: "Taipei HQ",
          }),
        ],
        2,
        100,
      ),
    );

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("Engineering Laptop")).toBeInTheDocument();
      expect(screen.getByText("Finance Laptop")).toBeInTheDocument();
    });

    await user.type(screen.getByRole("textbox", { name: "Department filter" }), "eer");
    await user.type(screen.getByRole("textbox", { name: "Location filter" }), "sin");

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenLastCalledWith({
        page: 1,
        perPage: 100,
      });
    });

    expect(screen.getByText("Engineering Laptop")).toBeInTheDocument();
    expect(screen.queryByText("Finance Laptop")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 assets")).toBeInTheDocument();
  });

  it("resets to the first page when a filter changes", async () => {
    authAs(managerUser);
    mockListAssets
      .mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 10))
      .mockResolvedValueOnce(buildResponse("AST-2026-00006", "Field Laptop", 10))
      .mockResolvedValue(buildResponse("AST-2026-00001", "Business Laptop 13", 10));

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    });

    await user.click(screen.getByTitle("2"));

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenLastCalledWith({ page: 2, perPage: 5 });
    });

    await selectOption(user, "asset-status-filter", "In Use");

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenLastCalledWith({
        page: 1,
        perPage: 5,
        status: "in_use",
      });
    });
  });

  it("maps sortable header clicks to backend sort params", async () => {
    authAs(managerUser);
    mockListAssets.mockResolvedValue(buildResponse("AST-2026-00001", "Business Laptop 13", 10));

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("Business Laptop 13")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("columnheader", { name: /asset code/i }));

    await waitFor(() => {
      expect(mockListAssets).toHaveBeenLastCalledWith({
        page: 1,
        perPage: 5,
        sort: "asset_code",
      });
    });
  });

  it("sorts purchase amount locally without refetching", async () => {
    authAs(managerUser);
    mockListAssets.mockResolvedValue(
      buildResponseFromAssets([
        buildAsset({
          id: "asset-expensive",
          asset_code: "AST-2026-00001",
          name: "Enterprise Workstation",
          purchase_amount: "50000.00",
        }),
        buildAsset({
          id: "asset-budget",
          asset_code: "AST-2026-00002",
          name: "Small Budget Laptop",
          purchase_amount: "1200.00",
        }),
      ]),
    );

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("Enterprise Workstation")).toBeInTheDocument();
      expect(screen.getByText("Small Budget Laptop")).toBeInTheDocument();
    });

    expect(getRenderedRowTexts()[0]).toContain("Enterprise Workstation");

    await user.click(screen.getByRole("columnheader", { name: /purchase amount/i }));

    await waitFor(() => {
      expect(getRenderedRowTexts()[0]).toContain("Small Budget Laptop");
    });
    expect(mockListAssets).toHaveBeenCalledTimes(1);
  });

  it("navigates to the asset detail page when clicking detail", async () => {
    authAs(managerUser);
    mockListAssets.mockResolvedValueOnce(buildResponse("AST-2026-00001", "Business Laptop 13", 1));

    const user = userEvent.setup({ delay: null });
    render(<AssetList />);

    await waitFor(() => {
      expect(screen.getByText("AST-2026-00001")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Detail" }));

    expect(mockNavigate).toHaveBeenCalledWith("/assets/AST-2026-00001-id");
  });

  it("blocks create when purchase amount is negative", async () => {
    const user = await renderAsManagerWith(buildResponse("AST-2026-00001", "Business Laptop 13", 1));
    await openCreateForm(user);

    await fillRequiredCreateFields(user, {
      name: "Invalid Asset",
      model: "X-100",
      purchaseAmount: "-1",
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          "Purchase amount must be a positive number with up to 2 decimal places and 15 digits",
        ),
      ).toBeInTheDocument();
    });
    expect(mockCreateAsset).not.toHaveBeenCalled();
  });

  it("blocks create when warranty expiry is before activation date", async () => {
    const user = await renderAsManagerWith(buildResponse("AST-2026-00001", "Business Laptop 13", 1));
    await openCreateForm(user);

    await fillRequiredCreateFields(user, {
      name: "Warranty Invalid Asset",
      model: "WX-1",
      purchaseAmount: "1000.00",
      activationDate: "2026-05-10",
      warrantyExpiry: "2026-05-01",
    });

    await waitFor(() => {
      expect(screen.getByText("Warranty expiry must be after activation date")).toBeInTheDocument();
    });
    expect(mockCreateAsset).not.toHaveBeenCalled();
  });
});
