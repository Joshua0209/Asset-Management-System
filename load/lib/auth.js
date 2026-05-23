// Shared authentication helper for the AMS k6 scripts.
//
// Why this lives in lib/ rather than inline:
//   1. Login is the slowest endpoint by ~10x (bcrypt verification). If every
//      VU re-logged in on every iteration the test would measure bcrypt, not
//      the app.
//   2. The JWT lifetime in dev is generous (settings default), so caching the
//      token for the run is safe.
//   3. The manager + holder seeds use deterministic credentials
//      (scripts/seed_demo_data.py); we want one place that knows them.
//
// Anti-enumeration in /auth/login means a wrong email/password returns a
// 401 with the same body, so the script logs and bails if the seed creds
// haven't been planted.

import http from "k6/http";
import { check, fail } from "k6";

export const BASE_URL = (__ENV.BASE_URL || "http://backend:8000").replace(
  /\/$/,
  "",
);

// Seed defaults match scripts/seed_demo_data.py's bootstrap manager + first
// holder. Override via env if a different account should drive the load.
export const MANAGER_EMAIL = __ENV.MANAGER_EMAIL || "manager@example.com";
export const MANAGER_PASSWORD =
  __ENV.MANAGER_PASSWORD || "ChangeMe123!"; // matches BOOTSTRAP_MANAGER_PASSWORD default in .env.example
export const HOLDER_EMAIL = __ENV.HOLDER_EMAIL || "holder1@example.com";
export const HOLDER_PASSWORD = __ENV.HOLDER_PASSWORD || "Password123";

// Per-VU token cache: each VU logs in once and reuses the JWT for the rest
// of the run. k6 isolates module state per VU, so this map only ever holds
// the credentials this VU touched.
const tokenCache = new Map();

export function login(email, password) {
  if (tokenCache.has(email)) {
    return tokenCache.get(email);
  }
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email, password }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "POST /auth/login" },
    },
  );
  const ok = check(res, {
    "login succeeded": (r) => r.status === 200,
  });
  if (!ok) {
    fail(
      `login failed for ${email}: status=${res.status} body=${res.body}`,
    );
  }
  const body = res.json();
  const token = body && body.data && body.data.token;
  if (!token) {
    fail(`login response missing data.token for ${email}`);
  }
  tokenCache.set(email, token);
  return token;
}

export function loginManager() {
  return login(MANAGER_EMAIL, MANAGER_PASSWORD);
}

export function loginHolder() {
  return login(HOLDER_EMAIL, HOLDER_PASSWORD);
}

export function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
  };
}

// Helper used by flows that ALSO need a JSON content type. Building the
// combined dict inline at every callsite triggers the "object literal in
// hot loop" allocation; k6 keeps perf samples cleaner when the object is
// pre-shaped per caller.
export function jsonAuthHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}
