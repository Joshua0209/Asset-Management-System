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
import type { AssetRecord, AssetUpdatePayload } from '../api/assets';
import type { UserRecord } from '../api/users';
import { STATUS_COLORS } from '../components/assets/constants';
import AssetFormFields from '../components/assets/AssetFormFields';
import {
  createWarrantyExpiryValidator,
  normalizeAssetFormValues,
  type AssetFormValues,
} from '../components/assets/assetFormShared';
import { formatDateValue, formatAmountValue } from '../utils/format';

interface AssignFormValues {
  responsible_person_id?: string;
  assignment_date?: string;
  reason?: string;
  unassignment_date?: string;
}

interface DisposeFormValues {
  disposal_reason: string;
}


const pageContainerStyle: React.CSSProperties = {
  maxWidth: 1200,
  margin: '0 auto',
};

function getTodayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

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
  const todayIsoDate = useMemo(() => getTodayIsoDate(), []);
  const formatApiError = useCallback((apiError: ApiError): string => getApiErrorMessage(apiError, t), [t]);
  const validatePurchaseAmount = createAmountValidator(t, { required: true });
  const validateWarrantyExpiry = useMemo(
    () => createWarrantyExpiryValidator(assetForm, t),
    [assetForm, t],
  );

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

  const showActionError = useCallback(
    (error: unknown) => {
      if (error instanceof ApiError) {
        if (error.code === 'conflict') {
          Modal.warning({
            title: t('errors.conflictTitle'),
            content: formatApiError(error),
            onOk: async () => {
              await loadAsset();
            },
          });
        } else {
          api.error({
            title: t('assetList.manager.actionFailedTitle'),
            description: formatApiError(error),
          });
        }
      }
    },
    [api, formatApiError, loadAsset, t],
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

  useEffect(() => {
    if (!id) {
      return;
    }
    loadAsset();
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
      category: asset.category as AssetFormValues['category'],
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
      assignForm.setFieldsValue({
        reason: '',
        unassignment_date: todayIsoDate,
      });
    } else {
      assignForm.setFieldValue('assignment_date', todayIsoDate);
      if (asset.responsible_person_id) {
        assignForm.setFieldValue('responsible_person_id', asset.responsible_person_id);
      }
    }
    setIsAssignModalOpen(true);
  };

  const openDisposeModal = () => {
    disposeForm.resetFields();
    setIsDisposeModalOpen(true);
  };

  const handleSaveAsset = async () => {
    if (!asset) {
      return;
    }

    try {
      const values = await assetForm.validateFields();
      await runSubmittingAction(async () => {
        const payload: AssetUpdatePayload = {
          ...normalizeAssetFormValues(values),
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
            unassignment_date: values.unassignment_date ?? '',
            version: asset.version,
          });
          api.success({ title: t('assetList.manager.unassignSuccess') });
        } else {
          await assetsApi.assignAsset(asset.id, {
            responsible_person_id: values.responsible_person_id ?? '',
            assignment_date: values.assignment_date ?? '',
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

  const commonModalProps = {
    cancelText: t('common.button.cancel'),
    confirmLoading: isSubmitting,
    destroyOnHidden: true,
    forceRender: true,
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
          <Descriptions.Item label={t('assetList.detail.assignmentDate')}>
            {formatDateValue(asset.assignment_date, t)}
          </Descriptions.Item>
          <Descriptions.Item label={t('assetList.detail.unassignmentDate')}>
            {formatDateValue(asset.unassignment_date, t)}
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
            <AssetFormFields
              t={t}
              validatePurchaseAmount={validatePurchaseAmount}
              validateWarrantyExpiry={validateWarrantyExpiry}
            />
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
              <>
                <Form.Item
                  name="reason"
                  label={t('assetList.form.unassignReason')}
                  rules={[{ required: true, message: t('validation.required') }]}
                >
                  <Input.TextArea rows={3} />
                </Form.Item>

                <Form.Item
                  name="unassignment_date"
                  label={t('assetList.form.unassignmentDate')}
                  rules={[{ required: true, message: t('validation.required') }]}
                >
                  <Input
                    type="date"
                    max={todayIsoDate}
                    min={asset?.assignment_date ?? undefined}
                  />
                </Form.Item>
              </>
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
                  <Input type="date" max={todayIsoDate} />
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
