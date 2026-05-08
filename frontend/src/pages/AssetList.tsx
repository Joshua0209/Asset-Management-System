import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
  notification,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { ApiError, assetsApi } from '../api';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import { PAGE_SIZE_OPTIONS } from '../components/assets/constants';
import { getAssetColumns } from '../components/assets/columns';
import type {
  AssetCategory,
  AssetCreatePayload,
  AssetRecord,
} from '../api/assets';
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
  const navigate = useNavigate();
  const [api, contextHolder] = notification.useNotification();
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE_OPTIONS[0]);
  const [assetForm] = Form.useForm<AssetFormValues>();

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
    assetForm.resetFields();
    setIsAssetModalOpen(true);
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

      await assetsApi.createAsset(payload);

      setIsAssetModalOpen(false);
      await reloadCurrentPage();
      api.success({ title: t('assetList.manager.createSuccess') });
    } catch (e) {
      if (e instanceof ApiError) {
        api.error({
          title: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(e),
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const actionsColumn: TableColumnsType<AssetRecord>[number] = {
    title: t('assetList.columns.actions'),
    key: 'actions',
    width: 110,
    render: (_: unknown, asset: AssetRecord) => (
      <Space size={4} wrap>
        <Button type="link" onClick={() => navigate(`/assets/${asset.id}`)}>
          {t('assetList.actions.detail')}
        </Button>
      </Space>
    ),
  };

  const columns: TableColumnsType<AssetRecord> = [...getAssetColumns(t), actionsColumn];

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      {contextHolder}
      <Typography.Title level={2} style={{ marginBottom: 0 }}>
        {t('assetList.title')}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('assetList.description')}
      </Typography.Paragraph>

      {error ? <Alert title={error} type="error" showIcon /> : null}

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
            open={isAssetModalOpen}
            title={t('assetList.manager.createTitle')}
            onCancel={() => setIsAssetModalOpen(false)}
            onOk={() => void handleSaveAsset()}
            okText={t('common.button.save')}
            cancelText={t('common.button.cancel')}
            confirmLoading={isSubmitting}
            destroyOnHidden
            forceRender
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
        </Space>
      </Card>
    </Space>
  );
};

export default AssetList;
