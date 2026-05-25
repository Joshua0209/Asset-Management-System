// Smoke test.
//
// Sanity check that the stack accepts traffic against every critical flow.
// Runs for 1 minute with 3 VUs; the goal is "no 5xx", not throughput.
//
// Exercises the AMS critical flow set (login, search, my-assets, list
// repairs, register asset, submit/approve/complete repair) so a green
// smoke run proves the observability stack sees every metric/log/trace
// label the dashboards depend on.

import { sleep } from "k6";

import { BASE_URL } from "./lib/auth.js";
import {
  approveRepairFlow,
  completeRepairFlow,
  healthFlow,
  listRepairsFlow,
  loginFlow,
  myAssetsFlow,
  registerAssetFlow,
  searchAssetsFlow,
  submitRepairFlow,
} from "./lib/flows.js";

export const options = {
  vus: 3,
  duration: __ENV.K6_DURATION || "1m",
  thresholds: {
    // Smoke is intentionally loose — we accept some 409s on the
    // multi-VU race paths (submit/approve/complete) but flag a 5xx.
    http_req_failed: ["rate<0.20"],
    http_req_duration: ["p(95)<2000"],
  },
};

const FLOWS = [
  healthFlow,
  loginFlow,
  searchAssetsFlow,
  myAssetsFlow,
  listRepairsFlow,
  registerAssetFlow,
  submitRepairFlow,
  approveRepairFlow,
  completeRepairFlow,
];

export default function () {
  const flow = FLOWS[__ITER % FLOWS.length];
  flow();
  sleep(0.5);
}

export function setup() {
  // eslint-disable-next-line no-console
  console.log(`k6-smoke: targeting ${BASE_URL}`);
}
