import { useCallback, useState } from 'react';
import { Modal } from 'antd';
import type { ParseKeys, TFunction } from 'i18next';
import { ApiError, assetsApi } from '@/api';
import { getApiErrorMessage } from '@/utils/apiErrors';
import type { AssetUpdatePayload } from '@/api/assets';

export interface AssignValues {
  responsible_person_id: string;
  assignment_date: string;
}

export interface UnassignValues {
  reason: string;
  unassignment_date: string;
}

export interface DisposeValues {
  disposal_reason: string;
}

interface NotificationApi {
  success: (config: { title: string }) => void;
  error: (config: { title: string; description?: string }) => void;
}

interface UseAssetActionsArgs {
  assetId: string;
  version: number;
  reload: () => Promise<void>;
  api: NotificationApi;
  t: TFunction;
}

export function useAssetActions({ assetId, version, reload, api, t }: UseAssetActionsArgs) {
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
              title: t('assetList.manager.actionFailedTitle'),
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

  const updateAsset = useCallback(
    (payload: Omit<AssetUpdatePayload, 'version'>) =>
      run(
        () => assetsApi.updateAsset(assetId, { ...payload, version }),
        'assetList.manager.editSuccess',
      ),
    [assetId, version, run],
  );

  const assignAsset = useCallback(
    (values: AssignValues) =>
      run(
        () => assetsApi.assignAsset(assetId, { ...values, version }),
        'assetList.manager.assignSuccess',
      ),
    [assetId, version, run],
  );

  const unassignAsset = useCallback(
    (values: UnassignValues) =>
      run(
        () => assetsApi.unassignAsset(assetId, { ...values, version }),
        'assetList.manager.unassignSuccess',
      ),
    [assetId, version, run],
  );

  const disposeAsset = useCallback(
    (values: DisposeValues) =>
      run(
        () => assetsApi.disposeAsset(assetId, { ...values, version }),
        'assetList.manager.disposeSuccess',
      ),
    [assetId, version, run],
  );

  return { isSubmitting, updateAsset, assignAsset, unassignAsset, disposeAsset };
}
