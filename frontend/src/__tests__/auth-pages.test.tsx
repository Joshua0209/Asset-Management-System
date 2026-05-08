import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Login from "../pages/auth/Login";
import Register from "../pages/auth/Register";
import { AuthProvider } from "../auth/AuthContext";
import { ApiError } from "../api";

// Replace the entire api barrel so both AuthContext (authApi.login) and
// Register (authApi.register) call into the same vi.fn() instances.
vi.mock("../api", async () => {
  const { ApiError } = await vi.importActual<typeof import("../api/base-client")>(
    "../api/base-client",
  );
  return {
    ApiError,
    authApi: {
      login: vi.fn(),
      register: vi.fn(),
      fetchMe: vi.fn(),
    },
  };
});

const apiBarrel = await import("../api");
const mockLogin = vi.mocked(apiBarrel.authApi.login);
const mockRegister = vi.mocked(apiBarrel.authApi.register);

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="path">{location.pathname}</span>;
}

function renderLogin() {
  return render(
    <AuthProvider>
      <MemoryRouter
        initialEntries={["/auth/login"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/auth/login" element={<Login />} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

function renderRegister() {
  return render(
    <AuthProvider>
      <MemoryRouter
        initialEntries={["/auth/register"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/auth/register" element={<Register />} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

const validSession = () => ({
  token: "tkn",
  expiresAt: new Date(Date.now() + 60_000).toISOString(),
  user: { id: "u", email: "x@example.com", name: "X", role: "holder" as const },
});

describe("Login page", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
    mockLogin.mockReset();
  });

  afterEach(() => {
    globalThis.localStorage.clear();
  });

  it("submits credentials and navigates to '/' on success", async () => {
    mockLogin.mockResolvedValueOnce(validSession());
    const user = userEvent.setup({ delay: null });
    renderLogin();

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "pw12345A");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith({
      email: "user@example.com",
      password: "pw12345A",
    }));
    await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/"));
  });

  it("renders an error alert when the API rejects with ApiError", async () => {
    mockLogin.mockRejectedValueOnce(
      new ApiError(401, "unauthorized", "Invalid email or password"),
    );
    const user = userEvent.setup({ delay: null });
    renderLogin();

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid email or password/i);
  });

  it("falls back to a generic message for non-ApiError failures", async () => {
    mockLogin.mockRejectedValueOnce(new Error("network down"));
    const user = userEvent.setup({ delay: null });
    renderLogin();

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "pw12345A");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("Register page", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
    mockLogin.mockReset();
    mockRegister.mockReset();
  });

  it("submits the form, auto-logs in, and navigates to '/'", async () => {
    mockRegister.mockResolvedValueOnce({
      id: "u-new",
      email: "new@example.com",
      name: "New",
      role: "holder",
    });
    mockLogin.mockResolvedValueOnce(validSession());
    const user = userEvent.setup({ delay: null });
    renderRegister();

    await user.type(screen.getByLabelText(/name/i), "New User");
    await user.type(screen.getByLabelText(/department/i), "IT");
    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/password/i), "abcd1234");
    await user.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => expect(mockRegister).toHaveBeenCalled());
    await waitFor(() => expect(mockLogin).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("path").textContent).toBe("/"));
  });

  it("renders an error alert when the register API rejects with ApiError", async () => {
    mockRegister.mockRejectedValueOnce(
      new ApiError(409, "conflict", "Email already registered"),
    );
    const user = userEvent.setup({ delay: null });
    renderRegister();

    await user.type(screen.getByLabelText(/name/i), "Dup");
    await user.type(screen.getByLabelText(/department/i), "IT");
    await user.type(screen.getByLabelText(/email/i), "admin@example.com");
    await user.type(screen.getByLabelText(/password/i), "abcd1234");
    await user.click(screen.getByRole("button", { name: /register/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/email already registered/i);
  });
});
