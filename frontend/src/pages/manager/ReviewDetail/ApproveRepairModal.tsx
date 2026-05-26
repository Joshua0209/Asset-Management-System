import React, { useEffect } from 'react';
import { Form, Input, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import { isAntdValidationError } from '@/utils/antdForm';
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
    allowZero: true,
    formatKey: 'validation.repairCostFormat',
    positiveKey: 'validation.repairCostPositive',
  });

  const handleOk = async () => {
    let values: ApproveValues;
    try {
      values = await form.validateFields();
    } catch (err) {
      if (!isAntdValidationError(err)) {
        console.error('Unexpected error in approve-repair form validation', err);
      }
      return;
    }
    const normalizedValues: ApproveValues = {};
    const repairPlan = values.repair_plan?.trim();
    if (repairPlan) {
      normalizedValues.repair_plan = repairPlan;
    }
    const repairVendor = values.repair_vendor?.trim();
    if (repairVendor) {
      normalizedValues.repair_vendor = repairVendor;
    }
    const repairCost = values.repair_cost?.trim();
    if (repairCost) {
      normalizedValues.repair_cost = repairCost;
    }
    const plannedDate = values.planned_date?.trim();
    if (plannedDate) {
      normalizedValues.planned_date = plannedDate;
    }
    await onSubmit(normalizedValues);
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
        >
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item
          name="repair_vendor"
          label={t('reviews.form.repairVendor')}
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
        >
          <Input type="date" />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default ApproveRepairModal;
