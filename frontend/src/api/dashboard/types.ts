import type { RepairRequestStatus } from "../repair-requests";

export interface DashboardKpis {
  // Sum of every non-disposed bucket below (total = in_stock + in_use +
  // pending_repair + under_repair) — matches docs/system-design/12-api-design.md.
  total_assets: number;
  in_stock_assets: number;
  in_use_assets: number;
  pending_repair_assets: number;
  under_repair_assets: number;
  pending_repair_requests: number;
}

export interface AssetCategoryCount {
  category: string;
  count: number;
}

export interface RepairSummary {
  created_today: number;
  pending_review: number;
  under_repair: number;
  completed_today: number;
}

export interface RecentPendingRepair {
  // Internal UUID primary key — used for routing to /reviews/<id>.
  // Never displayed.
  id: string;
  // Human-readable code (e.g. REP-2026-00041) shown in the UI.
  // Not safe to use as a route param because the backend route
  // resolves /reviews/<id> by UUID only.
  repair_id: string;
  asset_id: string;
  asset_name: string;
  requester_name: string;
  status: RepairRequestStatus;
  created_at: string;
}

export interface ManagerDashboard {
  kpis: DashboardKpis;
  asset_categories: AssetCategoryCount[];
  repair_summary: RepairSummary;
  recent_pending_repairs: RecentPendingRepair[];
}

export interface ManagerDashboardResponse {
  data: ManagerDashboard;
}
