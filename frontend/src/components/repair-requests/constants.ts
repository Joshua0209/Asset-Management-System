import type { RepairRequestStatus } from '../../api/repair-requests';

export const REPAIR_REQUEST_STATUS_COLORS: Record<RepairRequestStatus, string> = {
  pending_review: 'processing',
  under_repair: 'warning',
  completed: 'success',
  rejected: 'error',
};
