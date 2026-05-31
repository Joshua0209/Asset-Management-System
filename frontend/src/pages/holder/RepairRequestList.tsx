import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Space,
  Table,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { PlusOutlined } from '@ant-design/icons';

import { ApiError, repairRequestsApi } from '@/api';
import type { RepairRequestRecord } from '@/api/repair-requests';
import {
  buildCreatedAtColumn,
  buildStatusColumn,
  renderRequestAssetCell,
  renderRequestIdCell,
} from '@/components/repair-requests/columns';

const PAGE_SIZE_OPTIONS = [10, 20, 50];

const RepairRequestList: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [requests, setRequests] = useState<RepairRequestRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[1]);

  useEffect(() => {
    let cancelled = false;

    const loadRequests = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await repairRequestsApi.listRepairRequests({
          page,
          perPage: pageSize,
          sort: '-created_at',
        });
        if (cancelled) return;
        setRequests(response.data);
        setTotal(response.meta.total);
      } catch (e) {
        if (cancelled) return;
        setRequests([]);
        setTotal(0);
        if (e instanceof ApiError) {
          setError(e.message);
        } else {
          setError(t('errors.serverError'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void loadRequests();

    return () => {
      cancelled = true;
    };
  }, [page, pageSize, t]);

  const columns: TableColumnsType<RepairRequestRecord> = [
    {
      title: t('repairRequestList.columns.id'),
      dataIndex: 'repair_id',
      key: 'repair_id',
      render: (repairId: string) => renderRequestIdCell(repairId),
      width: 160,
    },
    {
      title: t('repairRequestList.columns.asset'),
      key: 'asset',
      render: (_, record) => renderRequestAssetCell(record.asset),
      width: 200,
    },
    buildStatusColumn(t('repairRequestList.columns.status'), t, 'repairRequestList.status'),
    buildCreatedAtColumn(t('repairRequestList.columns.createdAt')),
    {
      title: t('repairRequestList.columns.actions'),
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button type="link" onClick={() => navigate(`/repairs/${record.id}`)}>
          {t('assetList.actions.detail')}
        </Button>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          {t('repairRequestList.title')}
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/repairs/new')}
        >
          {t('repairRequestList.submitNew')}
        </Button>
      </div>

      {error ? <Alert title={error} type="error" showIcon /> : null}

      <Card styles={{ body: { padding: 0 } }}>
        <Table<RepairRequestRecord>
          rowKey="id"
          loading={loading}
          dataSource={requests}
          columns={columns}
          pagination={{
            current: page,
            pageSize,
            total,
            pageSizeOptions: PAGE_SIZE_OPTIONS.map(String),
            showSizeChanger: true,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
            showTotal: (total) => t('assetList.pagination.total', { count: total }),
          }}
          scroll={{ x: 800 }}
        />
      </Card>
    </Space>
  );
};

export default RepairRequestList;
