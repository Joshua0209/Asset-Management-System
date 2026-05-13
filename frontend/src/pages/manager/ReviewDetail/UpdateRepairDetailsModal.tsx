import React, { useEffect } from 'react';
import { Form, Input, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import { createAmountValidator } from '../../../utils/validators';
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

  useEffect(() => {
    if (open) {
      form.setFieldsValue(initialValues);
    }
  }, [open, initialValues, form]);

  const validateRepairCost = createAmountValidator(t, {
    formatKey: 'validation.repairCostFormat',
    positiveKey: 'validation.repairCostPositive',
  });

  const handleOk = async () => {
    let values: RepairDetailsValues;
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
      title={t('reviews.detailsTitle')}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('common.button.save')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item name="repair_date" label={t('reviews.form.repairDate')}>
          <Input type="date" />
        </Form.Item>
        <Form.Item name="fault_content" label={t('reviews.form.faultContent')}>
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item name="repair_plan" label={t('reviews.form.repairPlan')}>
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item
          name="repair_cost"
          label={t('reviews.form.repairCost')}
          rules={[{ validator: validateRepairCost }]}
        >
          <Input type="number" min={0} step="0.01" />
        </Form.Item>
        <Form.Item name="repair_vendor" label={t('reviews.form.repairVendor')}>
          <Input />
        </Form.Item>
      </Form>
    </Modal>
  );
};

export default UpdateRepairDetailsModal;
