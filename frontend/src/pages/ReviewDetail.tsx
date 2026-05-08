import React, { useEffect, useState } from 'react';
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Divider,
  Form,
  Input,
  Modal,
  Space,
  Spin,
  Tag,
  Typography,
  notification,
} from 'antd';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError, repairRequestsApi } from '../api';
import type { RepairRequestRecord, RepairRequestStatus } from '../api/repair-requests';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import AuthImage from '../components/AuthImage';

const STATUS_COLORS: Record<RepairRequestStatus, string> = {
  pending_review: 'warning',
  under_repair: 'processing',
  completed: 'success',
  rejected: 'error',
};

interface ApproveFormValues {
  repair_plan: string;
  repair_vendor: string;
  repair_cost: string;
  planned_date: string;
}

interface RejectFormValues {
  rejection_reason: string;
}

interface RepairDetailsFormValues {
  repair_date?: string;
  fault_content?: string;
  repair_plan?: string;
  repair_cost?: string;
  repair_vendor?: string;
}

interface CompleteFormValues {
  repair_date: string;
  fault_content: string;
  repair_plan: string;
  repair_cost: string;
  repair_vendor: string;
}

const ReviewDetail: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [api, contextHolder] = notification.useNotification();
  const [request, setRequest] = useState<RepairRequestRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [isCompleteModalOpen, setIsCompleteModalOpen] = useState(false);

  const [approveForm] = Form.useForm<ApproveFormValues>();
  const [rejectForm] = Form.useForm<RejectFormValues>();
  const [detailsForm] = Form.useForm<RepairDetailsFormValues>();
  const [completeForm] = Form.useForm<CompleteFormValues>();

  const validateRepairCostRequired = createAmountValidator(t, {
    required: true,
    formatKey: 'validation.repairCostFormat',
    positiveKey: 'validation.repairCostPositive',
  });
  const validateRepairCostOptional = createAmountValidator(t, {
    formatKey: 'validation.repairCostFormat',
    positiveKey: 'validation.repairCostPositive',
  });

  const formatApiError = (apiError: ApiError): string => getApiErrorMessage(apiError, t);

  const formatDateTime = (value: string | null | undefined): string => {
    if (!value) {
      return '-';
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  };

  const formatRepairCost = (
    value: string | number | null | undefined,
  ): string => (value === null || value === undefined || value === '' ? '-' : `TWD ${value}`);

  const loadRequest = async () => {
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
        setError(formatApiError(e));
      } else {
        setError(t('errors.serverError'));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRequest();
  }, [id]);

  const openApproveModal = () => {
    if (!request) {
      return;
    }

    approveForm.setFieldsValue({
      repair_plan: request.repair_plan ?? '',
      repair_vendor: request.repair_vendor ?? '',
      repair_cost: request.repair_cost ? String(request.repair_cost) : '',
      planned_date: request.repair_date ?? '',
    });
    setIsApproveModalOpen(true);
  };

  const openRejectModal = () => {
    if (!request) {
      return;
    }

    rejectForm.setFieldValue('rejection_reason', request.rejection_reason ?? '');
    setIsRejectModalOpen(true);
  };

  const openDetailsModal = () => {
    if (!request) {
      return;
    }

    detailsForm.setFieldsValue({
      repair_date: request.repair_date ?? undefined,
      fault_content: request.fault_content ?? undefined,
      repair_plan: request.repair_plan ?? undefined,
      repair_cost: request.repair_cost ? String(request.repair_cost) : undefined,
      repair_vendor: request.repair_vendor ?? undefined,
    });
    setIsDetailsModalOpen(true);
  };

  const openCompleteModal = () => {
    if (!request) {
      return;
    }

    completeForm.setFieldsValue({
      repair_date: request.repair_date ?? '',
      fault_content: request.fault_content ?? '',
      repair_plan: request.repair_plan ?? '',
      repair_cost: request.repair_cost ? String(request.repair_cost) : '',
      repair_vendor: request.repair_vendor ?? '',
    });
    setIsCompleteModalOpen(true);
  };

  const handleApprove = async () => {
    if (!request) {
      return;
    }

    try {
      const values = await approveForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.approveRepairRequest(request.id, {
        version: request.version,
        repair_plan: values.repair_plan,
        repair_vendor: values.repair_vendor,
        repair_cost: values.repair_cost,
        planned_date: values.planned_date,
      });
      setIsApproveModalOpen(false);
      await loadRequest();
      api.success({ title: t('reviews.approveSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('reviews.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!request) {
      return;
    }

    try {
      const values = await rejectForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.rejectRepairRequest(request.id, {
        version: request.version,
        rejection_reason: values.rejection_reason,
      });
      setIsRejectModalOpen(false);
      await loadRequest();
      api.success({ title: t('reviews.rejectSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('reviews.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveDetails = async () => {
    if (!request) {
      return;
    }

    try {
      const values = await detailsForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.updateRepairRequestDetails(request.id, {
        version: request.version,
        repair_date: values.repair_date,
        fault_content: values.fault_content,
        repair_plan: values.repair_plan,
        repair_cost: values.repair_cost,
        repair_vendor: values.repair_vendor,
      });
      setIsDetailsModalOpen(false);
      await loadRequest();
      api.success({ title: t('reviews.detailsSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('reviews.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleComplete = async () => {
    if (!request) {
      return;
    }

    try {
      const values = await completeForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.completeRepairRequest(request.id, {
        version: request.version,
        repair_date: values.repair_date,
        fault_content: values.fault_content,
        repair_plan: values.repair_plan,
        repair_cost: values.repair_cost,
        repair_vendor: values.repair_vendor,
      });
      setIsCompleteModalOpen(false);
      await loadRequest();
      api.success({ title: t('reviews.completeSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('reviews.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderActions = () => {
    if (!request) {
      return null;
    }

    if (request.status === 'pending_review') {
      return (
        <Space>
          <Button type="primary" onClick={openApproveModal}>
            {t('reviews.actions.approve')}
          </Button>
          <Button danger onClick={openRejectModal}>
            {t('reviews.actions.reject')}
          </Button>
        </Space>
      );
    }

    if (request.status === 'under_repair') {
      return (
        <Space>
          <Button onClick={openDetailsModal}>{t('reviews.actions.updateDetails')}</Button>
          <Button type="primary" onClick={openCompleteModal}>
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
                <Tag color={STATUS_COLORS[request.status]}>{t(`reviews.status.${request.status}`)}</Tag>
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

      <Modal
        open={isApproveModalOpen}
        title={t('reviews.approveTitle')}
        onCancel={() => setIsApproveModalOpen(false)}
        onOk={() => void handleApprove()}
        okText={t('reviews.actions.approve')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
      >
        <Form form={approveForm} layout="vertical">
          <Form.Item
            name="repair_plan"
            label={t('reviews.form.repairPlan')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="repair_vendor"
            label={t('reviews.form.repairVendor')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="repair_cost"
            label={t('reviews.form.repairCost')}
            rules={[{ validator: validateRepairCostRequired }]}
          >
            <Input type="number" min={0} step="0.01" />
          </Form.Item>
          <Form.Item
            name="planned_date"
            label={t('reviews.form.plannedDate')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input type="date" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={isRejectModalOpen}
        title={t('reviews.rejectTitle')}
        onCancel={() => setIsRejectModalOpen(false)}
        onOk={() => void handleReject()}
        okText={t('reviews.actions.reject')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
      >
        <Form form={rejectForm} layout="vertical">
          <Form.Item
            name="rejection_reason"
            label={t('reviews.form.rejectionReason')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={isDetailsModalOpen}
        title={t('reviews.detailsTitle')}
        onCancel={() => setIsDetailsModalOpen(false)}
        onOk={() => void handleSaveDetails()}
        okText={t('common.button.save')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
      >
        <Form form={detailsForm} layout="vertical">
          <Form.Item name="repair_date" label={t('reviews.form.repairDate')}>
            <Input type="date" />
          </Form.Item>
          <Form.Item name="fault_content" label={t('reviews.form.faultContent')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="repair_plan" label={t('reviews.form.repairPlan')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="repair_cost"
            label={t('reviews.form.repairCost')}
            rules={[{ validator: validateRepairCostOptional }]}
          >
            <Input type="number" min={0} step="0.01" />
          </Form.Item>
          <Form.Item name="repair_vendor" label={t('reviews.form.repairVendor')}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={isCompleteModalOpen}
        title={t('reviews.completeTitle')}
        onCancel={() => setIsCompleteModalOpen(false)}
        onOk={() => void handleComplete()}
        okText={t('reviews.actions.complete')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
      >
        <Form form={completeForm} layout="vertical">
          <Form.Item
            name="repair_date"
            label={t('reviews.form.repairDate')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input type="date" />
          </Form.Item>
          <Form.Item
            name="fault_content"
            label={t('reviews.form.faultContent')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="repair_plan"
            label={t('reviews.form.repairPlan')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="repair_cost"
            label={t('reviews.form.repairCost')}
            rules={[{ validator: validateRepairCostRequired }]}
          >
            <Input type="number" min={0} step="0.01" />
          </Form.Item>
          <Form.Item
            name="repair_vendor"
            label={t('reviews.form.repairVendor')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default ReviewDetail;
