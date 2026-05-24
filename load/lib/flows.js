// Reusable AMS flow functions for all k6 scripts in this directory.
//
// Why one shared module:
//   - The smoke, steady, spike, load, stress, and consistent scenarios all hit
//     the same six critical flows (login, search, submit_repair,
//     approve_repair, complete_repair, register_asset). Sharing them keeps
//     dashboard labels coherent across runs.
//   - `tags.name` on every request standardises the route template Prometheus
//     stores (`POST /repair-requests`, not `POST /repair-requests/<uuid>/...`),
//     so dashboards keep low cardinality.
//
// The flow API:
//   - Every exported function is a self-contained scenario tick. It logs in
//     lazily, does its read/write, and `check()`s a few invariants.
//   - Functions return `void`; failures are surfaced through `check()` so the
//     k6 summary aggregates them.
//   - Flows that need a *target* (e.g. approve picks a pending request) read
//     the live state via the list endpoints — never hard-code IDs, since the
//     DB churns over a long-running test.

import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

import {
  BASE_URL,
  HOLDER_EMAIL,
  HOLDER_PASSWORD,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  authHeaders,
  jsonAuthHeaders,
  loginHolder,
  loginManager,
  refreshIfUnauthorized,
} from "./auth.js";
import { JPEG, JPEG_CONTENT_TYPE, JPEG_FILENAME } from "./fixtures.js";

const HOLDER_TAG = { actor: "holder" };
const MANAGER_TAG = { actor: "manager" };

// Pivotable failure-mode Counters. Each Counter surfaces a distinct
// reason a flow short-circuited without doing user-facing work; they
// stream to GC via k6-prometheus-rw and let dashboards / alerts tell
// "rare fixture state" apart from "upstream regression".
//
// Why Counters, not k6 `check()`s with literal-false predicates: a
// `check(true, { "...": () => false })` shows up in the summary as a
// failed check but the iteration continues normally, so a 5xx from the
// API masquerades as "no candidate available". Counters make each
// failure mode addressable in PromQL and threshold-alertable.
export const submitRepairNoTarget = new Counter(
  "ams_load_submit_repair_no_target_total",
);
export const submitRepairPreconditionFail = new Counter(
  "ams_load_submit_repair_precondition_fail_total",
);
export const approveRepairNoCandidate = new Counter(
  "ams_load_approve_repair_no_candidate_total",
);
export const completeRepairNoCandidate = new Counter(
  "ams_load_complete_repair_no_candidate_total",
);
export const listRepairsUpstreamError = new Counter(
  "ams_load_list_repairs_upstream_error_total",
);
export const malformedEnvelope = new Counter(
  "ams_load_malformed_envelope_total",
);

// ── login (flow #1) ─────────────────────────────────────────────────────────
// Re-runs login so the test exercises the bcrypt cost and the limiter even
// after the per-VU token cache warms up. Uses a throwaway email/pwd that
// SHOULD fail, so we measure the auth path including the anti-enumeration
// dummy-hash branch.
export function loginFlow() {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({
      email: `loadtest+${__VU}@example.com`,
      password: "ProbablyWrong123", // gitleaks:allow — intentional fake creds; this login is expected to 401
    }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "POST /auth/login", actor: "anonymous" },
    },
  );
  // 401 is the expected response (anti-enumeration). We just want timing.
  check(res, {
    "login completed (401 or 200)": (r) =>
      r.status === 200 || r.status === 401,
  });
}

// ── search_assets (flow #2) ─────────────────────────────────────────────────
export function searchAssetsFlow() {
  const token = loginManager();
  const params = {
    headers: authHeaders(token),
    tags: { name: "GET /assets", ...MANAGER_TAG },
  };
  const query =
    "page=1&per_page=20&status=in_use&category=computer&sort=-created_at";
  const res = http.get(`${BASE_URL}/api/v1/assets?${query}`, params);
  check(res, {
    "search_assets 200": (r) => r.status === 200,
  });
}

// ── search_my_assets — the reference lab's "browse" equivalent ──────────────
export function myAssetsFlow() {
  const token = loginHolder();
  const params = {
    headers: authHeaders(token),
    tags: { name: "GET /assets/mine", ...HOLDER_TAG },
  };
  const res = http.get(`${BASE_URL}/api/v1/assets/mine?per_page=10`, params);
  check(res, {
    "my_assets 200": (r) => r.status === 200,
  });
}

