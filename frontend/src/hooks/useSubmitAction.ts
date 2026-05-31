import { useCallback, useState } from 'react';
import { Modal } from 'antd';
import type { ParseKeys, TFunction } from 'i18next';
import { ApiError } from '@/api';
import { getApiErrorMessage } from '@/utils/apiErrors';

interface NotificationApi {
  success: (config: { title: string }) => void;
  error: (config: { title: string; description?: string }) => void;
}

interface UseSubmitActionArgs {
  reload: () => Promise<void>;
  api: NotificationApi;
  t: TFunction;
  failureTitleKey: ParseKeys;
}

export function useSubmitAction({ reload, api, t, failureTitleKey }: UseSubmitActionArgs) {
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
              title: t(failureTitleKey),
              description: getApiErrorMessage(e, t),
            });
          }
        } else {
          // Non-ApiError: network failure, AbortError, or a bug in the call
          // chain. Surface a generic toast so the user knows the action did
          // not succeed instead of silently leaving the modal open.
          api.error({
            title: t(failureTitleKey),
            description: t('errors.serverError'),
          });
        }
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    [api, reload, t, failureTitleKey],
  );

  return { isSubmitting, run };
}
