import { TFunction } from 'i18next';

import i18n from '@/i18n';

export const moneyFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'TWD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const getActiveLocale = (): string => {
  const lng = i18n.resolvedLanguage ?? i18n.language ?? 'zh';
  return lng.startsWith('zh') ? 'zh-TW' : 'en-US';
};

export const formatDateValue = (value: string | null, t: TFunction): string => {
  if (!value) {
    return t('assetList.detail.notAvailable');
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(getActiveLocale());
};

export const formatAmountValue = (value: string | number): string => {
  const parsed = Number.parseFloat(String(value));
  return Number.isNaN(parsed) ? String(value) : moneyFormatter.format(parsed);
};

export const formatDateTime = (value: string | null | undefined): string => {
  if (!value) {
    return '-';
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(getActiveLocale());
};

export const formatRepairCost = (
  value: string | number | null | undefined,
): string => (value === null || value === undefined || value === '' ? '-' : `TWD ${value}`);
