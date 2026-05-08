import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Select,
  notification,
  Result,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';
import { assetsApi, ApiError, usersApi } from '../api';
import { getApiErrorMessage } from '../utils/apiErrors';
import { createAmountValidator } from '../utils/validators';
import type { AssetCategory, AssetRecord, AssetUpdatePayload } from '../api/assets';
import type { UserRecord } from '../api/users';
import { STATUS_COLORS } from '../components/assets/constants';
import { formatDateValue, formatAmountValue } from '../utils/format';

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

interface AssetTextFieldConfig {
  name: keyof AssetFormValues;
  label: string;
  required?: boolean;
  max?: number;
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

const pageContainerStyle: React.CSSProperties = {
  maxWidth: 1200,
  margin: '0 auto',
};

const AssetDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user } = useAuth();
  const [api, contextHolder] = notification.useNotification();
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [holders, setHolders] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false);
  const [isDisposeModalOpen, setIsDisposeModalOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [assetForm] = Form.useForm<AssetFormValues>();
  const [assignForm] = Form.useForm<AssignFormValues>();
  const [disposeForm] = Form.useForm<DisposeFormValues>();

  const isManager = user?.role === 'manager';
  const formatApiError = useCallback((apiError: ApiError): string => getApiErrorMessage(apiError, t), [t]);
  const validatePurchaseAmount = createAmountValidator(t, { required: true });

  const showActionError = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError) {
        api.error({
          title: t('assetList.manager.actionFailedTitle'),
          description: formatApiError(error),
        });
      }
    },
    [api, formatApiError, t],
  );

  const runSubmittingAction = useCallback(
    async (action: () => Promise<void>) => {
      setIsSubmitting(true);
      try {
        await action();
      } catch (error) {
        showActionError(error);
      } finally {
        setIsSubmitting(false);
      }
    },
    [showActionError],
  );

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

  const loadAsset = useCallback(
    async (showLoading = true) => {
      if (!id) {
        return;
      }

      if (showLoading) {
        setLoading(true);
      }

      setError(null);
      setStatus(null);

      try {
        const data = await assetsApi.getAssetById(id);
        setAsset(data);
      } catch (e) {
        if (e instanceof ApiError) {
          setError(e.message);
          setStatus(e.status);
        } else {
          setError(t('assetList.serverError'));
        }
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [id, t],
  );

  useEffect(() => {
    if (!id) {
      return;
    }
    void loadAsset();
  }, [id, loadAsset]);

  useEffect(() => {
    if (!isManager) {
      setHolders([]);
      return;
    }

    let cancelled = false;
    const loadHolders = async () => {
      try {
        const response = await usersApi.listUsers({ page: 1, perPage: 100, role: 'holder' });
        if (!cancelled) {
          setHolders(response.data);
        }
      } catch (e) {
        if (!cancelled && e instanceof ApiError) {
          api.error({
            title: t('assetList.manager.holdersLoadErrorTitle'),
            description: formatApiError(e),
          });
        }
      }
    };

    void loadHolders();

    return () => {
      cancelled = true;
    };
  }, [api, formatApiError, isManager, t]);

  const openEditModal = () => {
    if (!asset) {
      return;
    }

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
    setIsEditModalOpen(true);
  };

  const openAssignModal = () => {
    if (!asset) {
      return;
    }

    assignForm.resetFields();
    if (asset.status === 'in_use') {
      assignForm.setFieldValue('reason', '');
    } else if (asset.responsible_person_id) {
      assignForm.setFieldValue('responsible_person_id', asset.responsible_person_id);
    }
    setIsAssignModalOpen(true);
  };

  const openDisposeModal = () => {
    disposeForm.resetFields();
    setIsDisposeModalOpen(true);
  };

  const toAssetPayload = (values: AssetFormValues): Omit<AssetUpdatePayload, 'version'> => ({
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
    if (!asset) {
      return;
    }

    try {
      const values = await assetForm.validateFields();
      await runSubmittingAction(async () => {
        const payload: AssetUpdatePayload = {
          ...toAssetPayload(values),
          version: asset.version,
        };
        await assetsApi.updateAsset(asset.id, payload);
        setIsEditModalOpen(false);
        await loadAsset(false);
        api.success({ title: t('assetList.manager.editSuccess') });
      });
    } catch {
      // Form validation failure is handled by Ant Design field errors.
    }
  };

  const handleAssignOrUnassign = async () => {
    if (!asset) {
      return;
    }

    try {
      const values = await assignForm.validateFields();
      await runSubmittingAction(async () => {
        if (asset.status === 'in_use') {
          await assetsApi.unassignAsset(asset.id, {
            reason: values.reason ?? '',
            version: asset.version,
          });
          api.success({ title: t('assetList.manager.unassignSuccess') });
        } else {
          await assetsApi.assignAsset(asset.id, {
            responsible_person_id: values.responsible_person_id ?? '',
            assignment_date: values.assignment_date,
            version: asset.version,
          });
          api.success({ title: t('assetList.manager.assignSuccess') });
        }

        setIsAssignModalOpen(false);
        await loadAsset(false);
      });
    } catch {
      // Form validation failure is handled by Ant Design field errors.
    }
  };

  const handleDispose = async () => {
    if (!asset) {
      return;
    }

    try {
      const values = await disposeForm.validateFields();
      await runSubmittingAction(async () => {
        await assetsApi.disposeAsset(asset.id, {
          disposal_reason: values.disposal_reason,
          version: asset.version,
        });
        setIsDisposeModalOpen(false);
        await loadAsset(false);
        api.success({ title: t('assetList.manager.disposeSuccess') });
      });
    } catch {
      // Form validation failure is handled by Ant Design field errors.
    }
  };

  const assetTextFields = useMemo<AssetTextFieldConfig[]>(
    () => [
      { name: 'name', label: t('assetList.form.name'), required: true, max: 120 },
      { name: 'model', label: t('assetList.form.model'), required: true, max: 120 },
      { name: 'supplier', label: t('assetList.form.supplier'), required: true, max: 120 },
      { name: 'location', label: t('assetList.form.location'), max: 120 },
      { name: 'department', label: t('assetList.form.department'), max: 100 },
    ],
    [t],
  );

  const commonModalProps = {
    cancelText: t('common.button.cancel'),
    confirmLoading: isSubmitting,
    destroyOnHidden: true,
    forceRender: true,
  };

  const renderAssetTextField = ({ name, label, required, max }: AssetTextFieldConfig) => {
    const rules: Array<{ required?: true; max?: number; message: string }> = [];
    if (required) {
      rules.push({ required: true, message: t('validation.required') });
    }
    if (typeof max === 'number') {
      const maxMessageMap: Record<number, string> = {
        100: t('validation.max100Chars'),
        120: t('validation.max120Chars'),
      };
      rules.push({ max, message: maxMessageMap[max] ?? t('validation.max120Chars') });
    }

    return (
      <Form.Item key={name} name={name} label={label} rules={rules}>
        <Input />
      </Form.Item>
    );
  };

  const renderContent = () => {
    if (loading) {
      return (
        <Card>
          <Skeleton active title paragraph={{ rows: 10 }} />
        </Card>
      );
    }

    if (status === 404) {
      return (
        <Card>
          <Result
            status="404"
            title="404"
            subTitle={t('assetList.error.notFound')}
            extra={
              <Button type="primary" onClick={() => navigate(-1)}>
                {t('common.button.back')}
              </Button>
            }
          />
        </Card>
      );
    }

    if (status === 403) {
      return (
        <Card>
          <Result
            status="403"
            title="403"
            subTitle={t('assetList.error.forbidden')}
            extra={
              <Button type="primary" onClick={() => navigate(-1)}>
                {t('common.button.back')}
              </Button>
            }
          />
        </Card>
      );
    }

    if (error || !asset) {
      return <Alert title={error || t('assetList.serverError')} type="error" showIcon />;
    }

    return (
      <Card
        title={
          <Space>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {t('assetList.detail.title', { assetCode: asset.asset_code })}
            </Typography.Title>
            <Tag color={STATUS_COLORS[asset.status]}>{t(`assetList.status.${asset.status}`)}</Tag>
          </Space>
        }
      >
        <Descriptions column={{ xxl: 3, xl: 3, lg: 2, md: 2, sm: 1, xs: 1 }} bordered>
          <Descriptions.Item label={t('assetList.columns.assetCode')}>
            {asset.asset_code}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.name')}>
            {asset.name}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.category')}>
            {asset.category}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.holder')}>
            {asset.responsible_person?.name ?? t('assetList.detail.unassigned')}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.model')}>
            {asset.model}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.specs')}>
            {asset.specs ?? t('assetList.detail.notAvailable')}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.supplier')}>
            {asset.supplier}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.activationDate')}>
            {formatDateValue(asset.activation_date, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.warrantyExpiry')}>
            {formatDateValue(asset.warranty_expiry, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.department')}>
            {asset.department}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.location')}>
            {asset.location}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.purchaseAmount')}>
            {formatAmountValue(asset.purchase_amount)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.columns.purchaseDate')}>
            {formatDateValue(asset.purchase_date, t)}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    );
  };

  return (
    <div style={pageContainerStyle}>
      {contextHolder}
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          {t('common.button.back')}
        </Button>

        {isManager && asset ? (
          <Space wrap>
            <Button onClick={openEditModal}>{t('assetList.actions.edit')}</Button>

            {asset.status === 'in_stock' ? (
              <Button onClick={openAssignModal}>{t('assetList.actions.assign')}</Button>
            ) : null}

            {asset.status === 'in_use' ? (
              <Button onClick={openAssignModal}>{t('assetList.actions.unassign')}</Button>
            ) : null}

            {asset.status === 'in_stock' ? (
              <Button danger onClick={openDisposeModal}>{t('assetList.actions.dispose')}</Button>
            ) : null}
          </Space>
        ) : null}

        {renderContent()}

        <Modal
          open={isEditModalOpen}
          title={asset ? t('assetList.manager.editTitle', { assetCode: asset.asset_code }) : ''}
          onCancel={() => setIsEditModalOpen(false)}
          onOk={() => void handleSaveAsset()}
          okText={t('common.button.save')}
          {...commonModalProps}
        >
          <Form form={assetForm} layout="vertical">
            {assetTextFields.slice(0, 2).map(renderAssetTextField)}

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

            {assetTextFields.slice(2, 3).map(renderAssetTextField)}

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

            {assetTextFields.slice(3).map(renderAssetTextField)}

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
            asset?.status === 'in_use'
              ? t('assetList.manager.unassignTitle', { assetCode: asset?.asset_code ?? '' })
              : t('assetList.manager.assignTitle', { assetCode: asset?.asset_code ?? '' })
          }
          onCancel={() => setIsAssignModalOpen(false)}
          onOk={() => void handleAssignOrUnassign()}
          okText={t('common.button.confirm')}
          {...commonModalProps}
        >
          <Form form={assignForm} layout="vertical">
            {asset?.status === 'in_use' ? (
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
          title={t('assetList.manager.disposeTitle', { assetCode: asset?.asset_code ?? '' })}
          onCancel={() => setIsDisposeModalOpen(false)}
          onOk={() => void handleDispose()}
          okText={t('common.button.confirm')}
          {...commonModalProps}
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
    </div>
  );
};

export default AssetDetail;
