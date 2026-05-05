import { TFunction } from 'i18next';

export const moneyFormatter = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'TWD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export const formatDateValue = (value: string | null, t: TFunction): string => {
  if (!value) {
    return t('assetList.detail.notAvailable');
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
};

export const formatAmountValue = (value: string | number): string => {
  const parsed = Number.parseFloat(String(value));
  return Number.isNaN(parsed) ? String(value) : moneyFormatter.format(parsed);
};
