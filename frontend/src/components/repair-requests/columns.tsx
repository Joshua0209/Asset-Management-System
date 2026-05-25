import React from 'react';
import { Space, Tag, Typography } from 'antd';
import type { TFunction } from 'i18next';

import type { RepairRequestRecord, RepairRequestStatus } from '@/api/repair-requests';
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
