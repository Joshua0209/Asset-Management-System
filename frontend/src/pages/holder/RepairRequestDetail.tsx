import React, { useEffect, useState } from 'react';
import {
  Alert,
  Breadcrumb,
  Card,
  Col,
  Descriptions,
  Divider,
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

import { ApiError, repairRequestsApi } from '@/api';
import type { RepairRequestRecord } from '@/api/repair-requests';
import AuthImage from '@/components/AuthImage';
import { REPAIR_REQUEST_STATUS_COLORS } from '@/components/repair-requests/constants';
import { formatDateTime, formatRepairCost } from '@/utils/format';

const RepairRequestDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [request, setRequest] = useState<RepairRequestRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Breadcrumb items={[{ title: <Link to="/repairs">{t('repairRequestList.title')}</Link> }, { title: t('assetList.actions.detail') }]} />
        <Alert title={error || t('errors.notFound')} type="error" showIcon />
      </Space>
    );
  }

  const getTimelineItems = () => {
    const items = [
      {
        content: t('repairRequestList.status.pending_review'),
        color: 'blue',
        icon: <ClockCircleOutlined />,
        title: formatDateTime(request.created_at),
      },
    ];

    if (request.status === 'under_repair' || request.status === 'completed') {
      items.push({
        content: t('repairRequestList.status.under_repair'),
        color: 'orange',
        icon: <ToolOutlined />,
        title: request.updated_at ? formatDateTime(request.updated_at) : '',
      });
    }

    if (request.status === 'completed') {
      items.push({
        content: t('repairRequestList.status.completed'),
        color: 'green',
        icon: <CheckCircleOutlined />,
        title: formatDateTime(request.completed_at),
      });
    }

    if (request.status === 'rejected') {
      items.push({
        content: t('repairRequestList.status.rejected'),
        color: 'red',
        icon: <CloseCircleOutlined />,
        title: formatDateTime(request.updated_at),
      });
    }

    return items;
  };

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Breadcrumb items={[{ title: <Link to="/repairs">{t('repairRequestList.title')}</Link> }, { title: t('assetList.actions.detail') }]} />

      <Typography.Title level={2}>{t('repairRequestDetail.title')}</Typography.Title>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Card title={t('repairRequestDetail.sections.basic')}>
              <Descriptions column={{ xs: 1, sm: 2 }}>
                <Descriptions.Item label={t('repairRequestDetail.fields.status')}>
                  <Tag color={REPAIR_REQUEST_STATUS_COLORS[request.status]}>
                    {t(`repairRequestList.status.${request.status}`)}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label={t('repairRequestDetail.fields.createdAt')}>
                  {formatDateTime(request.created_at)}
                </Descriptions.Item>
                {request.completed_at && (
                  <Descriptions.Item label={t('repairRequestDetail.fields.completedAt')}>
                    {formatDateTime(request.completed_at)}
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
                      <AuthImage
                        key={img.id}
                        width={120}
                        imageId={img.id}
                        alt="Fault"
                        fallbackSrc="https://via.placeholder.com/120?text=Image+Error"
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
                    {formatRepairCost(request.repair_cost)}
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
              mode="start"
              items={getTimelineItems()}
            />
          </Card>
        </Col>
      </Row>
    </Space>
  );
};

export default RepairRequestDetail;
