import apiClient from '../client';
import type { ApiResponse } from '../types';
import type { LoginRequest, LoginResponse, RegisterRequest, User } from '@/types/user';

export const authApi = {
  login(data: LoginRequest) {
    return apiClient.post<ApiResponse<LoginResponse>>('/auth/login', data);
  },

  register(data: RegisterRequest) {
    return apiClient.post<ApiResponse<User>>('/auth/register', data);
  },

  getMe() {
    return apiClient.get<ApiResponse<User>>('/auth/me');
  },
};
