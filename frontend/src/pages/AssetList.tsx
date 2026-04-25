import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Segmented, Select, Space, Table, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';

import { DUMMY_ASSETS, DUMMY_HOLDERS, type AssetRecord, type AssetStatus } from '../mocks/assets';

type ViewMode = 'manager' | 'holder';

const STATUS_COLORS: Record<AssetStatus, string> = {
  in_stock: 'default',
  in_use: 'success',
  pending_repair: 'processing',
  under_repair: 'warning',
  disposed: 'error',
};

const PAGE_SIZE_OPTIONS = [5, 10, 20];

const AssetList: React.FC = () => {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<ViewMode>('manager');
  const [holderId, setHolderId] = useState<string>(DUMMY_HOLDERS[0]?.id ?? '');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);

  const moneyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: 'TWD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }),
    [],
  );

  const filteredAssets = useMemo(() => {
    if (viewMode === 'manager') {
      return DUMMY_ASSETS;
    }
    return DUMMY_ASSETS.filter((asset) => asset.responsible_person_id === holderId);
  }, [holderId, viewMode]);

  useEffect(() => {
    setPage(1);
  }, [viewMode, holderId, pageSize]);

  const columns: TableColumnsType<AssetRecord> = [
    {
      title: t('assetList.columns.assetCode'),
      dataIndex: 'asset_code',
      key: 'asset_code',
      render: (value: string) => <span style={{ fontFamily: 'monospace' }}>{value}</span>,
      width: 150,
    },
    {
      title: t('assetList.columns.name'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      width: 210,
    },
    {
      title: t('assetList.columns.category'),
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: t('assetList.columns.department'),
      dataIndex: 'department',
      key: 'department',
      width: 130,
    },
    {
      title: t('assetList.columns.location'),
      dataIndex: 'location',
      key: 'location',
      width: 150,
    },
    {
      title: t('assetList.columns.status'),
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: AssetStatus) => (
        <Tag color={STATUS_COLORS[status]}>{t(`assetList.status.${status}`)}</Tag>
      ),
    },
    {
      title: t('assetList.columns.purchaseAmount'),
      dataIndex: 'purchase_amount',
      key: 'purchase_amount',
      width: 160,
      align: 'right',
      render: (amount: string) => {
        const parsed = Number.parseFloat(amount);
        return Number.isNaN(parsed) ? amount : moneyFormatter.format(parsed);
      },
    },
    {
      title: t('assetList.columns.purchaseDate'),
      dataIndex: 'purchase_date',
      key: 'purchase_date',
      width: 150,
      render: (value: string) => {
        const parsed = new Date(value);
        return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
      },
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      <Alert message={t('assetList.dataSourceNotice')} type="info" showIcon />

      <Card>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Typography.Text strong>{t('assetList.roleLabel')}</Typography.Text>
            <Segmented<ViewMode>
              value={viewMode}
              onChange={(value) => setViewMode(value)}
              options={[
                { label: t('assetList.mode.manager'), value: 'manager' },
                { label: t('assetList.mode.holder'), value: 'holder' },
              ]}
            />
            {viewMode === 'holder' ? (
              <>
                <Typography.Text strong>{t('assetList.holderLabel')}</Typography.Text>
                <Select
                  value={holderId}
                  onChange={setHolderId}
                  options={DUMMY_HOLDERS.map((holder) => ({
                    label: holder.label,
                    value: holder.id,
                  }))}
                  style={{ width: 220 }}
                  placeholder={t('assetList.holderPlaceholder')}
                />
              </>
            ) : null}
          </Space>

          <Typography.Text type="secondary">
            {t('assetList.summary', { count: filteredAssets.length })}
          </Typography.Text>

          <Table<AssetRecord>
            rowKey="id"
            dataSource={filteredAssets}
            columns={columns}
            locale={{
              emptyText: t('assetList.empty'),
            }}
            pagination={{
              current: page,
              pageSize,
              total: filteredAssets.length,
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
        </Space>
      </Card>
    </Space>
  );
};

export default AssetList;
