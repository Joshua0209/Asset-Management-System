export const REPAIR_REQUEST_PATHS = {
  list: "/repair-requests",
  detail: (repairRequestId: string) => `/repair-requests/${repairRequestId}`,
  approve: (repairRequestId: string) => `/repair-requests/${repairRequestId}/approve`,
  reject: (repairRequestId: string) => `/repair-requests/${repairRequestId}/reject`,
  repairDetails: (repairRequestId: string) =>
    `/repair-requests/${repairRequestId}/repair-details`,
  complete: (repairRequestId: string) => `/repair-requests/${repairRequestId}/complete`,
} as const;
