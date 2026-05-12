import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  notification,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';

import { ApiError, repairRequestsApi } from '../api';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import type {
  RepairRequestRecord,
  RepairRequestStatus,
} from '../api/repair-requests';

const PAGE_SIZE_OPTIONS = [5, 10, 20];

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

const Reviews: React.FC = () => {
  const { t } = useTranslation();
  const [api, contextHolder] = notification.useNotification();
  const [requests, setRequests] = useState<RepairRequestRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [statusFilter, setStatusFilter] = useState<RepairRequestStatus | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [approvingRequest, setApprovingRequest] = useState<RepairRequestRecord | null>(null);
  const [rejectingRequest, setRejectingRequest] = useState<RepairRequestRecord | null>(null);
  const [editingRequest, setEditingRequest] = useState<RepairRequestRecord | null>(null);
  const [completingRequest, setCompletingRequest] = useState<RepairRequestRecord | null>(null);

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

  const loadRequests = async () => {
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
  };

  useEffect(() => {
    void loadRequests();
  }, [page, pageSize, statusFilter]);

  const openApproveModal = (request: RepairRequestRecord) => {
    setApprovingRequest(request);
    approveForm.setFieldsValue({
      repair_plan: request.repair_plan ?? '',
      repair_vendor: request.repair_vendor ?? '',
      repair_cost: request.repair_cost ? String(request.repair_cost) : '',
      planned_date: request.repair_date ?? '',
    });
  };

  const openRejectModal = (request: RepairRequestRecord) => {
    setRejectingRequest(request);
    rejectForm.setFieldValue('rejection_reason', request.rejection_reason ?? '');
  };

  const openDetailsModal = (request: RepairRequestRecord) => {
    setEditingRequest(request);
    detailsForm.setFieldsValue({
      repair_date: request.repair_date ?? undefined,
      fault_content: request.fault_content ?? undefined,
      repair_plan: request.repair_plan ?? undefined,
      repair_cost: request.repair_cost ? String(request.repair_cost) : undefined,
      repair_vendor: request.repair_vendor ?? undefined,
    });
  };

  const openCompleteModal = (request: RepairRequestRecord) => {
    setCompletingRequest(request);
    completeForm.setFieldsValue({
      repair_date: request.repair_date ?? '',
      fault_content: request.fault_content ?? '',
      repair_plan: request.repair_plan ?? '',
      repair_cost: request.repair_cost ? String(request.repair_cost) : '',
      repair_vendor: request.repair_vendor ?? '',
    });
  };

  const handleApprove = async () => {
    if (!approvingRequest) {
      return;
    }

    try {
      const values = await approveForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.approveRepairRequest(approvingRequest.id, {
        version: approvingRequest.version,
        repair_plan: values.repair_plan,
        repair_vendor: values.repair_vendor,
        repair_cost: values.repair_cost,
        planned_date: values.planned_date,
      });
      setApprovingRequest(null);
      await loadRequests();
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
    if (!rejectingRequest) {
      return;
    }

    try {
      const values = await rejectForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.rejectRepairRequest(rejectingRequest.id, {
        version: rejectingRequest.version,
        rejection_reason: values.rejection_reason,
      });
      setRejectingRequest(null);
      await loadRequests();
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
    if (!editingRequest) {
      return;
    }

    try {
      const values = await detailsForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.updateRepairRequestDetails(editingRequest.id, {
        version: editingRequest.version,
        repair_date: values.repair_date,
        fault_content: values.fault_content,
        repair_plan: values.repair_plan,
        repair_cost: values.repair_cost,
        repair_vendor: values.repair_vendor,
      });
      setEditingRequest(null);
      await loadRequests();
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
    if (!completingRequest) {
      return;
    }

    try {
      const values = await completeForm.validateFields();
      setIsSubmitting(true);
      await repairRequestsApi.completeRepairRequest(completingRequest.id, {
        version: completingRequest.version,
        repair_date: values.repair_date,
        fault_content: values.fault_content,
        repair_plan: values.repair_plan,
        repair_cost: values.repair_cost,
        repair_vendor: values.repair_vendor,
      });
      setCompletingRequest(null);
      await loadRequests();
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
      width: 320,
      render: (_: unknown, record) => (
        <Space size={4} wrap>
          {record.status === 'pending_review' ? (
            <>
              <Button type="link" onClick={() => openApproveModal(record)}>
                {t('reviews.actions.approve')}
              </Button>
              <Button type="link" danger onClick={() => openRejectModal(record)}>
                {t('reviews.actions.reject')}
              </Button>
            </>
          ) : null}

          {record.status === 'under_repair' ? (
            <>
              <Button type="link" onClick={() => openDetailsModal(record)}>
                {t('reviews.actions.updateDetails')}
              </Button>
              <Button type="link" onClick={() => openCompleteModal(record)}>
                {t('reviews.actions.complete')}
              </Button>
            </>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {contextHolder}
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

      <Modal
        open={approvingRequest !== null}
        title={t('reviews.approveTitle')}
        onCancel={() => setApprovingRequest(null)}
        onOk={() => void handleApprove()}
        okText={t('reviews.actions.approve')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
        forceRender
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
        open={rejectingRequest !== null}
        title={t('reviews.rejectTitle')}
        onCancel={() => setRejectingRequest(null)}
        onOk={() => void handleReject()}
        okText={t('reviews.actions.reject')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
        forceRender
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
        open={editingRequest !== null}
        title={t('reviews.detailsTitle')}
        onCancel={() => setEditingRequest(null)}
        onOk={() => void handleSaveDetails()}
        okText={t('common.button.save')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
        forceRender
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
        open={completingRequest !== null}
        title={t('reviews.completeTitle')}
        onCancel={() => setCompletingRequest(null)}
        onOk={() => void handleComplete()}
        okText={t('reviews.actions.complete')}
        cancelText={t('common.button.cancel')}
        confirmLoading={isSubmitting}
        destroyOnHidden
        forceRender
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

export default Reviews;
