import React from 'react';
import { Alert, Card, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import AssetTable from './AssetTable';
import type { AssetRecord } from '@/api/assets';
import AssetFilterBar from './AssetFilterBar';
import type { AssetListFilters, AssetSortState } from './listControls';

interface AssetListContainerProps {
  assets: AssetRecord[];
  loading: boolean;
  total: number;
  error: string | null;
  page: number;
  pageSize: number;
  filters: AssetListFilters;
  sortState: AssetSortState | null;
  isManager: boolean;
  actions?: React.ReactNode;
  onFilterChange: <K extends keyof AssetListFilters>(field: K, value: AssetListFilters[K]) => void;
  onResetFilters: () => void;
  onPaginationChange: (page: number, pageSize: number) => void;
  onSortChange: (sortState: AssetSortState | null) => void;
}

const AssetListContainer: React.FC<AssetListContainerProps> = ({
  assets,
  loading,
  total,
  error,
  page,
  pageSize,
  filters,
  sortState,
  isManager,
  actions,
  onFilterChange,
  onResetFilters,
  onPaginationChange,
  onSortChange,
}) => {
  const { t } = useTranslation();

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      {error ? <Alert title={error} type="error" showIcon /> : null}

      <Card>
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {actions}

          <AssetFilterBar
            filters={filters}
            isManager={isManager}
            onFilterChange={onFilterChange}
            onResetFilters={onResetFilters}
          />

          <Typography.Text type="secondary">
            {t('assetList.summary', { count: total })}
          </Typography.Text>

          <AssetTable
            assets={assets}
            loading={loading}
            total={total}
            page={page}
            pageSize={pageSize}
            sortState={sortState}
            onPaginationChange={onPaginationChange}
            onSortChange={onSortChange}
          />
        </Space>
      </Card>
    </Space>
  );
};

export default AssetListContainer;
