import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ApiError, repairRequestsApi } from '../../api';
import { getApiErrorMessage } from '../../utils/apiErrors';
import type {
  RepairRequestRecord,
  RepairRequestStatus,
} from '../../api/repair-requests';

const PAGE_SIZE_OPTIONS = [5, 10, 20];

const STATUS_COLORS: Record<RepairRequestStatus, string> = {
  pending_review: 'warning',
  under_repair: 'processing',
  completed: 'success',
  rejected: 'error',
};

const Reviews: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [requests, setRequests] = useState<RepairRequestRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [statusFilter, setStatusFilter] = useState<RepairRequestStatus | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formatApiError = React.useCallback(
    (apiError: ApiError): string => getApiErrorMessage(apiError, t),
    [t],
  );

  const loadRequests = React.useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await repairRequestsApi.listRepairRequests({
        page,
        perPage: pageSize,
        status: statusFilter,
      });
      setRequests(response.data);
      setTotal(response.meta.total);
    } catch (e) {
      setRequests([]);
      setTotal(0);
      if (e instanceof ApiError) {
        setError(formatApiError(e));
      } else {
        setError(t('reviews.loadError'));
      }
    } finally {
      setLoading(false);
    }
  }, [formatApiError, page, pageSize, statusFilter, t]);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  const columns: TableColumnsType<RepairRequestRecord> = [
    {
      title: t('reviews.columns.assetCode'),
      key: 'asset_code',
      render: (_: unknown, record) => record.asset.asset_code,
      width: 160,
    },
    {
      title: t('reviews.columns.assetName'),
      key: 'asset_name',
      render: (_: unknown, record) => record.asset.name,
      width: 220,
    },
    {
      title: t('reviews.columns.requester'),
      key: 'requester',
      render: (_: unknown, record) => record.requester.name,
      width: 160,
    },
    {
      title: t('reviews.columns.status'),
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: RepairRequestStatus) => (
        <Tag color={STATUS_COLORS[status]}>{t(`reviews.status.${status}`)}</Tag>
      ),
    },
    {
      title: t('reviews.columns.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: t('reviews.columns.actions'),
      key: 'actions',
      width: 140,
      render: (_: unknown, record) => (
        <Space size={4} wrap>
          <Button type="link" onClick={() => navigate(`/reviews/${record.id}`)}>
            {t('assetList.actions.detail')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('reviews.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('reviews.description')}
      </Typography.Paragraph>

      {error ? <Alert type="error" message={error} showIcon /> : null}

      <Space>
        <Select
          allowClear
          placeholder={t('reviews.filter.statusPlaceholder')}
          value={statusFilter}
          onChange={(value) => {
            setPage(1);
            setStatusFilter(value);
          }}
          style={{ width: 220 }}
          options={[
            { value: 'pending_review', label: t('reviews.status.pending_review') },
            { value: 'under_repair', label: t('reviews.status.under_repair') },
            { value: 'completed', label: t('reviews.status.completed') },
            { value: 'rejected', label: t('reviews.status.rejected') },
          ]}
        />
      </Space>

      <Table<RepairRequestRecord>
        rowKey="id"
        loading={loading}
        dataSource={requests}
        columns={columns}
        locale={{ emptyText: t('reviews.empty') }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZE_OPTIONS.map(String),
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage);
            setPageSize(nextPageSize);
          },
          showTotal: (count) => t('reviews.pagination.total', { count }),
        }}
      />
    </Space>
  );
};

export default Reviews;
