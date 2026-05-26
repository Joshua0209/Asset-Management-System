import React from 'react';
import { Space, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import type { TFunction } from 'i18next';

import type { RepairRequestRecord, RepairRequestStatus } from '@/api/repair-requests';
import { formatDateTime } from '@/utils/format';
import { REPAIR_REQUEST_STATUS_COLORS } from './constants';

const ID_PREFIX_LENGTH = 8;

export const renderRequestIdCell = (id: string): React.ReactNode => (
  <span className="asset-code">
    {id.slice(0, ID_PREFIX_LENGTH)}...
  </span>
);

export const renderRequestAssetCell = (
  asset: RepairRequestRecord['asset'],
): React.ReactNode => (
  <Space orientation="vertical" size={0}>
    <Typography.Text strong>{asset.name}</Typography.Text>
    <Typography.Text className="asset-code muted-small">
      {asset.asset_code}
    </Typography.Text>
  </Space>
);

type RepairRequestStatusKeyPrefix = 'repairRequestList.status' | 'reviews.status';

export const renderRequestStatusTag = (
  status: RepairRequestStatus,
  t: TFunction,
  statusKeyPrefix: RepairRequestStatusKeyPrefix,
): React.ReactNode => (
  <Tag color={REPAIR_REQUEST_STATUS_COLORS[status]}>
    {t(`${statusKeyPrefix}.${status}`)}
  </Tag>
);

type RepairRequestColumn = TableColumnsType<RepairRequestRecord>[number];

// Both the manager Reviews page and the holder RepairRequestList page render
// identical status and createdAt columns — only the i18n key prefix differs.
// Factor them out so the two tables can never drift in width or formatter.
// Callers pass the already-translated title so the typed `t()` keys stay
// pinned to the call site rather than being widened to plain string here.
export function buildStatusColumn(
  title: string,
  t: TFunction,
  statusKeyPrefix: RepairRequestStatusKeyPrefix,
): RepairRequestColumn {
  return {
    title,
    dataIndex: 'status',
    key: 'status',
    width: 140,
    render: (status: RepairRequestStatus) =>
      renderRequestStatusTag(status, t, statusKeyPrefix),
  };
}

export function buildCreatedAtColumn(title: string): RepairRequestColumn {
  return {
    title,
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180,
    render: (value: string) => (
      <span className="tabular-nums">{formatDateTime(value)}</span>
    ),
  };
}
