export type AssetStatus =
  | "in_stock"
  | "in_use"
  | "pending_repair"
  | "under_repair"
  | "disposed";

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

export interface ListAssetsParams {
  page?: number;
  perPage?: number;
}
