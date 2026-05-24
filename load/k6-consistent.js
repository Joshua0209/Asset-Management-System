// Long-running, per-flow constant-arrival-rate traffic generator.
//
// Each AMS flow gets its own constant-arrival-rate scenario whose rate is
// set via env, so an operator can independently knob-tweak how much
// search vs. approve traffic the dashboards see during a demo. Setting
// any rate to 0 drops that scenario.
//
// Default rates per minute (override via env):
//
//   SEARCH_PER_MIN   = 30
//   MY_ASSETS_PER_MIN = 15
//   LIST_REPAIRS_PER_MIN = 10
//   SUBMIT_PER_MIN   = 4
//   APPROVE_PER_MIN  = 4
//   COMPLETE_PER_MIN = 4
//   REGISTER_PER_MIN = 2
//   HEALTH_PER_MIN   = 6
//
// Default TRAFFIC_DURATION: 30m.

import { BASE_URL } from "./lib/auth.js";
import {
  approveRepairFlow,
  completeRepairFlow,
  healthFlow,
  listRepairsFlow,
  myAssetsFlow,
  registerAssetFlow,
  searchAssetsFlow,
  submitRepairFlow,
} from "./lib/flows.js";

const TRAFFIC_DURATION = __ENV.TRAFFIC_DURATION || "30m";
const DEFAULT_MAX_VUS = parsePositive("MAX_VUS", 50);

function parsePositive(name, fallback) {
  const value = Number.parseInt(__ENV[name] || `${fallback}`, 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function parseRate(name, fallback) {
  const value = Number.parseInt(__ENV[name] || `${fallback}`, 10);
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

function preAllocatedVUs(ratePerMinute) {
  const configured = Number.parseInt(__ENV.PREALLOCATED_VUS || "", 10);
  if (Number.isFinite(configured) && configured > 0) {
    return configured;
  }
  return Math.max(1, Math.ceil(ratePerMinute / 20));
}

function addScenario(scenarios, name, envName, defaultRate, execName) {
  const rate = parseRate(envName, defaultRate);
  if (rate === 0) return;
  const preAlloc = preAllocatedVUs(rate);
  scenarios[name] = {
    executor: "constant-arrival-rate",
    rate,
    timeUnit: "1m",
    duration: TRAFFIC_DURATION,
    preAllocatedVUs: preAlloc,
    maxVUs: Math.max(preAlloc, DEFAULT_MAX_VUS),
    exec: execName,
    tags: {
      traffic_profile: "consistent",
      flow: name,
    },
  };
}

const scenarios = {};
addScenario(scenarios, "search", "SEARCH_PER_MIN", 30, "search");
addScenario(scenarios, "my_assets", "MY_ASSETS_PER_MIN", 15, "myAssets");
addScenario(
  scenarios,
  "list_repairs",
  "LIST_REPAIRS_PER_MIN",
  10,
  "listRepairs",
);
addScenario(scenarios, "submit", "SUBMIT_PER_MIN", 4, "submit");
addScenario(scenarios, "approve", "APPROVE_PER_MIN", 4, "approve");
addScenario(scenarios, "complete", "COMPLETE_PER_MIN", 4, "complete");
addScenario(scenarios, "register", "REGISTER_PER_MIN", 2, "register");
addScenario(scenarios, "health", "HEALTH_PER_MIN", 6, "health");

if (Object.keys(scenarios).length === 0) {
  // If the operator zeroed every rate, register a 1/min health probe so
  // k6 has at least one scenario to run (k6 exits immediately with no
  // scenarios) and the dashboards still see a heartbeat.
  scenarios.health = {
    executor: "constant-arrival-rate",
    rate: 1,
    timeUnit: "1m",
    duration: TRAFFIC_DURATION,
    preAllocatedVUs: 1,
    maxVUs: Math.max(1, DEFAULT_MAX_VUS),
    exec: "health",
    tags: { traffic_profile: "consistent", flow: "health" },
  };
}

export const options = {
  scenarios,
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  userAgent: "ams-observability-traffic-generator/1.0",
};

export function search() {
  searchAssetsFlow();
}
export function myAssets() {
  myAssetsFlow();
}
export function listRepairs() {
  listRepairsFlow();
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
export function health() {
  healthFlow();
}

export function setup() {
  // eslint-disable-next-line no-console
  console.log(
    `k6-consistent: duration=${TRAFFIC_DURATION} scenarios=[${Object.keys(scenarios).join(",")}] target=${BASE_URL}`,
  );
}
