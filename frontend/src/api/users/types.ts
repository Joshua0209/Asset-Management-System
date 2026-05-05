export type UserRole = "holder" | "manager";

export interface UserRecord {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  department: string;
  created_at: string | null;
}

export interface PaginationMeta {
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface PaginatedUsersResponse {
  data: UserRecord[];
  meta: PaginationMeta;
}

export interface UsersListResponse {
  data: UserRecord[];
}

export interface ListUsersParams {
  page?: number;
  perPage?: number;
  role?: UserRole;
  department?: string;
  q?: string;
}
