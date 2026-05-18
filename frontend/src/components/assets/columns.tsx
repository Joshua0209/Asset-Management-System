import React from 'react';
import { Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import type { TFunction } from 'i18next';
import type { AssetCategory, AssetRecord, AssetStatus } from '@/api/assets';
import { STATUS_COLORS } from './constants';
import { formatDateValue, formatAmountValue } from '@/utils/format';
import {
  normalizeAssetCategoryLiteral,
  type AssetSortField,
  type AssetSortState,
} from './listControls';

function getSortOrder(
  sortState: AssetSortState | null,
  field: AssetSortField,
): 'ascend' | 'descend' | null {
  if (!sortState || sortState.field !== field) {
    return null;
  }

  return sortState.order;
}

function toCategoryFallbackLabel(value: string): string {
  const normalized = normalizeAssetCategoryLiteral(value);
  return normalized.replace(/_/g, ' ');
}

export const getAssetColumns = (
  t: TFunction,
  sortState: AssetSortState | null,
): TableColumnsType<AssetRecord> => [
  {
    title: t('assetList.columns.assetCode'),
    dataIndex: 'asset_code',
    key: 'asset_code',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'asset_code'),
    render: (value: string) => <span style={{ fontFamily: 'monospace' }}>{value}</span>,
    width: 150,
  },
  {
    title: t('assetList.columns.name'),
    dataIndex: 'name',
    key: 'name',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'name'),
    ellipsis: true,
    width: 210,
  },
  {
    title: t('assetList.columns.category'),
    dataIndex: 'category',
    key: 'category',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'category'),
    render: (value: string) => {
      const normalizedCategory = normalizeAssetCategoryLiteral(value);
      return t(`assetList.category.${normalizedCategory as AssetCategory}`, {
        defaultValue: toCategoryFallbackLabel(normalizedCategory),
      });
    },
    width: 120,
  },
  {
    title: t('assetList.columns.department'),
    dataIndex: 'department',
    key: 'department',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'department'),
    width: 130,
  },
  {
    title: t('assetList.columns.location'),
    dataIndex: 'location',
    key: 'location',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'location'),
    width: 150,
  },
  {
    title: t('assetList.columns.status'),
    dataIndex: 'status',
    key: 'status',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'status'),
    width: 140,
    render: (status: AssetStatus) => (
      <Tag color={STATUS_COLORS[status]}>{t(`assetList.status.${status}`)}</Tag>
    ),
  },
  {
    title: t('assetList.columns.purchaseAmount'),
    dataIndex: 'purchase_amount',
    key: 'purchase_amount',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'purchase_amount'),
    width: 160,
    align: 'right',
    render: (amount: string) => formatAmountValue(amount),
  },
  {
    title: t('assetList.columns.purchaseDate'),
    dataIndex: 'purchase_date',
    key: 'purchase_date',
    sorter: true,
    sortOrder: getSortOrder(sortState, 'purchase_date'),
    width: 150,
    render: (value: string) => formatDateValue(value, t),
  },
];
