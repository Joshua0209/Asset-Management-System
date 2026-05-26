import React, { useEffect, useState } from 'react';
import { Form, Input, Modal, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

import { isAntdValidationError } from '@/utils/antdForm';
import { createAmountValidator } from '@/utils/validators';
import type { RepairDetailsValues } from './useReviewActions';

interface UpdateRepairDetailsModalProps {
  open: boolean;
  initialValues: RepairDetailsValues;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (values: RepairDetailsValues) => Promise<void>;
}

const UpdateRepairDetailsModal: React.FC<UpdateRepairDetailsModalProps> = ({
  open,
  initialValues,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<RepairDetailsValues>();
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      form.setFieldsValue(initialValues);
      setDetailError(null);
    }
  }, [open, initialValues, form]);

  const validateRepairCost = createAmountValidator(t, {
    allowZero: true,
    formatKey: 'validation.repairCostFormat',
    positiveKey: 'validation.repairCostPositive',
  });

  const handleOk = async () => {
    let values: RepairDetailsValues;
    try {
      values = await form.validateFields();
    } catch (err) {
      if (!isAntdValidationError(err)) {
        console.error('Unexpected error in update-repair form validation', err);
      }
      return;
    }
    const normalizedValues: RepairDetailsValues = {};
    const repairDate = values.repair_date?.trim();
    if (repairDate) {
      normalizedValues.repair_date = repairDate;
    }
    const repairPlan = values.repair_plan?.trim();
    if (repairPlan) {
      normalizedValues.repair_plan = repairPlan;
    }
    const repairVendor = values.repair_vendor?.trim();
    if (repairVendor) {
      normalizedValues.repair_vendor = repairVendor;
    }
    const faultContent = values.fault_content?.trim();
    if (faultContent) {
      normalizedValues.fault_content = faultContent;
    }
    const repairCost = values.repair_cost?.trim();
    if (repairCost) {
      normalizedValues.repair_cost = repairCost;
    }
    if (Object.keys(normalizedValues).length === 0) {
      setDetailError(t('validation.atLeastOneRepairDetail'));
      return;
    }
    setDetailError(null);
    await onSubmit(normalizedValues);
  };

  return (
    <Modal
      open={open}
      title={t('reviews.detailsTitle')}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('common.button.save')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="repair_date"
          label={t('reviews.form.repairDate')}
        >
          <Input type="date" />
        </Form.Item>
        <Form.Item name="fault_content" label={t('reviews.form.faultContent')}>
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item
          name="repair_plan"
          label={t('reviews.form.repairPlan')}
        >
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item
          name="repair_cost"
          label={t('reviews.form.repairCost')}
          rules={[{ validator: validateRepairCost }]}
        >
          <Input type="number" min={0} step="0.01" />
        </Form.Item>
        <Form.Item
          name="repair_vendor"
          label={t('reviews.form.repairVendor')}
        >
          <Input />
        </Form.Item>
        {detailError ? <Typography.Text type="danger">{detailError}</Typography.Text> : null}
      </Form>
    </Modal>
  );
};

export default UpdateRepairDetailsModal;
