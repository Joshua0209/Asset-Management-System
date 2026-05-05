import React from 'react';
import { Button, Table, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { AssetRecord, AssetStatus } from '../../api/assets';
import { STATUS_COLORS, PAGE_SIZE_OPTIONS } from './constants';
import { formatDateValue, formatAmountValue } from '../../utils/format';

interface AssetTableProps {
  assets: AssetRecord[];
  loading: boolean;
  total: number;
  page: number;
  pageSize: number;
  onPaginationChange: (page: number, pageSize: number) => void;
  /** Optional extra columns to append to the default columns (e.g., manager actions) */
  extraColumns?: TableColumnsType<AssetRecord>;
}

const AssetTable: React.FC<AssetTableProps> = ({
  assets,
  loading,
  total,
  page,
  pageSize,
  onPaginationChange,
  extraColumns = [],
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const defaultColumns: TableColumnsType<AssetRecord> = [
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
      render: (amount: string) => formatAmountValue(amount),
    },
    {
      title: t('assetList.columns.purchaseDate'),
      dataIndex: 'purchase_date',
      key: 'purchase_date',
      width: 150,
      render: (value: string) => formatDateValue(value, t),
    },
    {
      title: t('assetList.columns.actions'),
      key: 'actions',
      width: 110,
      render: (_: unknown, asset: AssetRecord) => (
        <Button type="link" onClick={() => navigate(`/assets/${asset.id}`)}>
          {t('assetList.actions.detail')}
        </Button>
      ),
    },
  ];

  const columns = [...defaultColumns, ...extraColumns];

  return (
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
        onChange: onPaginationChange,
        showTotal: (totalCount) => t('assetList.pagination.total', { count: totalCount }),
      }}
      scroll={{ x: 1200 }}
    />
  );
};

export default AssetTable;
