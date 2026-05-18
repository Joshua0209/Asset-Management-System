import { useCallback } from 'react';
import type { TFunction } from 'i18next';
import { assetsApi } from '@/api';
import type { AssetUpdatePayload } from '@/api/assets';
import { useSubmitAction } from '@/hooks/useSubmitAction';

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
  const { isSubmitting, run } = useSubmitAction({
    reload,
    api,
    t,
    failureTitleKey: 'assetList.manager.actionFailedTitle',
  });

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
