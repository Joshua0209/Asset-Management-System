import { useCallback } from 'react';
import type { TFunction } from 'i18next';
import { repairRequestsApi } from '@/api';
import { useSubmitAction } from '@/hooks/useSubmitAction';

export interface ApproveValues {
  repair_plan: string;
  repair_vendor: string;
  repair_cost: string;
  planned_date: string;
}

export interface RejectValues {
  rejection_reason: string;
}

export interface RepairDetailsValues {
  repair_date?: string;
  fault_content?: string;
  repair_plan?: string;
  repair_cost?: string;
  repair_vendor?: string;
}

export interface CompleteValues {
  repair_date: string;
  fault_content: string;
  repair_plan: string;
  repair_cost: string;
  repair_vendor: string;
}

interface NotificationApi {
  success: (config: { title: string }) => void;
  error: (config: { title: string; description?: string }) => void;
}

interface UseReviewActionsArgs {
  requestId: string;
  version: number;
  reload: () => Promise<void>;
  api: NotificationApi;
  t: TFunction;
}

export function useReviewActions({ requestId, version, reload, api, t }: UseReviewActionsArgs) {
  const { isSubmitting, run } = useSubmitAction({
    reload,
    api,
    t,
    failureTitleKey: 'reviews.actionFailedTitle',
  });

  const approve = useCallback(
    (values: ApproveValues) =>
      run(
        () => repairRequestsApi.approveRepairRequest(requestId, { version, ...values }),
        'reviews.approveSuccess',
      ),
    [requestId, version, run],
  );

  const reject = useCallback(
    (values: RejectValues) =>
      run(
        () => repairRequestsApi.rejectRepairRequest(requestId, { version, ...values }),
        'reviews.rejectSuccess',
      ),
    [requestId, version, run],
  );

  const saveDetails = useCallback(
    (values: RepairDetailsValues) =>
      run(
        () => repairRequestsApi.updateRepairRequestDetails(requestId, { version, ...values }),
        'reviews.detailsSuccess',
      ),
    [requestId, version, run],
  );

  const complete = useCallback(
    (values: CompleteValues) =>
      run(
        () => repairRequestsApi.completeRepairRequest(requestId, { version, ...values }),
        'reviews.completeSuccess',
      ),
    [requestId, version, run],
  );

  return { isSubmitting, approve, reject, saveDetails, complete };
}
