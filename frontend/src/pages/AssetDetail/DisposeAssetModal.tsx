import React, { useEffect } from 'react';
import { Form, Input, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AssetRecord } from '../../api/assets';

export interface DisposeFormValues {
  disposal_reason: string;
}

interface DisposeAssetModalProps {
  open: boolean;
  asset: AssetRecord;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (values: DisposeFormValues) => Promise<void>;
}

const DisposeAssetModal: React.FC<DisposeAssetModalProps> = ({
  open,
  asset,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<DisposeFormValues>();

  useEffect(() => {
    if (open) {
      form.resetFields();
    }
  }, [open, form]);

  const handleOk = async () => {
    let values: DisposeFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    await onSubmit(values);
  };

  return (
    <Modal
      open={open}
      title={t('assetList.manager.disposeTitle', { assetCode: asset.asset_code })}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('common.button.confirm')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
      forceRender
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="disposal_reason"
          label={t('assetList.form.disposalReason')}
          rules={[{ required: true, message: t('validation.required') }]}
        >
          <Input.TextArea rows={4} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default DisposeAssetModal;
