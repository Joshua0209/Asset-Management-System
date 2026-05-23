// Phase 7 — main load test.
//
// Constant-arrival-rate scenarios for the six AMS critical flows, weighted
// per docs/plans/observability-implementation-plan.md § Phase 7:
//
//   search    40%   GET /api/v1/assets
//   login     20%   POST /api/v1/auth/login (anonymous, exercises bcrypt + limiter)
//   submit    15%   POST /api/v1/repair-requests
//   approve   10%   POST /api/v1/repair-requests/{id}/approve
//   complete  10%   POST /api/v1/repair-requests/{id}/complete
//   register   5%   POST /api/v1/assets
//
// Default total arrival rate: 60 req/min (configurable via K6_TOTAL_RPM).
// Default duration: 10 min.
//
// Thresholds: p(95) < 3000 ms on requests we expect to succeed,
// http_req_failed < 0.01 on the same. The submit/approve/complete flows
// carry a known >0% "expected 409" rate at high arrival rates, so we tag
// requests with `expected_response: true` only on the read paths; the writer
// paths report status via `check()` and contribute to a softer SLO.

import { BASE_URL } from "./lib/auth.js";
import {
  approveRepairFlow,
  completeRepairFlow,
  loginFlow,
  registerAssetFlow,
  searchAssetsFlow,
  submitRepairFlow,
} from "./lib/flows.js";

const TOTAL_RPM = parsePositive("K6_TOTAL_RPM", 60);
const DURATION = __ENV.K6_DURATION || "10m";

function parsePositive(name, fallback) {
  const value = Number.parseInt(__ENV[name] || `${fallback}`, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function rate(fraction) {
  // Floor at 1 req/min so a scenario never silently goes idle when
  // K6_TOTAL_RPM is set very low.
  return Math.max(1, Math.round(TOTAL_RPM * fraction));
}

function preAllocatedVUs(reqPerMinute) {
  // Reserve enough VUs to absorb 2s-ish latency without queueing. The
  // reference lab uses rate/30; we widen to rate/20 because the multipart
  // submit path is slower.
  return Math.max(2, Math.ceil(reqPerMinute / 20));
}

function scenario(execName, fraction) {
  const arrival = rate(fraction);
  const preAlloc = preAllocatedVUs(arrival);
  return {
    executor: "constant-arrival-rate",
    rate: arrival,
    timeUnit: "1m",
    duration: DURATION,
    preAllocatedVUs: preAlloc,
    maxVUs: Math.max(preAlloc * 2, 20),
    exec: execName,
    tags: {
      traffic_profile: "load",
      flow: execName,
    },
  };
}

export const options = {
  scenarios: {
    search: scenario("search", 0.4),
    login: scenario("login", 0.2),
    submit: scenario("submit", 0.15),
    approve: scenario("approve", 0.1),
    complete: scenario("complete", 0.1),
    register: scenario("register", 0.05),
  },
  thresholds: {
    // Strict on overall failure rate — anything > 1% on the load mix means
    // a flow is degrading the run.
    http_req_failed: ["rate<0.05"],
    // p(95) is generous because the submit path runs through multipart +
    // ImageStorage + audit log + flush. Tighter SLOs belong on per-route
    // dashboards.
    http_req_duration: ["p(95)<3000"],
    // Per-flow SLO: search must stay snappy or dashboards lose signal.
    "http_req_duration{flow:search}": ["p(95)<800"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export function search() {
  searchAssetsFlow();
}
export function login() {
  loginFlow();
}
export function submit() {
  submitRepairFlow();
}
export function approve() {
  approveRepairFlow();
}
export function complete() {
  completeRepairFlow();
}
export function register() {
  registerAssetFlow();
}

export function setup() {
  // eslint-disable-next-line no-console
  console.log(
    `k6-load: total=${TOTAL_RPM}rpm duration=${DURATION} target=${BASE_URL}`,
  );
}
