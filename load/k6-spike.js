// Spike test.
//
// Sudden surge to validate the stack absorbs a burst — the kind of pattern
// the dashboards' "saturation" panel is there to surface. Ramp 5 → 50 VUs
// in 20 s, hold 40 s, drain.
//
// Flow set focuses on the search path because that's the one the
// user-facing app routes the most reads through.

import { sleep } from "k6";

import { BASE_URL } from "./lib/auth.js";
import {
  myAssetsFlow,
  registerAssetFlow,
  searchAssetsFlow,
  submitRepairFlow,
} from "./lib/flows.js";

export const options = {
  stages: [
    { duration: "20s", target: 5 },
    { duration: "20s", target: 50 },
    { duration: __ENV.K6_HOLD || "40s", target: 50 },
    { duration: "20s", target: 0 },
  ],
  thresholds: {
    // Spike is allowed to push failures up — we just want to observe how
    // the stack reacts. 50% is the same ceiling the reference lab uses.
    http_req_failed: ["rate<0.50"],
  },
};

const SPIKE_FLOWS = [
  searchAssetsFlow,
  searchAssetsFlow,
  searchAssetsFlow,
  myAssetsFlow,
  submitRepairFlow,
  registerAssetFlow,
];

export default function () {
  const flow = SPIKE_FLOWS[__ITER % SPIKE_FLOWS.length];
  flow();
  sleep(0.2);
}

export function setup() {
  // eslint-disable-next-line no-console
  console.log(`k6-spike: targeting ${BASE_URL}`);
}
