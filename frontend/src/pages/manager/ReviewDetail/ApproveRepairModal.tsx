import React, { useEffect } from 'react';
import { Form, Input, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import { createAmountValidator } from '@/utils/validators';
import type { ApproveValues } from './useReviewActions';

interface ApproveRepairModalProps {
  open: boolean;
  initialValues: ApproveValues;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (values: ApproveValues) => Promise<void>;
}

const ApproveRepairModal: React.FC<ApproveRepairModalProps> = ({
  open,
  initialValues,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<ApproveValues>();

  useEffect(() => {
    if (open) {
      form.setFieldsValue(initialValues);
    }
  }, [open, initialValues, form]);

  const validateRepairCost = createAmountValidator(t, {
    required: true,
    formatKey: 'validation.repairCostFormat',
    positiveKey: 'validation.repairCostPositive',
  });

  const handleOk = async () => {
    let values: ApproveValues;
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
      title={t('reviews.approveTitle')}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('reviews.actions.approve')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
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
          rules={[{ validator: validateRepairCost }]}
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
  );
};

export default ApproveRepairModal;
