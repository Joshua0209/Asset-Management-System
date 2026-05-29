import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";
import { routes } from "@/App";
import type { AuthSession, UserRole } from "@/api/auth";

const STORAGE_KEY = "ams-auth";

function seedSession(role: UserRole): void {
  const session: AuthSession = {
    token: "test-token",
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
    user: {
      id: "u-1",
      email: role === "manager" ? "manager@example.com" : "holder@example.com",
      name: role === "manager" ? "Manager One" : "Holder One",
      role,
      department: role === "manager" ? "IT" : "Engineering",
      location: role === "manager" ? "Taipei HQ" : "Hsinchu Fab12",
    },
  };
  globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

function AppRoutes() {
  return useRoutes(routes);
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="current-path">{location.pathname}</span>;
}

async function renderAt(path: string): Promise<void> {
  await act(async () => {
    render(
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <LocationProbe />
        <AppRoutes />
      </MemoryRouter>,
    );
  });
}

function currentPath(): string | null {
  return screen.getByTestId("current-path").textContent;
}

describe("App routing & auth guards", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
  });

  it("redirects an unauthenticated visitor to /login", async () => {
    await renderAt("/");
    await waitFor(() => expect(currentPath()).toBe("/auth/login"));
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  it("redirects a manager landing to /dashboard and shows the dashboard", async () => {
    seedSession("manager");
    await renderAt("/");
    await waitFor(() => expect(currentPath()).toBe("/dashboard"));
    expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument();
  });

  it("redirects a holder landing to /my-assets", async () => {
    seedSession("holder");
    await renderAt("/");
    await waitFor(() => expect(currentPath()).toBe("/my-assets"));
    expect(screen.getByRole("heading", { name: /asset list/i })).toBeInTheDocument();
  });

  it("blocks holder from manager-only /reviews and routes to /forbidden", async () => {
    seedSession("holder");
    await renderAt("/reviews");
    await waitFor(() => expect(currentPath()).toBe("/forbidden"));
    expect(screen.getByText(/access denied/i)).toBeInTheDocument();
  });

  it("blocks holder from manager-only /dashboard and routes to /forbidden", async () => {
    seedSession("holder");
    await renderAt("/dashboard");
    await waitFor(() => expect(currentPath()).toBe("/forbidden"));
  });

  it("renders role-filtered sidebar items for manager", async () => {
    seedSession("manager");
    await renderAt("/dashboard");
    expect(screen.getByRole("menuitem", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /asset management/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /repair management/i })).toBeInTheDocument();
  });

  it("hides manager-only sidebar items for holder", async () => {
    seedSession("holder");
    await renderAt("/assets");
    expect(screen.queryByRole("menuitem", { name: /dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /repair management/i })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /my assets/i })).toBeInTheDocument();
  });

  it("redirects an authenticated user away from /auth/login to their landing", async () => {
    seedSession("manager");
    await renderAt("/auth/login");
    await waitFor(() => expect(currentPath()).toBe("/dashboard"));
  });

  it("redirects an unknown path to /auth/login when unauthenticated", async () => {
    await renderAt("/login");
    await waitFor(() => expect(currentPath()).toBe("/auth/login"));
  });

  it("redirects an unknown path to the role landing when authenticated", async () => {
    seedSession("holder");
    await renderAt("/login");
    await waitFor(() => expect(currentPath()).toBe("/my-assets"));
  });
});
