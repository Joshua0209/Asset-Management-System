export type RepairRequestStatus =
  | "pending_review"
  | "under_repair"
  | "completed"
  | "rejected";

export interface RepairAssetSummary {
  id: string;
  asset_code: string;
  name: string;
}

export interface RepairUserSummary {
  id: string;
  name: string;
}

export interface RepairImage {
  id: string;
  url: string;
  uploaded_at: string;
}

export interface RepairRequestRecord {
  id: string;
  asset_id: string;
  requester_id: string;
  reviewer_id: string | null;
  status: RepairRequestStatus;
  fault_description: string;
  repair_date: string | null;
  fault_content: string | null;
  repair_plan: string | null;
  repair_cost: string | number | null;
  repair_vendor: string | null;
  rejection_reason: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  asset: RepairAssetSummary;
  requester: RepairUserSummary;
  reviewer: RepairUserSummary | null;
  images: RepairImage[];
}

export interface PaginationMeta {
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface PaginatedRepairRequestResponse {
  data: RepairRequestRecord[];
  meta: PaginationMeta;
}

export interface RepairRequestDataResponse {
  data: RepairRequestRecord;
}

export interface ListRepairRequestsParams {
  page?: number;
  perPage?: number;
  status?: RepairRequestStatus;
  assetId?: string;
  requesterId?: string;
  sort?: string;
}

export interface RepairRequestApprovePayload {
  version: number;
  repair_plan?: string;
  repair_vendor?: string;
  repair_cost?: string | number;
  planned_date?: string;
}

export interface RepairRequestRejectPayload {
  version: number;
  rejection_reason?: string;
  reason?: string;
}

export interface RepairRequestDetailsPayload {
  version: number;
  repair_date?: string;
  fault_content?: string;
  repair_plan?: string;
  repair_cost?: string | number;
  repair_vendor?: string;
}

export interface RepairRequestCompletePayload {
  version: number;
  repair_date: string;
  fault_content: string;
  repair_plan: string;
  repair_cost: string | number;
  repair_vendor: string;
}

export interface RepairRequestCreatePayload {
  asset_id: string;
  fault_description: string;
  version?: number;
}
