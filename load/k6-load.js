// Main load test.
//
// Constant-arrival-rate scenarios for the six AMS critical flows, weighted:
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
// Thresholds: p(95) < 3000 ms and http_req_failed < 0.01 per scenario.
// The writer scenarios (submit/approve/complete) carry a known >0% "expected
// 409" rate at high arrival rates — those 409s are explicit ``check()``s in
// the flow rather than http_req_failed contributors, so the threshold above
// stays meaningful as a 5xx-only SLO.

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
    // Strict on overall failure rate — anything > 5% on the load mix means
    // a flow is degrading the run. ``abortOnFail`` so a fully-broken stack
    // ends the run early instead of burning the full ``K6_DURATION`` (10m
    // default) and filling dashboards with misleading "we got data" panels.
    // ``delayAbortEval`` gives the warmup a moment so a single bad first
    // batch doesn't tear the run down before steady state.
    http_req_failed: [
      { threshold: "rate<0.05", abortOnFail: true, delayAbortEval: "30s" },
    ],
    // p(95) is generous because the submit path runs through multipart +
    // ImageStorage + audit log + flush. Tighter SLOs belong on per-route
    // dashboards. Abort if p95 explodes past 8s for over a minute — that's
    // well into "the app is wedged" territory, not just transient queueing.
    http_req_duration: [
      { threshold: "p(95)<3000" },
      { threshold: "p(95)<8000", abortOnFail: true, delayAbortEval: "60s" },
    ],
    // Per-flow SLO: search must stay snappy or dashboards lose signal.
    "http_req_duration{flow:search}": ["p(95)<800"],
    // Per-flow check threshold: if every submit/approve/complete is
    // checks-failing (e.g. listRepairs prereq broken), the dashboard
    // signal is gone. Abort early rather than ride out the rest of the
    // run on an empty FSM-transition counter.
    "checks{flow:submit}": [
      { threshold: "rate>0.50", abortOnFail: true, delayAbortEval: "60s" },
    ],
    "checks{flow:approve}": [
      { threshold: "rate>0.50", abortOnFail: true, delayAbortEval: "60s" },
    ],
    "checks{flow:complete}": [
      { threshold: "rate>0.50", abortOnFail: true, delayAbortEval: "60s" },
    ],
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
