import React, { useEffect, useState } from 'react';
import { Alert, Card, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { assetsApi, ApiError } from '../api';
import type { AssetRecord } from '../api/assets';
import AssetTable from '../components/assets/AssetTable';
import { PAGE_SIZE_OPTIONS } from '../components/assets/constants';

const MyAssetList: React.FC = () => {
  const { t } = useTranslation();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);

  useEffect(() => {
    let cancelled = false;

    const loadAssets = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await assetsApi.listMyAssets({ page, perPage: pageSize });
        if (cancelled) return;
        setAssets(response.data);
        setTotal(response.meta.total);
      } catch (e) {
        if (cancelled) return;
        setAssets([]);
        setTotal(0);
        if (e instanceof ApiError) {
          setError(e.message);
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
  }, [page, pageSize, t]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      {error ? <Alert message={error} type="error" showIcon /> : null}

      <Card>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            {t('assetList.summary', { count: total })}
          </Typography.Text>

          <AssetTable
            assets={assets}
            loading={loading}
            total={total}
            page={page}
            pageSize={pageSize}
            onPaginationChange={(nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            }}
          />
        </Space>
      </Card>
    </Space>
  );
};

export default MyAssetList;
