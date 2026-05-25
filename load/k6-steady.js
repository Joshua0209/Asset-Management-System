// Steady test.
//
// Sustained moderate load to fill dashboards with realistic data for the
// correlation demo. 10 VUs for 5 minutes, with the read-heavy 80/20 mix the
// AMS dashboards expect: search/list dominates, write paths trickle in.
//
// The AMS-specific flow set is what the dashboards in
// config/grafana/dashboards/ are pinned against.

import { sleep } from "k6";

import { BASE_URL } from "./lib/auth.js";
import {
  approveRepairFlow,
  completeRepairFlow,
  listRepairsFlow,
  myAssetsFlow,
  registerAssetFlow,
  searchAssetsFlow,
  submitRepairFlow,
} from "./lib/flows.js";

export const options = {
  stages: [
    { duration: "30s", target: 10 },
    { duration: __ENV.K6_HOLD || "4m", target: 10 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.30"],
    http_req_duration: ["p(95)<3000"],
  },
};

// Read-heavy 80/20 mix. The reference lab does the same: dashboards need a
// dense, fast read stream for the latency histograms to bin properly, and
// write churn for the FSM-transitions panel.
function pickFlow() {
  const roll = Math.random();
  if (roll < 0.4) return searchAssetsFlow;
  if (roll < 0.6) return myAssetsFlow;
  if (roll < 0.75) return listRepairsFlow;
  if (roll < 0.85) return submitRepairFlow;
  if (roll < 0.92) return approveRepairFlow;
  if (roll < 0.97) return completeRepairFlow;
  return registerAssetFlow;
}

export default function () {
  pickFlow()();
  sleep(Math.random() * 1.5);
}

export function setup() {
  // eslint-disable-next-line no-console
  console.log(`k6-steady: targeting ${BASE_URL}`);
}
