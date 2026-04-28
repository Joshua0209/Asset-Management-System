// Auth API client: pure functions wrapping POST /auth/login, POST /auth/register
// and GET /auth/me as documented in 12-api-design.md §1.
//
// When VITE_USE_MOCK_AUTH=true, requests are served from an in-memory user list
// so the FE can be exercised without a running backend.

import { ApiError, apiFetch } from "../base-client";
import { AUTH_PATHS } from "./keys";
import type { AuthSession, AuthUser, LoginPayload, RegisterPayload, UserRole } from "./types";

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH === "true";

interface LoginEnvelope {
  data: {
    token: string;
    expires_at: string;
    user: { id: string; email: string; name: string; role: UserRole };
  };
}

interface UserEnvelope {
  data: AuthUser;
}

// ---------- Mock fixtures (dev-only) ----------

interface MockUserRecord {
  password: string;
  user: AuthUser;
}

const MOCK_USERS: ReadonlyArray<MockUserRecord> = [
  {
    password: "admin",
    user: { id: "mock-manager", email: "admin@example.com", name: "Admin Manager", role: "manager" },
  },
  {
    password: "holder",
    user: { id: "mock-holder", email: "holder@example.com", name: "Demo Holder", role: "holder" },
  },
];

const MOCK_DELAY_MS = 200;
const MOCK_SESSION_LIFETIME_MS = 24 * 60 * 60 * 1000;
const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

function mockSessionFor(user: AuthUser): AuthSession {
  return {
    token: `mock-token-${user.id}`,
    expiresAt: new Date(Date.now() + MOCK_SESSION_LIFETIME_MS).toISOString(),
    user,
  };
}

// ---------- Real API ----------

export async function login(payload: LoginPayload): Promise<AuthSession> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    const match = MOCK_USERS.find(
      (record) => record.user.email === payload.email && record.password === payload.password,
    );
    if (!match) {
      throw new ApiError(401, "unauthorized", "Invalid email or password");
    }
    return mockSessionFor(match.user);
  }

  const body = await apiFetch<LoginEnvelope>(AUTH_PATHS.login, {
    method: "POST",
    json: payload,
  });
  return {
    token: body.data.token,
    expiresAt: body.data.expires_at,
    user: body.data.user,
  };
}

export async function register(payload: RegisterPayload): Promise<AuthUser> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    if (MOCK_USERS.some((record) => record.user.email === payload.email)) {
      throw new ApiError(409, "conflict", "Email is already registered");
    }
    return {
      id: `mock-holder-${Date.now()}`,
      email: payload.email,
      name: payload.name,
      role: "holder",
    };
  }

  const body = await apiFetch<UserEnvelope>(AUTH_PATHS.register, {
    method: "POST",
    json: payload,
  });
  return body.data;
}

export async function fetchMe(token: string): Promise<AuthUser> {
  if (USE_MOCK_AUTH) {
    await sleep(MOCK_DELAY_MS);
    const match = MOCK_USERS.find((record) => token === `mock-token-${record.user.id}`);
    if (!match) throw new ApiError(401, "unauthorized", "Invalid token");
    return match.user;
  }

  const body = await apiFetch<UserEnvelope>(AUTH_PATHS.me, { token });
  return body.data;
}
