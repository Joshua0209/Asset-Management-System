import React from 'react';
import { Form, Input, Select } from 'antd';
import type { TFunction } from 'i18next';
import { ASSET_CATEGORY_OPTIONS, createPurchaseDateNotFutureValidator } from './assetFormShared';

interface AssetFormFieldsProps {
  t: TFunction;
  validatePurchaseAmount: (_: unknown, value?: string) => Promise<void>;
  validateWarrantyExpiry: (_: unknown, value?: string) => Promise<void>;
}

const AssetFormFields: React.FC<AssetFormFieldsProps> = ({
  t,
  validatePurchaseAmount,
  validateWarrantyExpiry,
}) => {
  const validatePurchaseDateNotFuture = createPurchaseDateNotFutureValidator(t);

  return (
    <>
      <Form.Item
        name="name"
        label={t('assetList.form.name')}
        rules={[
          { required: true, message: t('validation.required') },
          { max: 120, message: t('validation.max120Chars') },
        ]}
      >
        <Input />
      </Form.Item>

      <Form.Item
        name="model"
        label={t('assetList.form.model')}
        rules={[
          { required: true, message: t('validation.required') },
          { max: 120, message: t('validation.max120Chars') },
        ]}
      >
        <Input />
      </Form.Item>

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
          options={ASSET_CATEGORY_OPTIONS.map((category) => ({
            value: category,
            label: category,
          }))}
        />
      </Form.Item>

      <Form.Item
        name="supplier"
        label={t('assetList.form.supplier')}
        rules={[
          { required: true, message: t('validation.required') },
          { max: 120, message: t('validation.max120Chars') },
        ]}
      >
        <Input />
      </Form.Item>

      <Form.Item
        name="purchase_date"
        label={t('assetList.form.purchaseDate')}
        rules={[
          { required: true, message: t('validation.required') },
          { validator: validatePurchaseDateNotFuture },
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

      <Form.Item
        name="location"
        label={t('assetList.form.location')}
        rules={[{ max: 120, message: t('validation.max120Chars') }]}
      >
        <Input />
      </Form.Item>

      <Form.Item
        name="department"
        label={t('assetList.form.department')}
        rules={[{ max: 100, message: t('validation.max100Chars') }]}
      >
        <Input />
      </Form.Item>

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
    </>
  );
};

export default AssetFormFields;
