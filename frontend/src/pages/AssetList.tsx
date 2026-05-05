import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
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

import { useAuth } from '../auth/AuthContext';
import { ApiError, assetsApi, usersApi } from '../api';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import type {
  AssetCategory,
  AssetCreatePayload,
  AssetRecord,
  AssetStatus,
  AssetUpdatePayload,
} from '../api/assets';
import type { UserRecord } from '../api/users';

const STATUS_COLORS: Record<AssetStatus, string> = {
  in_stock: 'default',
  in_use: 'success',
  pending_repair: 'processing',
  under_repair: 'warning',
  disposed: 'error',
};

const PAGE_SIZE_OPTIONS = [5, 10, 20];
const CATEGORY_OPTIONS: AssetCategory[] = [
  'phone',
  'computer',
  'tablet',
  'monitor',
  'printer',
  'network_equipment',
  'other',
];

interface AssetFormValues {
  name: string;
  model: string;
  specs?: string;
  category: AssetCategory;
  supplier: string;
  purchase_date: string;
  purchase_amount: string;
  location?: string;
  department?: string;
  activation_date?: string;
  warranty_expiry?: string;
}

interface AssignFormValues {
  responsible_person_id?: string;
  assignment_date?: string;
  reason?: string;
}

interface DisposeFormValues {
  disposal_reason: string;
}

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parseDateOnly(value?: string | null): Date | null {
  if (!value || !DATE_ONLY_PATTERN.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function isFutureDate(value: string): boolean {
  const parsed = parseDateOnly(value);
  if (!parsed) {
    return false;
  }

  const todayUtc = new Date();
  todayUtc.setUTCHours(0, 0, 0, 0);
  return parsed.getTime() > todayUtc.getTime();
}

const AssetList: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [api, contextHolder] = notification.useNotification();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [holders, setHolders] = useState<UserRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailAsset, setDetailAsset] = useState<AssetRecord | null>(null);
  const [editingAsset, setEditingAsset] = useState<AssetRecord | null>(null);
  const [assigningAsset, setAssigningAsset] = useState<AssetRecord | null>(null);
  const [disposingAsset, setDisposingAsset] = useState<AssetRecord | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false);
  const [isDisposeModalOpen, setIsDisposeModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [assetForm] = Form.useForm<AssetFormValues>();
  const [assignForm] = Form.useForm<AssignFormValues>();
  const [disposeForm] = Form.useForm<DisposeFormValues>();

  const validatePurchaseAmount = createAmountValidator(t, { required: true });

  const validateWarrantyExpiry = async (_: unknown, value?: string) => {
    if (!value) {
      return;
    }

    const warrantyDate = parseDateOnly(value);
    if (!warrantyDate) {
      return;
    }

    const purchaseDate = parseDateOnly(assetForm.getFieldValue('purchase_date'));
    if (purchaseDate && warrantyDate.getTime() <= purchaseDate.getTime()) {
      throw new Error(t('validation.warrantyAfterPurchase'));
    }

    const activationDate = parseDateOnly(assetForm.getFieldValue('activation_date'));
    if (activationDate && warrantyDate.getTime() <= activationDate.getTime()) {
      throw new Error(t('validation.warrantyAfterActivation'));
    }
  };

  const formatApiError = (apiError: ApiError): string => getApiErrorMessage(apiError, t);

  const isManager = user?.role === 'manager';

  const moneyFormatter = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: 'TWD',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }),
    [],
  );

  const formatDateValue = (value: string | null): string => {
    if (!value) {
      return t('assetList.detail.notAvailable');
    }

    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
  };

  const formatAmountValue = (value: string | number): string => {
    const parsed = Number.parseFloat(String(value));
    return Number.isNaN(parsed) ? String(value) : moneyFormatter.format(parsed);
  };

  useEffect(() => {
    setPage(1);
  }, [user?.role]);

  useEffect(() => {
    if (!user) {
      return;
    }

    let cancelled = false;

    const loadAssets = async () => {
      setLoading(true);
      setError(null);
      try {
        const response =
          user.role === 'manager'
            ? await assetsApi.listAssets({ page, perPage: pageSize })
            : await assetsApi.listMyAssets({ page, perPage: pageSize });
        if (cancelled) {
          return;
        }
        setAssets(response.data);
        setTotal(response.meta.total);
      } catch (e) {
        if (cancelled) {
          return;
        }
        setAssets([]);
        setTotal(0);
        if (e instanceof ApiError) {
          setError(formatApiError(e));
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadAssets();

    return () => {
      cancelled = true;
    };
  }, [page, pageSize, t, user]);

  useEffect(() => {
    if (!isManager) {
      setHolders([]);
      return;
    }

    let cancelled = false;
    const loadHolders = async () => {
      try {
        const response = await usersApi.listUsers({ page: 1, perPage: 200, role: 'holder' });
        if (!cancelled) {
          setHolders(response.data);
        }
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiError) {
            api.error({
              message: t('assetList.manager.holdersLoadErrorTitle'),
              description: formatApiError(e),
            });
          }
        }
      }
    };

    void loadHolders();

    return () => {
      cancelled = true;
    };
  }, [api, isManager, t]);

  const reloadCurrentPage = async () => {
    if (!user) {
      return;
    }

    const response =
      user.role === 'manager'
        ? await assetsApi.listAssets({ page, perPage: pageSize })
        : await assetsApi.listMyAssets({ page, perPage: pageSize });
    setAssets(response.data);
    setTotal(response.meta.total);
  };

  const openCreateModal = () => {
    setEditingAsset(null);
    assetForm.resetFields();
    setIsAssetModalOpen(true);
  };

  const openEditModal = (asset: AssetRecord) => {
    setEditingAsset(asset);
    assetForm.setFieldsValue({
      name: asset.name,
      model: asset.model,
      specs: asset.specs ?? undefined,
      category: asset.category as AssetCategory,
      supplier: asset.supplier,
      purchase_date: asset.purchase_date,
      purchase_amount: String(asset.purchase_amount),
      location: asset.location,
      department: asset.department,
      activation_date: asset.activation_date ?? undefined,
      warranty_expiry: asset.warranty_expiry ?? undefined,
    });
    setIsAssetModalOpen(true);
  };

  const openAssignModal = (asset: AssetRecord) => {
    setAssigningAsset(asset);
    assignForm.resetFields();
    if (asset.status === 'in_use') {
      assignForm.setFieldValue('reason', '');
    } else if (asset.responsible_person_id) {
      assignForm.setFieldValue('responsible_person_id', asset.responsible_person_id);
    }
    setIsAssignModalOpen(true);
  };

  const openDisposeModal = (asset: AssetRecord) => {
    setDisposingAsset(asset);
    disposeForm.resetFields();
    setIsDisposeModalOpen(true);
  };

  const toAssetPayload = (values: AssetFormValues): Omit<AssetCreatePayload, 'category'> & {
    category: AssetCategory;
  } => ({
    name: values.name,
    model: values.model,
    specs: values.specs?.trim() ? values.specs.trim() : null,
    category: values.category,
    supplier: values.supplier,
    purchase_date: values.purchase_date,
    purchase_amount: values.purchase_amount,
    location: values.location?.trim() ? values.location.trim() : null,
    department: values.department?.trim() ? values.department.trim() : null,
    activation_date: values.activation_date?.trim() ? values.activation_date.trim() : null,
    warranty_expiry: values.warranty_expiry?.trim() ? values.warranty_expiry.trim() : null,
  });

  const handleSaveAsset = async () => {
    try {
      const values = await assetForm.validateFields();
      const payload = toAssetPayload(values);
      setIsSubmitting(true);

      if (editingAsset) {
        const updatePayload: AssetUpdatePayload = {
          ...payload,
          version: editingAsset.version,
        };
        await assetsApi.updateAsset(editingAsset.id, updatePayload);
      } else {
        await assetsApi.createAsset(payload);
      }

      setIsAssetModalOpen(false);
      await reloadCurrentPage();
      api.success({
        message: editingAsset
          ? t('assetList.manager.editSuccess')
          : t('assetList.manager.createSuccess'),
      });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          message: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAssignOrUnassign = async () => {
    if (!assigningAsset) {
      return;
    }

    try {
      const values = await assignForm.validateFields();
      setIsSubmitting(true);

      if (assigningAsset.status === 'in_use') {
        await assetsApi.unassignAsset(assigningAsset.id, {
          reason: values.reason ?? '',
          version: assigningAsset.version,
        });
        api.success({ message: t('assetList.manager.unassignSuccess') });
      } else {
        await assetsApi.assignAsset(assigningAsset.id, {
          responsible_person_id: values.responsible_person_id ?? '',
          assignment_date: values.assignment_date,
          version: assigningAsset.version,
        });
        api.success({ message: t('assetList.manager.assignSuccess') });
      }

      setIsAssignModalOpen(false);
      setAssigningAsset(null);
      await reloadCurrentPage();
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          message: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDispose = async () => {
    if (!disposingAsset) {
      return;
    }

    try {
      const values = await disposeForm.validateFields();
      setIsSubmitting(true);
      await assetsApi.disposeAsset(disposingAsset.id, {
        disposal_reason: values.disposal_reason,
        version: disposingAsset.version,
      });
      setIsDisposeModalOpen(false);
      setDisposingAsset(null);
      await reloadCurrentPage();
      api.success({ message: t('assetList.manager.disposeSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          message: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const columns: TableColumnsType<AssetRecord> = [
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
      render: (value: string) => formatDateValue(value),
    },
    {
      title: t('assetList.columns.actions'),
      key: 'actions',
      width: isManager ? 260 : 110,
      render: (_: unknown, asset: AssetRecord) => (
        <Space size={4} wrap>
          <Button type="link" onClick={() => setDetailAsset(asset)}>
            {t('assetList.actions.detail')}
          </Button>

          {isManager ? (
            <Button type="link" onClick={() => openEditModal(asset)}>
              {t('assetList.actions.edit')}
            </Button>
          ) : null}

          {isManager && asset.status === 'in_stock' ? (
            <Button type="link" onClick={() => openAssignModal(asset)}>
              {t('assetList.actions.assign')}
            </Button>
          ) : null}

          {isManager && asset.status === 'in_use' ? (
            <Button type="link" onClick={() => openAssignModal(asset)}>
              {t('assetList.actions.unassign')}
            </Button>
          ) : null}

          {isManager && asset.status === 'in_stock' ? (
            <Button type="link" danger onClick={() => openDisposeModal(asset)}>
              {t('assetList.actions.dispose')}
            </Button>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {contextHolder}
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      {error ? <Alert message={error} type="error" showIcon /> : null}

      <Card>
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          {isManager ? (
            <Space>
              <Button type="primary" onClick={openCreateModal}>
                {t('assetList.manager.createButton')}
              </Button>
            </Space>
          ) : null}

          <Typography.Text type="secondary">
            {t('assetList.summary', { count: total })}
          </Typography.Text>

          <Table<AssetRecord>
            rowKey="id"
            loading={loading}
            dataSource={assets}
            columns={columns}
            locale={{
              emptyText: t('assetList.empty'),
            }}
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
            scroll={{ x: 1200 }}
          />

          <Modal
            open={detailAsset !== null}
            title={t('assetList.detail.title', { assetCode: detailAsset?.asset_code ?? '' })}
            onCancel={() => setDetailAsset(null)}
            footer={[
              <Button key="close" onClick={() => setDetailAsset(null)}>
                {t('common.button.cancel')}
              </Button>,
            ]}
          >
            {detailAsset ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t('assetList.columns.assetCode')}>
                  {detailAsset.asset_code}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.columns.name')}>
                  {detailAsset.name}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.columns.status')}>
                  {t(`assetList.status.${detailAsset.status}`)}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.detail.holder')}>
                  {detailAsset.responsible_person?.name ?? t('assetList.detail.unassigned')}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.detail.model')}>
                  {detailAsset.model}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.detail.specs')}>
                  {detailAsset.specs ?? t('assetList.detail.notAvailable')}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.detail.supplier')}>
                  {detailAsset.supplier}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.detail.activationDate')}>
                  {formatDateValue(detailAsset.activation_date)}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.detail.warrantyExpiry')}>
                  {formatDateValue(detailAsset.warranty_expiry)}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.columns.department')}>
                  {detailAsset.department}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.columns.location')}>
                  {detailAsset.location}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.columns.purchaseAmount')}>
                  {formatAmountValue(detailAsset.purchase_amount)}
                </Descriptions.Item>
                <Descriptions.Item label={t('assetList.columns.purchaseDate')}>
                  {formatDateValue(detailAsset.purchase_date)}
                </Descriptions.Item>
              </Descriptions>
            ) : null}
          </Modal>

          <Modal
            open={isAssetModalOpen}
            title={
              editingAsset
                ? t('assetList.manager.editTitle', { assetCode: editingAsset.asset_code })
                : t('assetList.manager.createTitle')
            }
            onCancel={() => setIsAssetModalOpen(false)}
            onOk={() => void handleSaveAsset()}
            okText={t('common.button.save')}
            cancelText={t('common.button.cancel')}
            confirmLoading={isSubmitting}
            destroyOnHidden
          >
            <Form form={assetForm} layout="vertical">
              <Form.Item
                name="name"
                label={t('assetList.form.name')}
                rules={[
                  { required: true, message: t('validation.required') },
                  { max: 120, message: t('validation.max120Chars') },
                ]}
              >
                <Input />
              </Form.Item>

              <Form.Item
                name="model"
                label={t('assetList.form.model')}
                rules={[
                  { required: true, message: t('validation.required') },
                  { max: 120, message: t('validation.max120Chars') },
                ]}
              >
                <Input />
              </Form.Item>

              <Form.Item
                name="specs"
                label={t('assetList.form.specs')}
                rules={[{ max: 500, message: t('validation.max500Chars') }]}
              >
                <Input.TextArea rows={2} />
              </Form.Item>

              <Form.Item
                name="category"
                label={t('assetList.form.category')}
                rules={[{ required: true, message: t('validation.required') }]}
              >
                <Select
                  options={CATEGORY_OPTIONS.map((category) => ({
                    value: category,
                    label: category,
                  }))}
                />
              </Form.Item>

              <Form.Item
                name="supplier"
                label={t('assetList.form.supplier')}
                rules={[
                  { required: true, message: t('validation.required') },
                  { max: 120, message: t('validation.max120Chars') },
                ]}
              >
                <Input />
              </Form.Item>

              <Form.Item
                name="purchase_date"
                label={t('assetList.form.purchaseDate')}
                rules={[
                  { required: true, message: t('validation.required') },
                  {
                    validator: async (_rule, value?: string) => {
                      if (!value) {
                        return;
                      }
                      if (isFutureDate(value)) {
                        throw new Error(t('validation.purchaseDateNotFuture'));
                      }
                    },
                  },
                ]}
              >
                <Input type="date" />
              </Form.Item>

              <Form.Item
                name="purchase_amount"
                label={t('assetList.form.purchaseAmount')}
                rules={[{ validator: validatePurchaseAmount }]}
              >
                <Input type="number" min={0} step="0.01" />
              </Form.Item>

              <Form.Item
                name="location"
                label={t('assetList.form.location')}
                rules={[{ max: 120, message: t('validation.max120Chars') }]}
              >
                <Input />
              </Form.Item>

              <Form.Item
                name="department"
                label={t('assetList.form.department')}
                rules={[{ max: 100, message: t('validation.max100Chars') }]}
              >
                <Input />
              </Form.Item>

              <Form.Item name="activation_date" label={t('assetList.form.activationDate')}>
                <Input type="date" />
              </Form.Item>

              <Form.Item
                name="warranty_expiry"
                label={t('assetList.form.warrantyExpiry')}
                dependencies={['purchase_date', 'activation_date']}
                rules={[{ validator: validateWarrantyExpiry }]}
              >
                <Input type="date" />
              </Form.Item>
            </Form>
          </Modal>

          <Modal
            open={isAssignModalOpen}
            title={
              assigningAsset?.status === 'in_use'
                ? t('assetList.manager.unassignTitle', { assetCode: assigningAsset?.asset_code ?? '' })
                : t('assetList.manager.assignTitle', { assetCode: assigningAsset?.asset_code ?? '' })
            }
            onCancel={() => {
              setIsAssignModalOpen(false);
              setAssigningAsset(null);
            }}
            onOk={() => void handleAssignOrUnassign()}
            okText={t('common.button.confirm')}
            cancelText={t('common.button.cancel')}
            confirmLoading={isSubmitting}
            destroyOnHidden
          >
            <Form form={assignForm} layout="vertical">
              {assigningAsset?.status === 'in_use' ? (
                <Form.Item
                  name="reason"
                  label={t('assetList.form.unassignReason')}
                  rules={[{ required: true, message: t('validation.required') }]}
                >
                  <Input.TextArea rows={3} />
                </Form.Item>
              ) : (
                <>
                  <Form.Item
                    name="responsible_person_id"
                    label={t('assetList.form.holder')}
                    rules={[{ required: true, message: t('validation.required') }]}
                  >
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={holders.map((holder) => ({
                        value: holder.id,
                        label: `${holder.name} (${holder.email})`,
                      }))}
                    />
                  </Form.Item>

                  <Form.Item
                    name="assignment_date"
                    label={t('assetList.form.assignmentDate')}
                    rules={[{ required: true, message: t('validation.required') }]}
                  >
                    <Input type="date" />
                  </Form.Item>
                </>
              )}
            </Form>
          </Modal>

          <Modal
            open={isDisposeModalOpen}
            title={t('assetList.manager.disposeTitle', { assetCode: disposingAsset?.asset_code ?? '' })}
            onCancel={() => {
              setIsDisposeModalOpen(false);
              setDisposingAsset(null);
            }}
            onOk={() => void handleDispose()}
            okText={t('common.button.confirm')}
            cancelText={t('common.button.cancel')}
            confirmLoading={isSubmitting}
            destroyOnHidden
          >
            <Form form={disposeForm} layout="vertical">
              <Form.Item
                name="disposal_reason"
                label={t('assetList.form.disposalReason')}
                rules={[{ required: true, message: t('validation.required') }]}
              >
                <Input.TextArea rows={4} />
              </Form.Item>
            </Form>
          </Modal>
        </Space>
      </Card>
    </Space>
  );
};

export default AssetList;
