import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";
import { routes } from "../App";
import type { AuthSession, UserRole } from "../api/auth";

const STORAGE_KEY = "ams-auth";

function seedSession(role: UserRole): void {
  const session: AuthSession = {
    token: "test-token",
    expiresAt: new Date(Date.now() + 3600_000).toISOString(),
    user: {
      id: "u-1",
      email: role === "manager" ? "manager@example.com" : "holder@example.com",
      name: role === "manager" ? "Manager One" : "Holder One",
      role,
    },
  };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
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
      <MemoryRouter initialEntries={[path]}>
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
    window.localStorage.clear();
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

  it("redirects a holder landing to /assets", async () => {
    seedSession("holder");
    await renderAt("/");
    await waitFor(() => expect(currentPath()).toBe("/assets"));
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
    expect(screen.getByRole("menuitem", { name: /assets/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /reviews/i })).toBeInTheDocument();
  });

  it("hides manager-only sidebar items for holder", async () => {
    seedSession("holder");
    await renderAt("/assets");
    expect(screen.queryByRole("menuitem", { name: /dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /reviews/i })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /assets/i })).toBeInTheDocument();
  });
});
