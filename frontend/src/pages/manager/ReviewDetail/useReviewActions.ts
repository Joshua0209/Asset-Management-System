import { useCallback, useState } from 'react';
import { Modal } from 'antd';
import type { ParseKeys, TFunction } from 'i18next';
import { ApiError, repairRequestsApi } from '@/api';
import { getApiErrorMessage } from '@/utils/apiErrors';

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
  const [isSubmitting, setIsSubmitting] = useState(false);

  const run = useCallback(
    async (call: () => Promise<unknown>, successKey: ParseKeys): Promise<boolean> => {
      setIsSubmitting(true);
      try {
        await call();
        await reload();
        api.success({ title: t(successKey) });
        return true;
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.code === 'conflict') {
            Modal.warning({
              title: t('errors.conflictTitle'),
              content: getApiErrorMessage(e, t),
              onOk: async () => {
                await reload();
              },
            });
          } else {
            api.error({
              title: t('reviews.actionFailedTitle'),
              description: getApiErrorMessage(e, t),
            });
          }
        }
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    [api, reload, t],
  );

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
