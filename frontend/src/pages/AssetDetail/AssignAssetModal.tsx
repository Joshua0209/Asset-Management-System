import React, { useEffect, useMemo } from 'react';
import { Form, Input, Modal, Select } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AssetRecord } from '../../api/assets';
import type { UserRecord } from '../../api/users';

export interface AssignFormValues {
  responsible_person_id?: string;
  assignment_date?: string;
  reason?: string;
  unassignment_date?: string;
}

function getTodayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

interface AssignAssetModalProps {
  open: boolean;
  asset: AssetRecord;
  holders: UserRecord[];
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (values: AssignFormValues) => Promise<void>;
}

const AssignAssetModal: React.FC<AssignAssetModalProps> = ({
  open,
  asset,
  holders,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<AssignFormValues>();
  const isUnassign = asset.status === 'in_use';
  const todayIsoDate = useMemo(() => getTodayIsoDate(), []);

  useEffect(() => {
    if (!open) {
      return;
    }
    form.resetFields();
    if (isUnassign) {
      form.setFieldsValue({
        reason: '',
        unassignment_date: todayIsoDate,
      });
    } else {
      form.setFieldValue('assignment_date', todayIsoDate);
      if (asset.responsible_person_id) {
        form.setFieldValue('responsible_person_id', asset.responsible_person_id);
      }
    }
  }, [open, isUnassign, asset.responsible_person_id, todayIsoDate, form]);

  const handleOk = async () => {
    let values: AssignFormValues;
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
      title={
        isUnassign
          ? t('assetList.manager.unassignTitle', { assetCode: asset.asset_code })
          : t('assetList.manager.assignTitle', { assetCode: asset.asset_code })
      }
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText={t('common.button.confirm')}
      cancelText={t('common.button.cancel')}
      confirmLoading={isSubmitting}
      destroyOnHidden
      forceRender
    >
      <Form form={form} layout="vertical">
        {isUnassign ? (
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
                min={asset.assignment_date ?? undefined}
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
  );
};

export default AssignAssetModal;
