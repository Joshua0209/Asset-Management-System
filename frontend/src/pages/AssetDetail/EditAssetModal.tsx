import React, { useEffect, useMemo } from 'react';
import { Form, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AssetRecord } from '../../api/assets';
import { createAmountValidator } from '../../utils/validators';
import AssetFormFields from '../../components/assets/AssetFormFields';
import {
  createWarrantyExpiryValidator,
  normalizeAssetFormValues,
  type AssetFormPayload,
  type AssetFormValues,
} from '../../components/assets/assetFormShared';

interface EditAssetModalProps {
  open: boolean;
  asset: AssetRecord;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (payload: AssetFormPayload) => Promise<void>;
}

const EditAssetModal: React.FC<EditAssetModalProps> = ({
  open,
  asset,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<AssetFormValues>();

  const validatePurchaseAmount = createAmountValidator(t, { required: true });
  const validateWarrantyExpiry = useMemo(
    () => createWarrantyExpiryValidator(form, t),
    [form, t],
  );

  useEffect(() => {
    if (open) {
      form.setFieldsValue({
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
    }
  }, [open, asset, form]);

  const handleOk = async () => {
    let values: AssetFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    await onSubmit(normalizeAssetFormValues(values));
  };

  return (
    <Modal
      open={open}
      title={t('assetList.manager.editTitle', { assetCode: asset.asset_code })}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('common.button.save')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
      forceRender
    >
      <Form form={form} layout="vertical">
        <AssetFormFields
          t={t}
          validatePurchaseAmount={validatePurchaseAmount}
          validateWarrantyExpiry={validateWarrantyExpiry}
        />
      </Form>
    </Modal>
  );
};

export default EditAssetModal;
