export type AssetStatus =
  | "in_stock"
  | "in_use"
  | "pending_repair"
  | "under_repair"
  | "disposed";

export type AssetCategory =
  | "phone"
  | "computer"
  | "tablet"
  | "monitor"
  | "printer"
  | "network_equipment"
  | "other";

export interface AssetPerson {
  id: string;
  name: string;
  email?: string;
}

export interface AssetRecord {
  id: string;
  asset_code: string;
  name: string;
  model: string;
  specs: string | null;
  category: string;
  supplier: string;
  purchase_date: string;
  purchase_amount: string | number;
  location: string;
  department: string;
  activation_date: string | null;
  warranty_expiry: string | null;
  assignment_date: string | null;
  unassignment_date: string | null;
  status: AssetStatus;
  responsible_person_id: string | null;
  responsible_person: AssetPerson | null;
  disposal_reason: string | null;
  version: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface PaginationMeta {
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface PaginatedAssetResponse {
  data: AssetRecord[];
  meta: PaginationMeta;
}

export interface AssetDataResponse {
  data: AssetRecord;
}

export interface ListAssetsParams {
  page?: number;
  perPage?: number;
  q?: string;
  status?: AssetStatus;
  category?: string;
  department?: string;
  location?: string;
  responsiblePersonId?: string;
  sort?: string;
}

export interface AssetCreatePayload {
  name: string;
  model: string;
  specs?: string | null;
  category: AssetCategory;
  supplier: string;
  purchase_date: string;
  purchase_amount: string | number;
  location?: string | null;
  department?: string | null;
  activation_date?: string | null;
  warranty_expiry?: string | null;
}

export interface AssetUpdatePayload {
  version: number;
  name?: string;
  model?: string;
  specs?: string | null;
  category?: AssetCategory;
  supplier?: string;
  purchase_date?: string;
  purchase_amount?: string | number;
  location?: string | null;
  department?: string | null;
  activation_date?: string | null;
  warranty_expiry?: string | null;
}

export interface AssetAssignPayload {
  responsible_person_id: string;
  assignment_date: string;
  version: number;
}

export interface AssetUnassignPayload {
  reason: string;
  unassignment_date: string;
  version: number;
}

export interface AssetDisposePayload {
  disposal_reason: string;
  version: number;
}
