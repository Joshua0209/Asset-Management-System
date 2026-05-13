import type { TFunction } from 'i18next';
import type { AssetCategory } from '../../api/assets';

export const ASSET_CATEGORY_OPTIONS: AssetCategory[] = [
  'phone',
  'computer',
  'tablet',
  'monitor',
  'printer',
  'network_equipment',
  'other',
];

export function isAssetCategory(value: string): value is AssetCategory {
  return ASSET_CATEGORY_OPTIONS.includes(value as AssetCategory);
}

export function getAssetCategoryLabel(t: TFunction, category: string): string {
  switch (category) {
    case 'phone':
      return t('assetList.categories.phone');
    case 'computer':
      return t('assetList.categories.computer');
    case 'tablet':
      return t('assetList.categories.tablet');
    case 'monitor':
      return t('assetList.categories.monitor');
    case 'printer':
      return t('assetList.categories.printer');
    case 'network_equipment':
      return t('assetList.categories.networkEquipment');
    case 'other':
      return t('assetList.categories.other');
    default:
      return category;
  }
}

export interface AssetFormValues {
  name: string;
  model: string;
  specs?: string;
  category: AssetCategory;
  supplier: string;
  purchase_date: string;
  purchase_amount: string;
  location?: string;
  department?: string;
  activation_date?: string;
  warranty_expiry?: string;
}

export interface AssetFormPayload {
  name: string;
  model: string;
  specs: string | null;
  category: AssetCategory;
  supplier: string;
  purchase_date: string;
  purchase_amount: string;
  location: string | null;
  department: string | null;
  activation_date: string | null;
  warranty_expiry: string | null;
}

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parseDateOnly(value?: string | null): Date | null {
  if (!value || !DATE_ONLY_PATTERN.test(value)) {
    return null;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function normalizeOptionalText(value?: string): string | null {
  const trimmed = value?.trim();
  return trimmed || null;
}

export function isFutureDate(value: string): boolean {
  const parsed = parseDateOnly(value);
  if (!parsed) {
    return false;
  }

  const todayUtc = new Date();
  todayUtc.setUTCHours(0, 0, 0, 0);
  return parsed.getTime() > todayUtc.getTime();
}

export function createPurchaseDateNotFutureValidator(t: TFunction) {
  return async (_: unknown, value?: string) => {
    if (!value) {
      return;
    }
    if (isFutureDate(value)) {
      throw new Error(t('validation.purchaseDateNotFuture'));
    }
  };
}

export function createWarrantyExpiryValidator(
  form: { getFieldValue: (name: keyof AssetFormValues) => unknown },
  t: TFunction,
) {
  return async (_: unknown, value?: string) => {
    if (!value) {
      return;
    }

    const warrantyDate = parseDateOnly(value);
    if (!warrantyDate) {
      return;
    }

    const purchaseDate = parseDateOnly(form.getFieldValue('purchase_date') as string | undefined);
    if (purchaseDate && warrantyDate.getTime() <= purchaseDate.getTime()) {
      throw new Error(t('validation.warrantyAfterPurchase'));
    }

    const activationDate = parseDateOnly(form.getFieldValue('activation_date') as string | undefined);
    if (activationDate && warrantyDate.getTime() <= activationDate.getTime()) {
      throw new Error(t('validation.warrantyAfterActivation'));
    }
  };
}

export function normalizeAssetFormValues(values: AssetFormValues): AssetFormPayload {
  return {
    name: values.name,
    model: values.model,
    specs: normalizeOptionalText(values.specs),
    category: values.category,
    supplier: values.supplier,
    purchase_date: values.purchase_date,
    purchase_amount: values.purchase_amount,
    location: normalizeOptionalText(values.location),
    department: normalizeOptionalText(values.department),
    activation_date: normalizeOptionalText(values.activation_date),
    warranty_expiry: normalizeOptionalText(values.warranty_expiry),
  };
}
