import React from 'react';
import { Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import type { TFunction } from 'i18next';
import type { AssetRecord, AssetStatus } from '../../api/assets';
import { STATUS_COLORS } from './constants';
import { getAssetCategoryLabel } from './assetFormShared';
import { formatDateValue, formatAmountValue } from '../../utils/format';

export const getAssetColumns = (t: TFunction): TableColumnsType<AssetRecord> => [
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
    render: (category: string) => getAssetCategoryLabel(t, category),
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
];
