import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  notification,
  Result,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/AuthContext';
import { assetsApi, ApiError, usersApi } from '@/api';
import { getApiErrorMessage } from '@/utils/apiErrors';
import type { AssetRecord } from '@/api/assets';
import type { UserRecord } from '@/api/users';
import { STATUS_COLORS } from '@/components/assets/constants';
import { formatDateValue, formatAmountValue } from '@/utils/format';
import type { AssetFormPayload } from '@/components/assets/assetFormShared';

import EditAssetModal from './EditAssetModal';
import AssignAssetModal, { type AssignFormValues } from './AssignAssetModal';
import DisposeAssetModal, { type DisposeFormValues } from './DisposeAssetModal';
import { useAssetActions } from './useAssetActions';

const pageContainerStyle: React.CSSProperties = {
  maxWidth: 1200,
  margin: '0 auto',
};

const AssetDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user } = useAuth();
  const [api, contextHolder] = notification.useNotification();
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [holders, setHolders] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false);
  const [isDisposeModalOpen, setIsDisposeModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);

  const isManager = user?.role === 'manager';

  const loadAsset = useCallback(
    async (showLoading = true) => {
      if (!id) {
        return;
      }

      if (showLoading) {
        setLoading(true);
      }

      setError(null);
      setStatus(null);

      try {
        const data = await assetsApi.getAssetById(id);
        setAsset(data);
      } catch (e) {
        if (e instanceof ApiError) {
          setError(e.message);
          setStatus(e.status);
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [id, t],
  );

  useEffect(() => {
    if (!id) {
      return;
    }
    loadAsset();
  }, [id, loadAsset]);

  useEffect(() => {
    if (!isManager) {
      setHolders([]);
      return;
    }

    let cancelled = false;
    const loadHolders = async () => {
      try {
        const response = await usersApi.listUsers({ page: 1, perPage: 100, role: 'holder' });
        if (!cancelled) {
          setHolders(response.data);
        }
      } catch (e) {
        if (!cancelled && e instanceof ApiError) {
          api.error({
            title: t('assetList.manager.holdersLoadErrorTitle'),
            description: getApiErrorMessage(e, t),
          });
        }
      }
    };

    void loadHolders();

    return () => {
      cancelled = true;
    };
  }, [api, isManager, t]);

  const reloadSilently = useCallback(() => loadAsset(false), [loadAsset]);

  const { isSubmitting, updateAsset, assignAsset, unassignAsset, disposeAsset } = useAssetActions({
    assetId: asset?.id ?? '',
    version: asset?.version ?? 0,
    reload: reloadSilently,
    api,
    t,
  });

  const handleEditSubmit = async (payload: AssetFormPayload) => {
    if (await updateAsset(payload)) setIsEditModalOpen(false);
  };

  const handleAssignSubmit = async (values: AssignFormValues) => {
    if (!asset) {
      return;
    }
    const ok =
      asset.status === 'in_use'
        ? await unassignAsset({
            reason: values.reason ?? '',
            unassignment_date: values.unassignment_date ?? '',
          })
        : await assignAsset({
            responsible_person_id: values.responsible_person_id ?? '',
            assignment_date: values.assignment_date ?? '',
          });
    if (ok) setIsAssignModalOpen(false);
  };

  const handleDisposeSubmit = async (values: DisposeFormValues) => {
    if (await disposeAsset(values)) setIsDisposeModalOpen(false);
  };

  const renderContent = () => {
    if (loading) {
      return (
        <Card>
          <Skeleton active title paragraph={{ rows: 10 }} />
        </Card>
      );
    }

    if (status === 404) {
      return (
        <Card>
          <Result
            status="404"
            title="404"
            subTitle={t('assetList.error.notFound')}
            extra={
              <Button type="primary" onClick={() => navigate(-1)}>
                {t('common.button.back')}
              </Button>
            }
          />
        </Card>
      );
    }

    if (status === 403) {
      return (
        <Card>
          <Result
            status="403"
            title="403"
            subTitle={t('assetList.error.forbidden')}
            extra={
              <Button type="primary" onClick={() => navigate(-1)}>
                {t('common.button.back')}
              </Button>
            }
          />
        </Card>
      );
    }

    if (error || !asset) {
      return <Alert title={error || t('assetList.serverError')} type="error" showIcon />;
    }

    return (
      <Card
        title={
          <Space>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {t('assetList.detail.title', { assetCode: asset.asset_code })}
            </Typography.Title>
            <Tag color={STATUS_COLORS[asset.status]}>{t(`assetList.status.${asset.status}`)}</Tag>
          </Space>
        }
      >
        <Descriptions column={{ xxl: 3, xl: 3, lg: 2, md: 2, sm: 1, xs: 1 }} bordered>
          <Descriptions.Item label={t('assetList.columns.assetCode')}>
            {asset.asset_code}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.name')}>
            {asset.name}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.category')}>
            {asset.category}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.holder')}>
            {asset.responsible_person?.name ?? t('assetList.detail.unassigned')}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.assignmentDate')}>
            {formatDateValue(asset.assignment_date, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.unassignmentDate')}>
            {formatDateValue(asset.unassignment_date, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.model')}>
            {asset.model}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.specs')}>
            {asset.specs ?? t('assetList.detail.notAvailable')}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.supplier')}>
            {asset.supplier}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.activationDate')}>
            {formatDateValue(asset.activation_date, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.warrantyExpiry')}>
            {formatDateValue(asset.warranty_expiry, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.department')}>
            {asset.department}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.location')}>
            {asset.location}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.purchaseAmount')}>
            {formatAmountValue(asset.purchase_amount)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.purchaseDate')}>
            {formatDateValue(asset.purchase_date, t)}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    );
  };

  return (
    <div style={pageContainerStyle}>
      {contextHolder}
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          {t('common.button.back')}
        </Button>

        {isManager && asset ? (
          <Space wrap>
            <Button onClick={() => setIsEditModalOpen(true)}>{t('assetList.actions.edit')}</Button>

            {asset.status === 'in_stock' ? (
              <Button onClick={() => setIsAssignModalOpen(true)}>{t('assetList.actions.assign')}</Button>
            ) : null}

            {asset.status === 'in_use' ? (
              <Button onClick={() => setIsAssignModalOpen(true)}>{t('assetList.actions.unassign')}</Button>
            ) : null}

            {asset.status === 'in_stock' ? (
              <Button danger onClick={() => setIsDisposeModalOpen(true)}>{t('assetList.actions.dispose')}</Button>
            ) : null}
          </Space>
        ) : null}

        {renderContent()}

        {asset ? (
          <>
            <EditAssetModal
              open={isEditModalOpen}
              asset={asset}
              isSubmitting={isSubmitting}
              onCancel={() => setIsEditModalOpen(false)}
              onSubmit={handleEditSubmit}
            />
            <AssignAssetModal
              open={isAssignModalOpen}
              asset={asset}
              holders={holders}
              isSubmitting={isSubmitting}
              onCancel={() => setIsAssignModalOpen(false)}
              onSubmit={handleAssignSubmit}
            />
            <DisposeAssetModal
              open={isDisposeModalOpen}
              asset={asset}
              isSubmitting={isSubmitting}
              onCancel={() => setIsDisposeModalOpen(false)}
              onSubmit={handleDisposeSubmit}
            />
          </>
        ) : null}
      </Space>
    </div>
  );
};

export default AssetDetail;
