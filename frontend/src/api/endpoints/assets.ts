import apiClient from '../client';
import type { ApiResponse, PaginatedResponse } from '../types';
import type {
  Asset,
  CreateAssetRequest,
  UpdateAssetRequest,
  AssetFilterParams,
} from '@/types/asset';

export const assetsApi = {
  list(params?: AssetFilterParams) {
    return apiClient.get<PaginatedResponse<Asset>>('/assets', { params });
  },

  getById(id: string) {
    return apiClient.get<ApiResponse<Asset>>(`/assets/${id}`);
  },

  create(data: CreateAssetRequest) {
    return apiClient.post<ApiResponse<Asset>>('/assets', data);
  },

  update(id: string, data: UpdateAssetRequest) {
    return apiClient.patch<ApiResponse<Asset>>(`/assets/${id}`, data);
  },

  assign(id: string, userId: string, version: number) {
    return apiClient.post<ApiResponse<Asset>>(`/assets/${id}/assign`, {
      user_id: userId,
      version,
    });
  },

  unassign(id: string, reason: string, version: number) {
    return apiClient.post<ApiResponse<Asset>>(`/assets/${id}/unassign`, {
      reason,
      version,
    });
  },

  dispose(id: string, reason: string, version: number) {
    return apiClient.post<ApiResponse<Asset>>(`/assets/${id}/dispose`, {
      reason,
      version,
    });
  },
};
