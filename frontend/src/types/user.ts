export type UserRole = 'holder' | 'manager';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  department: string;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  role: UserRole;
  department: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}
