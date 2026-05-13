import React, { useEffect } from 'react';
import { Form, Input, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import type { RejectValues } from './useReviewActions';

interface RejectRepairModalProps {
  open: boolean;
  initialValues: RejectValues;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (values: RejectValues) => Promise<void>;
}

const RejectRepairModal: React.FC<RejectRepairModalProps> = ({
  open,
  initialValues,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<RejectValues>();

  useEffect(() => {
    if (open) {
      form.setFieldsValue(initialValues);
    }
  }, [open, initialValues, form]);

  const handleOk = async () => {
    let values: RejectValues;
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
      title={t('reviews.rejectTitle')}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('reviews.actions.reject')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="rejection_reason"
          label={t('reviews.form.rejectionReason')}
          rules={[{ required: true, message: t('validation.required') }]}
        >
          <Input.TextArea rows={4} />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default RejectRepairModal;
