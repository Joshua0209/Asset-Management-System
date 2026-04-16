export type AssetStatus = 'in_stock' | 'in_use' | 'pending_repair' | 'under_repair' | 'disposed';

export type AssetCategory =
  | 'phone'
  | 'computer'
  | 'tablet'
  | 'monitor'
  | 'printer'
  | 'network_equipment'
  | 'other';

export interface Asset {
  id: string;
  asset_code: string;
  name: string;
  model: string;
  category: AssetCategory;
  status: AssetStatus;
  specification: string;
  supplier: string;
  purchase_date: string;
  purchase_amount: string;
  warranty_expiry: string;
  location: string;
  department: string;
  responsible_person_id: string | null;
  responsible_person_name: string | null;
  activation_date: string | null;
  notes: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CreateAssetRequest {
  name: string;
  model: string;
  category: AssetCategory;
  specification?: string;
  supplier: string;
  purchase_date: string;
  purchase_amount: string;
  warranty_expiry?: string;
  location: string;
  department: string;
  notes?: string;
}

export interface UpdateAssetRequest {
  name?: string;
  model?: string;
  category?: AssetCategory;
  specification?: string;
  location?: string;
  department?: string;
  notes?: string;
  version: number;
}

export interface AssetFilterParams {
  page?: number;
  per_page?: number;
  search?: string;
  category?: AssetCategory;
  status?: AssetStatus;
  department?: string;
  location?: string;
  responsible_person_id?: string;
}
