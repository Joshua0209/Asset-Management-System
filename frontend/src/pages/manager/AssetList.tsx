import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Form, Modal, Space, notification } from 'antd';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/auth/AuthContext';
import { ApiError, assetsApi } from '@/api';
import { getApiErrorMessage } from '@/utils/apiErrors';
import { createAmountValidator } from '@/utils/validators';
import type { ListAssetsParams } from '@/api/assets';
import AssetFormFields from '@/components/assets/AssetFormFields';
import AssetListContainer from '@/components/assets/AssetListContainer';
import { useAssetList } from '@/hooks/useAssetList';
import {
  createWarrantyExpiryValidator,
  normalizeAssetFormValues,
  type AssetFormValues,
} from '@/components/assets/assetFormShared';

const AssetList: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [api, contextHolder] = notification.useNotification();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [assetForm] = Form.useForm<AssetFormValues>();

  const validatePurchaseAmount = createAmountValidator(t, { required: true });
  const validateWarrantyExpiry = useMemo(
    () => createWarrantyExpiryValidator(assetForm, t),
    [assetForm, t],
  );

  const formatApiError = React.useCallback(
    (apiError: ApiError): string => getApiErrorMessage(apiError, t),
    [t],
  );

  const isManager = user?.role === 'manager';

  const fetchFn = useCallback(
    (params: ListAssetsParams) =>
      user?.role === 'manager' ? assetsApi.listAssets(params) : assetsApi.listMyAssets(params),
    [user?.role],
  );

  const {
    assets,
    total,
    loading,
    error,
    page,
    pageSize,
    setPage,
    setPageSize,
    filters,
    onFilterChange,
    onResetFilters,
    sortState,
    onSortChange,
    resetQueryState,
    reload,
  } = useAssetList({
    fetchFn,
    enabled: Boolean(user),
  });

  useEffect(() => {
    resetQueryState();
  }, [resetQueryState, user?.role]);

  const openCreateModal = () => {
    assetForm.resetFields();
    setIsAssetModalOpen(true);
  };

  const handleSaveAsset = async () => {
    try {
      const values = await assetForm.validateFields();
      const payload = normalizeAssetFormValues(values);
      setIsSubmitting(true);

      await assetsApi.createAsset(payload);

      setIsAssetModalOpen(false);
      reload();
      api.success({ title: t('assetList.manager.createSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const actions = isManager ? (
    <Space>
      <Button type="primary" onClick={openCreateModal}>
        {t('assetList.manager.createButton')}
      </Button>
    </Space>
  ) : null;

  return (
    <>
      {contextHolder}
      <AssetListContainer
        assets={assets}
        loading={loading}
        total={total}
        error={error}
        page={page}
        pageSize={pageSize}
        filters={filters}
        sortState={sortState}
        isManager={isManager}
        actions={actions}
        onFilterChange={onFilterChange}
        onResetFilters={onResetFilters}
        onPaginationChange={(nextPage, nextPageSize) => {
          setPage(nextPage);
          setPageSize(nextPageSize);
        }}
        onSortChange={onSortChange}
      />

      <Modal
        open={isAssetModalOpen}
        title={t('assetList.manager.createTitle')}
        onCancel={() => setIsAssetModalOpen(false)}
        onOk={() => void handleSaveAsset()}
        okText={t('common.button.save')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
        forceRender
      >
        <Form form={assetForm} layout="vertical">
          <AssetFormFields
            t={t}
            validatePurchaseAmount={validatePurchaseAmount}
            validateWarrantyExpiry={validateWarrantyExpiry}
          />
        </Form>
      </Modal>
    </>
  );
};

export default AssetList;
