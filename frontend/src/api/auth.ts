import apiClient from './client';
import {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  User,
  PasswordResetRequest,
  PasswordResetConfirmRequest,
  CommonResponse
} from './types';

export const authApi = {
  login: (data: LoginRequest) =>
    apiClient.post<LoginResponse>('/auth/login', data),

  register: (data: RegisterRequest) =>
    apiClient.post<RegisterResponse>('/auth/register', data),

  me: () =>
    apiClient.get<CommonResponse<User>>('/auth/me'),

  requestPasswordReset: (data: PasswordResetRequest) =>
    apiClient.post<CommonResponse<{ message: string }>>('/auth/password-reset', data),

  confirmPasswordReset: (data: PasswordResetConfirmRequest) =>
    apiClient.post<CommonResponse<{ message: string }>>('/auth/password-reset/confirm', data),
};