// ── list_repair_requests — supports the approve/complete flows ──────────────
// Returns ``{token, items}`` so callers learn whether the cached token was
// refreshed mid-flight (long stress runs that outlive the JWT TTL would
// otherwise loop on a stale token, see auth.js::refreshIfUnauthorized).
// The k6 ``check()`` distinguishes:
//   * 200 — happy path (items may be empty if no candidates exist).
//   * 401 → 200 after refresh — token expiry recovered (a soft signal).
//   * any other status — explicit "list_repairs failed" check so a 500
//     from the API isn't silently confused with "no candidates available"
//     by the downstream approve/complete flows.
function listRepairs(token, statusFilter, asActor, email, password) {
  const params = {
    headers: authHeaders(token),
    tags: {
      name: "GET /repair-requests",
      actor: asActor,
    },
  };
  let res = http.get(
    `${BASE_URL}/api/v1/repair-requests?status=${statusFilter}&per_page=20`,
    params,
  );
  const refreshed = refreshIfUnauthorized(res, email, password);
  let activeToken = token;
  if (refreshed) {
    activeToken = refreshed;
    res = http.get(
      `${BASE_URL}/api/v1/repair-requests?status=${statusFilter}&per_page=20`,
      { ...params, headers: authHeaders(activeToken) },
    );
  }
  check(res, {
    "list_repairs prereq 200": (r) => r.status === 200,
  });
  if (res.status !== 200) {
    // Non-200/non-401: upstream regression masquerading as "no work".
    // Increment the dedicated Counter so PromQL can pivot on it (the
    // check rate alone can't separate this from legitimate empty-result
    // states, since both leave `items` empty).
    listRepairsUpstreamError.add(1, { status: String(res.status) });
    return { token: activeToken, items: [] };
  }
  const body = res.json();
  if (!body || !Array.isArray(body.data)) {
    // 200 with an unexpected envelope shape (server-side regression
    // renaming `data` -> `items`, dropping the field, etc.). Without
    // this guard the flow would silently treat it as empty work.
    malformedEnvelope.add(1, { endpoint: "list_repairs" });
    return { token: activeToken, items: [] };
  }
  return { token: activeToken, items: body.data };
}

export function listRepairsFlow() {
  const token = loginManager();
  const params = {
    headers: authHeaders(token),
    tags: { name: "GET /repair-requests", ...MANAGER_TAG },
  };
  const res = http.get(
    `${BASE_URL}/api/v1/repair-requests?per_page=20&sort=-created_at`,
    params,
  );
  check(res, {
    "list_repairs 200": (r) => r.status === 200,
  });
}

// ── submit_repair (flow #3) ─────────────────────────────────────────────────
// Picks one of the holder's assigned in_use assets, attaches a tiny JPEG and
// POSTs multipart. Conflicts (asset already has an active request) are
// expected at high arrival rates; we just want to drive the multipart parser
// + ImageStorage write path.
export function submitRepairFlow() {
  let token = loginHolder();
  const listParams = {
    headers: authHeaders(token),
    tags: { name: "GET /assets/mine", ...HOLDER_TAG },
  };
  let assets = http.get(
    `${BASE_URL}/api/v1/assets/mine?status=in_use&per_page=20`,
    listParams,
  );
  // Recover from JWT expiry on long runs: a 401 here would silently
  // degrade the rest of the run to "no target" without an explicit signal.
  const refreshed = refreshIfUnauthorized(assets, HOLDER_EMAIL, HOLDER_PASSWORD);
  if (refreshed) {
    token = refreshed;
    assets = http.get(
      `${BASE_URL}/api/v1/assets/mine?status=in_use&per_page=20`,
      { ...listParams, headers: authHeaders(token) },
    );
  }
  if (
    !check(assets, {
      "assets/mine 200 (precondition)": (r) => r.status === 200,
    })
  ) {
    // Real upstream failure: pivot on the actual status so a 5xx is
    // visible in dashboards instead of confused with "no target".
    submitRepairPreconditionFail.add(1, { status: String(assets.status) });
    return;
  }
  const body = assets.json();
  if (!body || !Array.isArray(body.data)) {
    malformedEnvelope.add(1, { endpoint: "assets_mine" });
    return;
  }
  const items = body.data;
  if (items.length === 0) {
    // No assignable target — emit on the dedicated Counter so dashboards
    // distinguish "fixture-empty" from upstream errors handled above.
    submitRepairNoTarget.add(1);
    return;
  }
  const target = items[__VU % items.length];
  const payload = {
    asset_id: target.id,
    fault_description: `k6-submit VU=${__VU} iter=${__ITER}`,
    images: http.file(JPEG, JPEG_FILENAME, JPEG_CONTENT_TYPE),
  };
  const res = http.post(`${BASE_URL}/api/v1/repair-requests`, payload, {
    headers: authHeaders(token),
    tags: { name: "POST /repair-requests", ...HOLDER_TAG },
  });
  check(res, {
    // 201 = created, 409 = duplicate active request (expected under load)
    "submit_repair 2xx/409": (r) => r.status === 201 || r.status === 409,
  });
}

