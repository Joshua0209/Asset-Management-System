// Phase 7 — stress / breakpoint test.
//
// Ramps the six AMS critical flows from a light baseline up past the point
// the stack degrades, so the operator can read the breakpoint (the arrival
// rate at which p(95) > 3 s or error rate > 1%).
//
// IMPORTANT: per Phase 7 plan, the rate limiter must be disabled while this
// runs, or we measure slowapi rather than the app. Set
// `RATE_LIMIT_ENABLED=false` on the backend service before invoking:
//
//   docker compose -f docker-compose.yml -f docker-compose.observability.yml \
//     run --rm -e RATE_LIMIT_ENABLED=false backend ...
//
// (The Makefile target `make load-stress` documents the same step.)

import { BASE_URL } from "./lib/auth.js";
import {
  approveRepairFlow,
  completeRepairFlow,
  loginFlow,
  registerAssetFlow,
  searchAssetsFlow,
  submitRepairFlow,
} from "./lib/flows.js";

const MAX_VUS = parsePositive("K6_MAX_VUS", 200);
const RAMP_DURATION = __ENV.K6_RAMP || "5m";

function parsePositive(name, fallback) {
  const value = Number.parseInt(__ENV[name] || `${fallback}`, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

// Ramping VUs (not ramping-arrival-rate) because the breakpoint we care
// about is "how many concurrent users does this single-worker backend hold
// before tail latency explodes" — that maps directly onto VU count.
export const options = {
  stages: [
    { duration: "30s", target: 5 },
    { duration: "60s", target: 25 },
    { duration: RAMP_DURATION, target: MAX_VUS },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    // Threshold abort: if the stack starts erroring > 50% or p95 stretches
    // past 10s, we have crossed the breakpoint and can stop. abortOnFail
    // makes the run end early so the operator's terminal doesn't fill with
    // failing checks for the rest of the ramp.
    http_req_failed: [
      { threshold: "rate<0.50", abortOnFail: true, delayAbortEval: "10s" },
    ],
    http_req_duration: [
      { threshold: "p(95)<10000", abortOnFail: true, delayAbortEval: "30s" },
    ],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

// Weighted picker — search/login dominate so the breakpoint is realistic
// against the read-heavy workload AMS sees in real use. Writes (submit,
// approve, complete, register) still appear so the FSM-transition counter
// has signal during the ramp.
const FLOWS = [
  { weight: 0.45, fn: searchAssetsFlow },
  { weight: 0.2, fn: loginFlow },
  { weight: 0.1, fn: submitRepairFlow },
  { weight: 0.1, fn: approveRepairFlow },
  { weight: 0.1, fn: completeRepairFlow },
  { weight: 0.05, fn: registerAssetFlow },
];

let cumulativeWeights = null;
function ensureWeights() {
  if (cumulativeWeights !== null) return cumulativeWeights;
  const acc = [];
  let running = 0;
  for (const item of FLOWS) {
    running += item.weight;
    acc.push({ threshold: running, fn: item.fn });
  }
  cumulativeWeights = acc;
  return acc;
}

export default function () {
  const dist = ensureWeights();
  const roll = Math.random();
  for (const item of dist) {
    if (roll < item.threshold) {
      item.fn();
      return;
    }
  }
  dist[dist.length - 1].fn();
}

export function setup() {
  // eslint-disable-next-line no-console
  console.log(
    `k6-stress: maxVUs=${MAX_VUS} ramp=${RAMP_DURATION} target=${BASE_URL}`,
  );
  // eslint-disable-next-line no-console
  console.log(
    "Reminder: set RATE_LIMIT_ENABLED=false on the backend or this run measures the limiter, not the app.",
  );
}
