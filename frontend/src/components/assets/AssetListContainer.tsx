import React from 'react';
import { Alert, Card, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import AssetTable from './AssetTable';
import type { AssetRecord } from '../../api/assets';

interface AssetListContainerProps {
  assets: AssetRecord[];
  loading: boolean;
  total: number;
  error: string | null;
  page: number;
  pageSize: number;
  onPaginationChange: (page: number, pageSize: number) => void;
}

const AssetListContainer: React.FC<AssetListContainerProps> = ({
  assets,
  loading,
  total,
  error,
  page,
  pageSize,
  onPaginationChange,
}) => {
  const { t } = useTranslation();

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
            onPaginationChange={onPaginationChange}
          />
        </Space>
      </Card>
    </Space>
  );
};

export default AssetListContainer;
