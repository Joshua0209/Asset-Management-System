// Shared authentication helper for the AMS k6 scripts.
//
// Why this lives in lib/ rather than inline:
//   1. Login is the slowest endpoint by ~10x (bcrypt verification). If every
//      VU re-logged in on every iteration the test would measure bcrypt, not
//      the app.
//   2. The JWT lifetime in dev is generous (settings default), so caching the
//      token for the run is safe.
//   3. The manager + holder seeds use deterministic credentials (managed by
//      backend/scripts/seed_demo_data.py on the host, mounted into the
//      backend container as /app/scripts/seed_demo_data.py); we want one
//      place that knows them.
//
// Anti-enumeration in /auth/login means a wrong email/password returns a
// 401 with the same body, so the script logs and bails if the seed creds
// haven't been planted.

import http from "k6/http";
import { check, fail } from "k6";
import { Counter } from "k6/metrics";

// Default targets the host-network backend (developer runs `k6` on their
// laptop against `docker compose up backend`). For a container-run k6 use
// `-e BASE_URL=http://host.docker.internal:8000` on Docker Desktop / OrbStack
// or `--network host` plus the default URL on Linux.
export const BASE_URL = (__ENV.BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

// Seed defaults match the BOOTSTRAP_MANAGER_* env in docker-compose.yml
// (bootstrap manager) and scripts/seed_demo_data.py (first holder).
// Override via env if a different account should drive the load.
export const MANAGER_EMAIL = __ENV.MANAGER_EMAIL || "admin@example.com";
export const MANAGER_PASSWORD = __ENV.MANAGER_PASSWORD || "ChangeMe123";
export const HOLDER_EMAIL = __ENV.HOLDER_EMAIL || "holder1@example.com";
export const HOLDER_PASSWORD = __ENV.HOLDER_PASSWORD || "Password123";

// Per-VU token cache: each VU logs in once and reuses the JWT for the rest
// of the run. k6 isolates module state per VU, so this map only ever holds
// the credentials this VU touched.
const tokenCache = new Map();

// Counter surfaced on the k6 summary + dashboards so a token-expiry storm
// during long stress / consistent runs is visible instead of degrading to a
// "no work done" silence. One increment per cache eviction triggered by a
// downstream 401 (see ``invalidateToken`` below).
export const tokenEvictions = new Counter("ams_load_token_evictions");

function performLogin(email, password) {
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

export function login(email, password) {
  if (tokenCache.has(email)) {
    return tokenCache.get(email);
  }
  return performLogin(email, password);
}

export function loginManager() {
  return login(MANAGER_EMAIL, MANAGER_PASSWORD);
}

export function loginHolder() {
  return login(HOLDER_EMAIL, HOLDER_PASSWORD);
}

// Drop a cached token after a downstream 401 so a long run that outlives
// the JWT TTL recovers on the next iteration instead of silently looping
// on a stale token. Returns the credentials that were cached so callers
// can re-login eagerly via ``loginManager`` / ``loginHolder`` / ``login``.
//
// Default behaviour: if the email is known, drop it and bump the
// ``ams_load_token_evictions`` counter. Calling this on an unknown email
// is a no-op (e.g. a flow that uses a per-VU throwaway address).
export function invalidateToken(email) {
  if (tokenCache.has(email)) {
    tokenCache.delete(email);
    tokenEvictions.add(1, { email_role: roleForEmail(email) });
  }
}

function roleForEmail(email) {
  if (email === MANAGER_EMAIL) return "manager";
  if (email === HOLDER_EMAIL) return "holder";
  return "other";
}

// Helper for flow scripts: if ``res.status`` is 401, drop the cached
// token for this email and re-login once. The flow is expected to retry
// its downstream call after this returns the fresh token. Returns
// ``null`` when no retry is warranted (status != 401), so the caller can
// branch.
export function refreshIfUnauthorized(res, email, password) {
  if (res.status !== 401) {
    return null;
  }
  invalidateToken(email);
  return performLogin(email, password);
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
