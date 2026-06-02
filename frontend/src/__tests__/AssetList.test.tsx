import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import AssetList from "@/pages/manager/AssetList";
import i18n from "@/i18n";
import { ApiError } from "@/api";
import { mockApi } from "./test-helpers";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@/auth/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/api", async () => {
  const actual = await vi.importActual<typeof import("@/api")>("@/api");
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

const authModule = await import("@/auth/AuthContext");
const apiModule = await import("@/api");

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
  department: "IT",
  location: "Taipei HQ",
};

const holderUser = {
  id: "holder-1",
  email: "holder@example.com",
  name: "Holder",
  role: "holder" as const,
  department: "Engineering",
  location: "Hsinchu Fab12",
};

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
  responses.forEach((r) => mockListAssets.mockResolvedValueOnce(r));
  const user = userEvent.setup({ delay: null });
  render(<AssetList />);
  await waitFor(() => expect(screen.getByText(responses[0].data[0].name)).toBeInTheDocument());
  return user;
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
  const modal = screen.getByRole("dialog");

  await user.type(within(modal).getByLabelText("Name"), overrides.name);
  await user.type(within(modal).getByLabelText("Model"), overrides.model);
  // antd Select: clicking the label opens the dropdown. The option list is
  // portaled to .ant-select-dropdown; wait for it to be visible before
  // picking "computer". `getAllByRole("option")` without the wait can match
  // a stale, hidden option from a previous test or fail outright if the
  // dropdown hasn't mounted yet.
  // Open the antd Category Select and click its "computer" option. The
  // option list is portaled to body. Multiple ".ant-select-item-option"
  // rows live in the DOM at once (one per category); target the visible
  // dropdown's first match.
  await user.click(within(modal).getByLabelText("Category"));
  await user.click(
    await screen.findByText("computer", { selector: ".ant-select-item-option-content" }),
  );
  await user.type(within(modal).getByLabelText("Supplier"), "Acme");
  await user.type(within(modal).getByLabelText("Purchase Date"), "2026-01-10");
  await user.type(within(modal).getByLabelText("Purchase Amount"), overrides.purchaseAmount);
  if (overrides.activationDate) {
    await user.type(within(modal).getByLabelText("Activation Date"), overrides.activationDate);
  }
  if (overrides.warrantyExpiry) {
    await user.type(within(modal).getByLabelText("Warranty Expiry"), overrides.warrantyExpiry);
  }
  await user.click(screen.getByRole("button", { name: "Save" }));
}

function buildResponse(
  assetCode: string,
  assetName: string,
  total: number,
  status: "in_stock" | "in_use" | "disposed" = "in_use",
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
        assignment_date: status === "in_use" ? "2026-01-05" : null,
        unassignment_date: null,
        status,
        responsible_person_id: "holder-1",
        responsible_person: {
          id: "holder-1",
          name: "Alice Chen",
          department: "Engineering",
          location: "Hsinchu Fab12",
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
    mockCreateAsset.mockReset();
    mockListUsers.mockReset();
    mockNavigate.mockReset();
    mockApi.success.mockReset();
    mockApi.error.mockReset();
    mockListUsers.mockResolvedValue({
      data: [
        {
          id: "holder-1",
          name: "Alice Chen",
          email: "alice@example.com",
          role: "holder",
          department: "IT",
          location: "Taipei HQ",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      meta: {
        total: 1,
        page: 1,
        per_page: 100,
        total_pages: 1,
      },
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

  it("marks purchase amount as required in the create form", async () => {
    const user = await renderAsManagerWith(buildResponse("AST-2026-00001", "Business Laptop 13", 1));

    await openCreateForm(user);

    const modal = screen.getByRole("dialog");
    const purchaseAmountLabel = within(modal).getByText("Purchase Amount").closest("label");

    expect(purchaseAmountLabel).toHaveClass("ant-form-item-required");
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

  // handleSaveAsset has three distinct exit branches after the create
  // refactor — locking each in catches the original "form validation
  // error silently fires the action-failed toast" bug and the new
  // "non-ApiError now surfaces a generic toast" behaviour.

  it("fires the success toast after a successful create", async () => {
    const user = await renderAsManagerWith(buildResponse("AST-2026-00001", "Business Laptop 13", 1));
    mockCreateAsset.mockResolvedValueOnce(
      buildResponse("AST-2026-00002", "New Laptop", 1).data[0],
    );
    // The post-create reload fires another listAssets — return a permissive
    // mock so the success branch (which calls reload BEFORE api.success)
    // doesn't trip on an undefined response.
    mockListAssets.mockResolvedValue(buildResponse("AST-2026-00002", "New Laptop", 2));

    await openCreateForm(user);
    await fillRequiredCreateFields(user, {
      name: "New Laptop",
      model: "X-200",
      purchaseAmount: "1500.00",
    });

    await waitFor(() => {
      expect(mockCreateAsset).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(mockApi.success).toHaveBeenCalledWith({
        title: "Asset registered successfully",
      });
    });
    expect(mockApi.error).not.toHaveBeenCalled();
  });

  it("surfaces an ApiError as a description on the action-failed toast", async () => {
    const user = await renderAsManagerWith(buildResponse("AST-2026-00001", "Business Laptop 13", 1));
    mockCreateAsset.mockRejectedValueOnce(
      new ApiError(409, "conflict", "duplicate asset_code"),
    );

    await openCreateForm(user);
    await fillRequiredCreateFields(user, {
      name: "Dup Laptop",
      model: "X-200",
      purchaseAmount: "1500.00",
    });

    await waitFor(() => {
      expect(mockApi.error).toHaveBeenCalled();
    });
    // The error toast routes ApiError through getApiErrorMessage; pin both
    // the title and the fact that the description is non-empty (the exact
    // i18n string for 'errors.conflict' is owned by apiErrors.ts, not us).
    const calls = mockApi.error.mock.calls;
    const lastErrorCall = calls[calls.length - 1]?.[0];
    expect(lastErrorCall?.title).toBe("Action failed");
    expect(typeof lastErrorCall?.description).toBe("string");
    expect(lastErrorCall?.description).not.toBe("Something went wrong. Please try again later.");
    expect(mockApi.success).not.toHaveBeenCalled();
  });

  it("falls back to a generic toast description when create rejects with a non-ApiError", async () => {
    const user = await renderAsManagerWith(buildResponse("AST-2026-00001", "Business Laptop 13", 1));
    mockCreateAsset.mockRejectedValueOnce(new Error("network down"));

    await openCreateForm(user);
    await fillRequiredCreateFields(user, {
      name: "Network Fail Laptop",
      model: "X-200",
      purchaseAmount: "1500.00",
    });

    await waitFor(() => {
      expect(mockApi.error).toHaveBeenCalledWith({
        title: "Action failed",
        // errors.serverError — the generic fallback we added so plain
        // Errors (network failure / JS bug) no longer fail silently.
        description: "Something went wrong. Please try again later.",
      });
    });
    expect(mockApi.success).not.toHaveBeenCalled();
  });
});
