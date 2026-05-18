import React from 'react';
import { Button, Table } from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { AssetRecord } from '@/api/assets';
import { PAGE_SIZE_OPTIONS } from './constants';
import { getAssetColumns } from './columns';
import {
  isAssetSortField,
  type AssetSortState,
} from './listControls';

interface AssetTableProps {
  assets: AssetRecord[];
  loading: boolean;
  total: number;
  page: number;
  pageSize: number;
  sortState: AssetSortState | null;
  onPaginationChange: (page: number, pageSize: number) => void;
  onSortChange: (sortState: AssetSortState | null) => void;
  /** Optional extra columns to append to the default columns (e.g., manager actions) */
  extraColumns?: TableColumnsType<AssetRecord>;
}

const AssetTable: React.FC<AssetTableProps> = ({
  assets,
  loading,
  total,
  page,
  pageSize,
  sortState,
  onPaginationChange,
  onSortChange,
  extraColumns = [],
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const actionsColumn: TableColumnsType<AssetRecord>[number] = {
    title: t('assetList.columns.actions'),
    key: 'actions',
    width: 110,
    render: (_: unknown, asset: AssetRecord) => (
      <Button type="link" onClick={() => navigate(`/assets/${asset.id}`)}>
        {t('assetList.actions.detail')}
      </Button>
    ),
  };

  const columns = [...getAssetColumns(t, sortState), actionsColumn, ...extraColumns];

  return (
    <Table<AssetRecord>
      rowKey="id"
      loading={loading}
      dataSource={assets}
      columns={columns}
      onChange={(_pagination, _filters, sorter) => {
        const singleSorter = Array.isArray(sorter) ? sorter[0] : sorter;
        const nextOrder = singleSorter?.order;
        const nextField = singleSorter?.columnKey;

        const nextSortState =
          nextOrder && isAssetSortField(nextField)
            ? {
                field: nextField,
                order: nextOrder,
              }
            : null;

        const unchanged =
          (sortState === null && nextSortState === null) ||
          (sortState !== null &&
            nextSortState !== null &&
            sortState.field === nextSortState.field &&
            sortState.order === nextSortState.order);

        if (unchanged) {
          return;
        }

        onSortChange(nextSortState);
      }}
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
