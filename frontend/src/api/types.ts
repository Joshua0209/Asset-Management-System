export interface User {
  id: string;
  email: string;
  name: string;
  department: string;
  role: 'holder' | 'manager';
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  data: {
    token: string;
    expires_at: string;
    user: User;
  };
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  department: string;
  role: 'holder' | 'manager';
}

export interface RegisterResponse {
  data: User;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  token: string;
  new_password: string;
}

export interface CommonResponse<T> {
  data: T;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Array<{
      field: string;
      message: string;
      code: string;
    }>;
  };
}
