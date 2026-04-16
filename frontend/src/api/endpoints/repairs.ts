import apiClient from '../client';
import type { ApiResponse, PaginatedResponse } from '../types';
import type {
  RepairRequest,
  SubmitRepairRequest,
  ApproveRepairRequest,
  RejectRepairRequest,
  CompleteRepairRequest,
  RepairFilterParams,
} from '@/types/repair';

export const repairsApi = {
  list(params?: RepairFilterParams) {
    return apiClient.get<PaginatedResponse<RepairRequest>>('/repair-requests', { params });
  },

  getById(id: string) {
    return apiClient.get<ApiResponse<RepairRequest>>(`/repair-requests/${id}`);
  },

  submit(data: SubmitRepairRequest) {
    return apiClient.post<ApiResponse<RepairRequest>>('/repair-requests', data);
  },

  approve(id: string, data: ApproveRepairRequest) {
    return apiClient.post<ApiResponse<RepairRequest>>(`/repair-requests/${id}/approve`, data);
  },

  reject(id: string, data: RejectRepairRequest) {
    return apiClient.post<ApiResponse<RepairRequest>>(`/repair-requests/${id}/reject`, data);
  },

  complete(id: string, data: CompleteRepairRequest) {
    return apiClient.post<ApiResponse<RepairRequest>>(`/repair-requests/${id}/complete`, data);
  },
};
