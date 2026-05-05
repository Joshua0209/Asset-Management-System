import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Result,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { assetsApi, ApiError } from '../api';
import type { AssetRecord } from '../api/assets';
import { STATUS_COLORS } from '../components/assets/constants';
import { formatDateValue, formatAmountValue } from '../utils/format';

const AssetDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    const loadAsset = async () => {
      setLoading(true);
      setError(null);
      setStatus(null);
      try {
        const data = await assetsApi.getAssetById(id);
        if (cancelled) return;
        setAsset(data);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setError(e.message);
          setStatus(e.status);
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadAsset();

    return () => {
      cancelled = true;
    };
  }, [id, t]);

  if (loading) {
    return (
      <Card>
        <Skeleton active title paragraph={{ rows: 10 }} />
      </Card>
    );
  }

  if (status === 404) {
    return (
      <Result
        status="404"
        title="404"
        subTitle={t('assetList.error.notFound')}
        extra={<Button type="primary" onClick={() => navigate(-1)}>{t('common.button.back')}</Button>}
      />
    );
  }

  if (status === 403) {
    return (
      <Result
        status="403"
        title="403"
        subTitle={t('assetList.error.forbidden')}
        extra={<Button type="primary" onClick={() => navigate(-1)}>{t('common.button.back')}</Button>}
      />
    );
  }

  if (error || !asset) {
    return <Alert message={error || t('assetList.serverError')} type="error" showIcon />;
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
        {t('common.button.back')}
      </Button>

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
    </Space>
  );
};

export default AssetDetail;
