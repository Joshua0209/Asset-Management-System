export type RepairStatus = 'pending_review' | 'under_repair' | 'completed' | 'rejected';

export interface RepairRequest {
  id: string;
  asset_id: string;
  asset_code: string;
  asset_name: string;
  requester_id: string;
  requester_name: string;
  reviewer_id: string | null;
  reviewer_name: string | null;
  status: RepairStatus;
  fault_description: string;
  rejection_reason: string | null;
  repair_date: string | null;
  fault_content: string | null;
  repair_plan: string | null;
  repair_cost: string | null;
  repair_vendor: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SubmitRepairRequest {
  asset_id: string;
  fault_description: string;
}

export interface ApproveRepairRequest {
  version: number;
}

export interface RejectRepairRequest {
  rejection_reason: string;
  version: number;
}

export interface CompleteRepairRequest {
  repair_date: string;
  fault_content: string;
  repair_plan: string;
  repair_cost: string;
  repair_vendor: string;
  version: number;
}

export interface RepairFilterParams {
  page?: number;
  per_page?: number;
  status?: RepairStatus;
  asset_id?: string;
}