// ── approve_repair (flow #4) ────────────────────────────────────────────────
export function approveRepairFlow() {
  let token = loginManager();
  const { token: refreshedToken, items: candidates } = listRepairs(
    token,
    "pending_review",
    "manager",
    MANAGER_EMAIL,
    MANAGER_PASSWORD,
  );
  token = refreshedToken;
  if (candidates.length === 0) {
    approveRepairNoCandidate.add(1);
    return;
  }
  const target = candidates[__VU % candidates.length];
  const res = http.post(
    `${BASE_URL}/api/v1/repair-requests/${target.id}/approve`,
    JSON.stringify({ version: target.version }),
    {
      headers: jsonAuthHeaders(token),
      tags: { name: "POST /repair-requests/{id}/approve", ...MANAGER_TAG },
    },
  );
  check(res, {
    // 200 = approved, 409 = stale version or invalid transition (expected
    // when multiple VUs race for the same target).
    "approve_repair 200/409": (r) => r.status === 200 || r.status === 409,
  });
}

// ── complete_repair (flow #5) ───────────────────────────────────────────────
export function completeRepairFlow() {
  let token = loginManager();
  const { token: refreshedToken, items: candidates } = listRepairs(
    token,
    "under_repair",
    "manager",
    MANAGER_EMAIL,
    MANAGER_PASSWORD,
  );
  token = refreshedToken;
  if (candidates.length === 0) {
    completeRepairNoCandidate.add(1);
    return;
  }
  const target = candidates[__VU % candidates.length];
  const completion = {
    repair_date: new Date().toISOString().slice(0, 10),
    fault_content: "k6 verified fault",
    repair_plan: "k6 repaired and validated",
    repair_cost: "199.99",
    repair_vendor: "k6 Vendor",
    version: target.version,
  };
  const res = http.post(
    `${BASE_URL}/api/v1/repair-requests/${target.id}/complete`,
    JSON.stringify(completion),
    {
      headers: jsonAuthHeaders(token),
      tags: { name: "POST /repair-requests/{id}/complete", ...MANAGER_TAG },
    },
  );
  check(res, {
    "complete_repair 200/409": (r) => r.status === 200 || r.status === 409,
  });
}

// ── register_asset (flow #6) ────────────────────────────────────────────────
const ASSET_CATEGORIES = [
  "phone",
  "computer",
  "tablet",
  "monitor",
  "printer",
  "network_equipment",
  "other",
];

export function registerAssetFlow() {
  const token = loginManager();
  const category = ASSET_CATEGORIES[__ITER % ASSET_CATEGORIES.length];
  const today = new Date().toISOString().slice(0, 10);
  const payload = {
    name: `k6 ${category} ${__VU}-${__ITER}`,
    model: `k6-model-${__VU}-${__ITER}`,
    specs: "k6 load generator entry",
    category,
    supplier: "k6 Supplier",
    purchase_date: today,
    purchase_amount: "1500.00",
    location: "Taipei HQ",
    department: "IT",
  };
  const res = http.post(
    `${BASE_URL}/api/v1/assets`,
    JSON.stringify(payload),
    {
      headers: jsonAuthHeaders(token),
      tags: { name: "POST /assets", ...MANAGER_TAG },
    },
  );
  check(res, {
    // 200 = created (returns DataResponse), 409 = asset_code race (expected
    // under heavy parallel registers).
    "register_asset 2xx/409": (r) =>
      r.status === 200 || r.status === 201 || r.status === 409,
  });
}

// ── health (reference-lab parity) ───────────────────────────────────────────
// Liveness + readiness. The smoke and consistent profiles hit these so
// dashboards always have at least one heartbeat metric.
export function healthFlow() {
  http.get(`${BASE_URL}/health`, {
    tags: { name: "GET /health", actor: "anonymous" },
  });
  http.get(`${BASE_URL}/ready`, {
    tags: { name: "GET /ready", actor: "anonymous" },
  });
}
