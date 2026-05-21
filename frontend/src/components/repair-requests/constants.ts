import type { RepairRequestStatus } from '@/api/repair-requests';
import { designStatusColors } from '@/design/antdTheme';

export const REPAIR_REQUEST_STATUS_COLORS: Record<RepairRequestStatus, string> = {
  pending_review: designStatusColors.repairRequest.pendingReview,
  under_repair: designStatusColors.repairRequest.underRepair,
  completed: designStatusColors.repairRequest.completed,
  rejected: designStatusColors.repairRequest.rejected,
};
