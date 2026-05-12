import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Modal,
  Space,
  Table,
  Typography,
  notification,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { ApiError, assetsApi } from '../api';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import { PAGE_SIZE_OPTIONS } from '../components/assets/constants';
import { getAssetColumns } from '../components/assets/columns';
import type { AssetRecord } from '../api/assets';
import AssetFormFields from '../components/assets/AssetFormFields';
import {
  createWarrantyExpiryValidator,
  normalizeAssetFormValues,
  type AssetFormValues,
} from '../components/assets/assetFormShared';

const AssetList: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [api, contextHolder] = notification.useNotification();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [assetForm] = Form.useForm<AssetFormValues>();

  const validatePurchaseAmount = createAmountValidator(t, { required: true });
  const validateWarrantyExpiry = useMemo(
    () => createWarrantyExpiryValidator(assetForm, t),
    [assetForm, t],
  );

  const formatApiError = (apiError: ApiError): string => getApiErrorMessage(apiError, t);

  const isManager = user?.role === 'manager';

  useEffect(() => {
    setPage(1);
  }, [user?.role]);

  useEffect(() => {
    if (!user) {
      return;
    }

    let cancelled = false;

    const loadAssets = async () => {
      setLoading(true);
      setError(null);
      try {
        const response =
          user.role === 'manager'
            ? await assetsApi.listAssets({ page, perPage: pageSize })
            : await assetsApi.listMyAssets({ page, perPage: pageSize });
        if (cancelled) {
          return;
        }
        setAssets(response.data);
        setTotal(response.meta.total);
      } catch (e) {
        if (cancelled) {
          return;
        }
        setAssets([]);
        setTotal(0);
        if (e instanceof ApiError) {
          setError(formatApiError(e));
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadAssets();

    return () => {
      cancelled = true;
    };
  }, [page, pageSize, t, user]);

  const reloadCurrentPage = async () => {
    if (!user) {
      return;
    }

    const response =
      user.role === 'manager'
        ? await assetsApi.listAssets({ page, perPage: pageSize })
        : await assetsApi.listMyAssets({ page, perPage: pageSize });
    setAssets(response.data);
    setTotal(response.meta.total);
  };

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
      await reloadCurrentPage();
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

  const actionsColumn: TableColumnsType<AssetRecord>[number] = {
    title: t('assetList.columns.actions'),
    key: 'actions',
    width: 110,
    render: (_: unknown, asset: AssetRecord) => (
      <Space size={4} wrap>
        <Button type="link" onClick={() => navigate(`/assets/${asset.id}`)}>
          {t('assetList.actions.detail')}
        </Button>
      </Space>
    ),
  };

  const columns: TableColumnsType<AssetRecord> = [...getAssetColumns(t), actionsColumn];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {contextHolder}
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      {error ? <Alert title={error} type="error" showIcon /> : null}

      <Card>
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {isManager ? (
            <Space>
              <Button type="primary" onClick={openCreateModal}>
                {t('assetList.manager.createButton')}
              </Button>
            </Space>
          ) : null}

          <Typography.Text type="secondary">
            {t('assetList.summary', { count: total })}
          </Typography.Text>

          <Table<AssetRecord>
            rowKey="id"
            loading={loading}
            dataSource={assets}
            columns={columns}
            locale={{
              emptyText: t('assetList.empty'),
            }}
            pagination={{
              current: page,
              pageSize,
              total,
              pageSizeOptions: PAGE_SIZE_OPTIONS.map(String),
              showSizeChanger: true,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage);
                setPageSize(nextPageSize);
              },
              showTotal: (total) => t('assetList.pagination.total', { count: total }),
            }}
            scroll={{ x: 1200 }}
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
        </Space>
      </Card>
    </Space>
  );
};

export default AssetList;
