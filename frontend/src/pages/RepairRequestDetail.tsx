import React, { useEffect, useState } from 'react';
import {
  Alert,
  Breadcrumb,
  Card,
  Col,
  Descriptions,
  Divider,
  Image,
  Row,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';
import { ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, ToolOutlined } from '@ant-design/icons';

import { ApiError, repairRequestsApi } from '../api';
import type { RepairRequestRecord } from '../api/repair-requests';

const RepairRequestDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [request, setRequest] = useState<RepairRequestRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const formatDate = (value: string | null): string => {
    if (!value) return '-';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  };

  useEffect(() => {
    if (!id) return;

    const loadRequest = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await repairRequestsApi.getRepairRequestById(id);
        setRequest(data);
      } catch (e) {
        if (e instanceof ApiError) {
          setError(e.message);
        } else {
          setError(t('errors.serverError'));
        }
      } finally {
        setLoading(false);
      }
    };

    void loadRequest();
  }, [id, t]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error || !request) {
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Breadcrumb items={[{ title: <Link to="/repairs">{t('repairRequestList.title')}</Link> }, { title: t('assetList.actions.detail') }]} />
        <Alert message={error || t('errors.notFound')} type="error" showIcon />
      </Space>
    );
  }

  const getTimelineItems = () => {
    const items = [
      {
        children: t('repairRequestList.status.pending_review'),
        color: 'blue',
        dot: <ClockCircleOutlined />,
        label: formatDate(request.created_at),
      },
    ];

    if (request.status === 'under_repair' || request.status === 'completed') {
      items.push({
        children: t('repairRequestList.status.under_repair'),
        color: 'orange',
        dot: <ToolOutlined />,
        label: request.updated_at ? formatDate(request.updated_at) : '',
      });
    }

    if (request.status === 'completed') {
      items.push({
        children: t('repairRequestList.status.completed'),
        color: 'green',
        dot: <CheckCircleOutlined />,
        label: formatDate(request.completed_at),
      });
    }

    if (request.status === 'rejected') {
      items.push({
        children: t('repairRequestList.status.rejected'),
        color: 'red',
        dot: <CloseCircleOutlined />,
        label: formatDate(request.updated_at),
      });
    }

    return items;
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Breadcrumb items={[{ title: <Link to="/repairs">{t('repairRequestList.title')}</Link> }, { title: t('assetList.actions.detail') }]} />

      <Typography.Title level={2}>{t('repairRequestDetail.title')}</Typography.Title>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card title={t('repairRequestDetail.sections.basic')}>
              <Descriptions column={{ xs: 1, sm: 2 }}>
                <Descriptions.Item label={t('repairRequestDetail.fields.status')}>
                  <Tag color={request.status === 'completed' ? 'success' : request.status === 'rejected' ? 'error' : request.status === 'under_repair' ? 'warning' : 'processing'}>
                    {t(`repairRequestList.status.${request.status}`)}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('repairRequestDetail.fields.createdAt')}>
                  {formatDate(request.created_at)}
                </Descriptions.Item>
                {request.completed_at && (
                  <Descriptions.Item label={t('repairRequestDetail.fields.completedAt')}>
                    {formatDate(request.completed_at)}
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>

            <Card title={t('repairRequestDetail.sections.asset')}>
              <Descriptions column={{ xs: 1, sm: 2 }}>
                <Descriptions.Item label={t('repairRequestDetail.fields.assetName')}>
                  {request.asset.name}
                </Descriptions.Item>
                <Descriptions.Item label={t('repairRequestDetail.fields.assetCode')}>
                  <Typography.Text code>{request.asset.asset_code}</Typography.Text>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card title={t('repairRequestDetail.sections.fault')}>
              <Typography.Paragraph>
                {request.fault_description}
              </Typography.Paragraph>

              {request.images && request.images.length > 0 && (
                <>
                  <Divider style={{ fontSize: '14px' }}>{t('repairRequestDetail.sections.images')}</Divider>
                  <Space size={[8, 8]} wrap>
                    {request.images.map((img) => (
                      <Image
                        key={img.id}
                        width={120}
                        src={img.url}
                        alt="Fault"
                        fallback="https://via.placeholder.com/120?text=Image+Error"
                      />
                    ))}
                  </Space>
                </>
              )}

              {request.status === 'rejected' && request.rejection_reason && (
                <>
                  <Divider />
                  <Typography.Text type="danger" strong>{t('repairRequestDetail.fields.rejectionReason')}: </Typography.Text>
                  <Typography.Text type="danger">{request.rejection_reason}</Typography.Text>
                </>
              )}
            </Card>

            {request.status === 'completed' && (
              <Card title={t('repairRequestDetail.sections.result')}>
                <Descriptions column={{ xs: 1, sm: 2 }}>
                  <Descriptions.Item label={t('repairRequestDetail.fields.repairDate')}>
                    {request.repair_date || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('repairRequestDetail.fields.repairVendor')}>
                    {request.repair_vendor || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('repairRequestDetail.fields.repairCost')}>
                    {request.repair_cost ? `TWD ${request.repair_cost}` : '-'}
                  </Descriptions.Item>
                </Descriptions>
                <Divider style={{ margin: '12px 0' }} />
                <Typography.Text strong>{t('repairRequestDetail.fields.repairPlan')}:</Typography.Text>
                <Typography.Paragraph>{request.repair_plan || '-'}</Typography.Paragraph>
                <Typography.Text strong>{t('repairRequestDetail.fields.faultContent')}:</Typography.Text>
                <Typography.Paragraph>{request.fault_content || '-'}</Typography.Paragraph>
              </Card>
            )}
          </Space>
        </Col>

        <Col xs={24} lg={8}>
          <Card title={t('repairRequestDetail.statusTimeline')}>
            <Timeline
              mode="left"
              items={getTimelineItems()}
            />
          </Card>
        </Col>
      </Row>
    </Space>
  );
};

export default RepairRequestDetail;
