import { render, screen } from "@testing-library/react";
import App from "../App";
import { vi } from "vitest";

// Mock react-router-dom to use memory router in tests
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    createBrowserRouter: actual.createMemoryRouter,
  };
});

// Mock the AuthContext
vi.mock("../contexts/AuthContext", async () => {
  const actual = await vi.importActual("../contexts/AuthContext");
  return {
    ...actual,
    useAuth: () => ({
      user: { id: "1", name: "Test User", role: "manager" },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    }),
    AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

// Mock react-i18next partially
vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: {
        changeLanguage: () => Promise.resolve(),
        language: "en",
      },
    }),
  };
});

describe("App", () => {
  it("renders the sidebar menu items", async () => {
    render(<App />);
    // Since we mocked t to return the key, we check for keys
    // Using findBy to handle async rendering and avoid act() warnings
    expect(await screen.findByRole("menuitem", { name: /common.nav.dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /common.nav.assets/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /common.nav.repairs/i })).toBeInTheDocument();
  });

  it("renders the language switcher", async () => {
    render(<App />);
    expect(await screen.findByText("中")).toBeInTheDocument();
    expect(screen.getByText("EN")).toBeInTheDocument();
  });
});
