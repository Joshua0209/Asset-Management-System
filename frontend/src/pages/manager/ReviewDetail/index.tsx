import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Divider,
  Space,
  Spin,
  Tag,
  Typography,
  notification,
} from 'antd';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError, repairRequestsApi } from '@/api';
import type { RepairRequestRecord } from '@/api/repair-requests';
import { getApiErrorMessage } from '@/utils/apiErrors';
import { formatDateTime, formatRepairCost } from '@/utils/format';
import AuthImage from '@/components/AuthImage';
import { REPAIR_REQUEST_STATUS_COLORS } from '@/components/repair-requests/constants';

import ApproveRepairModal from './ApproveRepairModal';
import RejectRepairModal from './RejectRepairModal';
import UpdateRepairDetailsModal from './UpdateRepairDetailsModal';
import CompleteRepairModal from './CompleteRepairModal';
import {
  useReviewActions,
  type ApproveValues,
  type RejectValues,
  type RepairDetailsValues,
  type CompleteValues,
} from './useReviewActions';

const ReviewDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [api, contextHolder] = notification.useNotification();
  const [request, setRequest] = useState<RepairRequestRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [isCompleteModalOpen, setIsCompleteModalOpen] = useState(false);

  const loadRequest = useCallback(async () => {
    if (!id) {
      setRequest(null);
      setError(t('errors.notFound'));
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await repairRequestsApi.getRepairRequestById(id);
      setRequest(result);
    } catch (e) {
      setRequest(null);
      if (e instanceof ApiError) {
        setError(getApiErrorMessage(e, t));
      } else {
        setError(t('errors.serverError'));
      }
    } finally {
      setLoading(false);
    }
  }, [id, t]);

  useEffect(() => {
    loadRequest();
  }, [loadRequest]);

  const { isSubmitting, approve, reject, saveDetails, complete } = useReviewActions({
    requestId: request?.id ?? '',
    version: request?.version ?? 0,
    reload: loadRequest,
    api,
    t,
  });

  const approveInitialValues = useMemo<ApproveValues>(
    () => ({
      repair_plan: request?.repair_plan ?? '',
      repair_vendor: request?.repair_vendor ?? '',
      repair_cost: request?.repair_cost ? String(request.repair_cost) : '',
      planned_date: request?.repair_date ?? '',
    }),
    [request],
  );

  const rejectInitialValues = useMemo<RejectValues>(
    () => ({ rejection_reason: request?.rejection_reason ?? '' }),
    [request],
  );

  const detailsInitialValues = useMemo<RepairDetailsValues>(
    () => ({
      repair_date: request?.repair_date ?? undefined,
      fault_content: request?.fault_content ?? undefined,
      repair_plan: request?.repair_plan ?? undefined,
      repair_cost: request?.repair_cost ? String(request.repair_cost) : undefined,
      repair_vendor: request?.repair_vendor ?? undefined,
    }),
    [request],
  );

  const completeInitialValues = useMemo<CompleteValues>(
    () => ({
      repair_date: request?.repair_date ?? '',
      fault_content: request?.fault_content ?? '',
      repair_plan: request?.repair_plan ?? '',
      repair_cost: request?.repair_cost ? String(request.repair_cost) : '',
      repair_vendor: request?.repair_vendor ?? '',
    }),
    [request],
  );

  const handleApproveSubmit = async (values: ApproveValues) => {
    if (await approve(values)) setIsApproveModalOpen(false);
  };
  const handleRejectSubmit = async (values: RejectValues) => {
    if (await reject(values)) setIsRejectModalOpen(false);
  };
  const handleDetailsSubmit = async (values: RepairDetailsValues) => {
    if (await saveDetails(values)) setIsDetailsModalOpen(false);
  };
  const handleCompleteSubmit = async (values: CompleteValues) => {
    if (await complete(values)) setIsCompleteModalOpen(false);
  };

  const renderActions = () => {
    if (!request) {
      return null;
    }

    if (request.status === 'pending_review') {
      return (
        <Space>
          <Button type="primary" onClick={() => setIsApproveModalOpen(true)}>
            {t('reviews.actions.approve')}
          </Button>
          <Button danger onClick={() => setIsRejectModalOpen(true)}>
            {t('reviews.actions.reject')}
          </Button>
        </Space>
      );
    }

    if (request.status === 'under_repair') {
      return (
        <Space>
          <Button onClick={() => setIsDetailsModalOpen(true)}>
            {t('reviews.actions.updateDetails')}
          </Button>
          <Button type="primary" onClick={() => setIsCompleteModalOpen(true)}>
            {t('reviews.actions.complete')}
          </Button>
        </Space>
      );
    }

    return <Typography.Text type="secondary">-</Typography.Text>;
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 0' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {contextHolder}
      <Breadcrumb
        items={[
          { title: <Link to="/reviews">{t('reviews.title')}</Link> },
          { title: t('repairRequestDetail.title') },
        ]}
      />

      {error || !request ? (
        <Alert type="error" showIcon message={error ?? t('errors.notFound')} />
      ) : (
        <>
          <Typography.Title level={2} style={{ marginBottom: 0 }}>
            {t('repairRequestDetail.title')}
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
            {request.asset.name} ({request.asset.asset_code})
          </Typography.Paragraph>

          <Card title={t('reviews.columns.actions')}>{renderActions()}</Card>

          <Card title={t('repairRequestDetail.sections.basic')}>
            <Descriptions column={{ xs: 1, sm: 2 }}>
              <Descriptions.Item label={t('repairRequestDetail.fields.status')}>
                <Tag color={REPAIR_REQUEST_STATUS_COLORS[request.status]}>
                  {t(`reviews.status.${request.status}`)}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('reviews.columns.requester')}>
                {request.requester.name}
              </Descriptions.Item>
              <Descriptions.Item label={t('repairRequestDetail.fields.createdAt')}>
                {formatDateTime(request.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label={t('repairRequestDetail.fields.completedAt')}>
                {formatDateTime(request.completed_at)}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title={t('repairRequestDetail.sections.fault')}>
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              {request.fault_description || '-'}
            </Typography.Paragraph>

            <Divider style={{ margin: '16px 0' }} />

            <Typography.Text strong>{t('repairRequestDetail.sections.images')}</Typography.Text>
            <div style={{ marginTop: 8 }}>
              {request.images.length > 0 ? (
                <Space size={[8, 8]} wrap>
                  {request.images.map((image) => (
                    <AuthImage
                      key={image.id}
                      width={120}
                      height={120}
                      imageId={image.id}
                      alt={t('repairRequestDetail.sections.images')}
                      fallbackSrc="https://via.placeholder.com/120?text=Image"
                    />
                  ))}
                </Space>
              ) : (
                <Typography.Text type="secondary">-</Typography.Text>
              )}
            </div>
          </Card>

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
              <Descriptions.Item label={t('repairRequestDetail.fields.rejectionReason')}>
                {request.rejection_reason || '-'}
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '12px 0' }} />

            <Typography.Text strong>{t('repairRequestDetail.fields.repairPlan')}</Typography.Text>
            <Typography.Paragraph>{request.repair_plan || '-'}</Typography.Paragraph>

            <Typography.Text strong>{t('repairRequestDetail.fields.faultContent')}</Typography.Text>
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              {request.fault_content || '-'}
            </Typography.Paragraph>
          </Card>
        </>
      )}

      <ApproveRepairModal
        open={isApproveModalOpen}
        initialValues={approveInitialValues}
        isSubmitting={isSubmitting}
        onCancel={() => setIsApproveModalOpen(false)}
        onSubmit={handleApproveSubmit}
      />
      <RejectRepairModal
        open={isRejectModalOpen}
        initialValues={rejectInitialValues}
        isSubmitting={isSubmitting}
        onCancel={() => setIsRejectModalOpen(false)}
        onSubmit={handleRejectSubmit}
      />
      <UpdateRepairDetailsModal
        open={isDetailsModalOpen}
        initialValues={detailsInitialValues}
        isSubmitting={isSubmitting}
        onCancel={() => setIsDetailsModalOpen(false)}
        onSubmit={handleDetailsSubmit}
      />
      <CompleteRepairModal
        open={isCompleteModalOpen}
        initialValues={completeInitialValues}
        isSubmitting={isSubmitting}
        onCancel={() => setIsCompleteModalOpen(false)}
        onSubmit={handleCompleteSubmit}
      />
    </Space>
  );
};

export default ReviewDetail;
