import { request } from "../base-client";
import { DASHBOARD_PATHS } from "./keys";
import type { ManagerDashboard, ManagerDashboardResponse } from "./types";

const USE_MOCK_AUTH = import.meta.env.VITE_USE_MOCK_AUTH === "true";

export interface ManagerDashboardResult {
  data: ManagerDashboard;
  // True when VITE_USE_MOCK_AUTH is on and the values are a stub.
  // The page surfaces this as a banner so operators can never mistake
  // a zeroed-out mock payload for a real "everything is fine" reading.
  isMock: boolean;
}

const EMPTY_DASHBOARD: ManagerDashboard = {
  kpis: {
    total_assets: 0,
    in_stock_assets: 0,
    in_use_assets: 0,
    pending_repair_assets: 0,
    under_repair_assets: 0,
    pending_repair_requests: 0,
  },
  asset_categories: [],
  repair_summary: {
    created_today: 0,
    pending_review: 0,
    under_repair: 0,
    completed_today: 0,
  },
  recent_pending_repairs: [],
};

export async function getManagerDashboard(): Promise<ManagerDashboardResult> {
  if (USE_MOCK_AUTH) {
    // Mock mode has no aggregation backend; return a zero-state payload
    // so the UI renders without 404s. Real numbers come from the API.
    // eslint-disable-next-line no-console
    console.warn(
      "[dashboard] VITE_USE_MOCK_AUTH=true — returning zeroed mock payload, " +
        "not live data. Disable mock auth to see real metrics.",
    );
    return { data: EMPTY_DASHBOARD, isMock: true };
  }
  const response = await request<ManagerDashboardResponse>({
    method: "GET",
    url: DASHBOARD_PATHS.manager,
  });
  return { data: response.data, isMock: false };
}
