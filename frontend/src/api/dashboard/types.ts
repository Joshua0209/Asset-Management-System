import type { RepairRequestStatus } from "../repair-requests";

export interface DashboardKpis {
  total_assets: number;
  in_use_assets: number;
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
  id: string;
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
